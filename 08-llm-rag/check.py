"""Prescription check: does a prescription in the EMR agree with the guidelines?

    python check.py rx02                    # one record from prescriptions.csv, version v2
    python check.py rx02 --version v1       # the LLM decides everything
    python check.py rx02 --model qwen/qwen3.5-9b

The same pipeline as rag.py (retrieve guideline passages, ask an LLM), asked a different question once it sits
inside a workflow: not "is this answer good?" but "does it catch the errors?". Two versions:

  v1  **The LLM decides everything.** Patient, prescription and passages go in; a verdict comes out
      (correct / incorrect / not covered) with a reason.
  v2  **The LLM reads, Python counts.** The LLM only extracts the dosing rule that applies to this patient from
      the passages, as JSON (mg/kg, min/max, cap, interval, duration, "do not give"), with a verbatim quote.
      Python checks the quote is really in the passages, then does the arithmetic and the comparison. If the
      quote isn't there, the verdict is "unsure": a person looks, instead of the check guessing.

prescriptions.csv holds SIMULATED records (no real patients), each with the expected verdict and the guideline
page it rests on. evaluate_check.py scores a version on all of them.
"""

import argparse
import json
import re
from dataclasses import asdict

import pandas as pd

import rag

HERE = rag.HERE
RECORDS = HERE / "prescriptions.csv"
TOLERANCE = 0.10          # a prescribed dose within 10% of the guideline range counts as matching (rounding)
K = 8                     # passages: a dosing rule is often a table row, so take a few more than rag.py
RETRIEVER = "embed"       # EMR wording rarely matches the guideline's words; see evaluate_check.py --retrieval-only

PROMPTS = {
    "v1": (
        "You check prescriptions against Ethiopian national guidelines, using ONLY the numbered guideline passages "
        "provided.\n"
        "- verdict \"correct\": the passages give a rule for this drug in this patient and the prescription follows it "
        "(dose for age and weight, interval, number of doses, duration, infusion time).\n"
        "- verdict \"incorrect\": the passages give a rule and the prescription breaks it, or the passages say this "
        "drug must not be given to this patient.\n"
        "- verdict \"not covered\": the passages give no rule for this drug in this patient.\n"
        "Reply with JSON only: {\"verdict\": \"...\", \"reason\": \"one or two sentences, citing passages like [1]\"}"
    ),
    "v2": (
        "You read Ethiopian national guidelines. From ONLY the numbered passages, extract the dosing rule for the "
        "given drug that applies to THIS patient (age, weight, pregnancy, diagnosis). Do not judge any prescription "
        "and do not calculate a dose for the patient's weight: copy the rule.\n"
        "Reply with JSON only, using null for anything the passages do not state:\n"
        "{\"covered\": true if the passages give a dosing rule or a prohibition for this drug in this patient,\n"
        " \"do_not_give\": true if the passages say not to give this drug to this patient, or restrict it to "
        "patients this one is not (another age group, trimester, condition),\n"
        " \"do_not_give_reason\": string or null,\n"
        " \"amount_min\": number, \"amount_max\": number, exactly as written in the quote, before any calculation "
        "(2 and 4 for '2–4 mg/kg'; same as amount_min if the rule gives one number),\n"
        " \"per_kg\": true if the amount is per kg of body weight,\n"
        " \"max_amount\": the cap per dose, if stated,\n"
        " \"every_hours\": hours between doses (once daily = 24),\n"
        " \"n_doses\": total number of doses (single dose = 1),\n"
        " \"duration_days\": days of treatment (1 month = 30 days),\n"
        " \"over_hours\": hours over which an infusion or a fluid volume is given,\n"
        " \"quote\": the sentence or table row the rule comes from, verbatim,\n"
        " \"passage\": its passage number}\n"
        "Give amounts in the unit stated in the request. If the regimen has several steps, give the first step. "
        "If the passages give rules for several age or weight groups, use the group this patient is in."
    ),
}


# ---------------------------------------------------------------- the record


def load_records(path=RECORDS):
    text = ["pregnancy", "other", "error_type", "doc", "pages", "quote"]
    return pd.read_csv(path, dtype=dict.fromkeys(text, str)).fillna(dict.fromkeys(text, ""))


def patient(r):
    """The record as the EMR would show it."""
    lines = [f"Patient: {'male' if r.sex == 'M' else 'female'}, {r.age}, {r.weight_kg:g} kg"
             + (f", {r.pregnancy}" if r.pregnancy else ""),
             f"Diagnosis: {r.diagnosis}"]
    if r.other:
        lines.append(f"Other: {r.other}")
    return "\n".join(lines)


def search_query(r):
    """What the EMR knows: drug, diagnosis, other conditions. Pregnancy matters for many rules, so it goes in too."""
    return f"{r.drug} {r.diagnosis} {r.other}" + (" pregnancy" if "trimester" in r.pregnancy else "")


# ---------------------------------------------------------------- the LLM call


def ask(client, settings, system, user):
    response = client.chat.completions.create(
        model=settings.model, temperature=settings.temperature, max_tokens=800, **rag.thinking_switch(settings.thinking),
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
    text = (response.choices[0].message.content or "").strip()
    return parse(text), text


def parse(text):
    """The JSON object in a reply. If it isn't valid JSON (a stray quote inside the reason), keep the stated verdict."""
    found = re.search(r"\{.*\}", text, re.S)
    try:
        return json.loads(found.group(0)) if found else {}
    except json.JSONDecodeError:
        pass
    verdict = re.search(r'"verdict"\s*:\s*"([^"]+)"', text)
    reason = re.search(r'"reason"\s*:\s*"(.*)', text, re.S)
    return {"verdict": verdict.group(1), "reason": reason.group(1) if reason else ""} if verdict else {}


# ---------------------------------------------------------------- v2: Python does the arithmetic


def number(x):
    try:
        return None if x is None or pd.isna(x) else float(x)
    except (TypeError, ValueError):
        return None


def flat(s):
    """Letters and digits only: PDF text breaks words ("condi - tions") and spaces table cells unpredictably."""
    return re.sub(r"[^0-9a-z]", "", str(s).lower())


def stated(amount, text):
    """Does this number appear in the text as a number (also as grams, if the rule was converted to mg)?"""
    text = text.replace(",", "")
    return any(re.search(rf"(?<![\d.]){a:g}(?![\d.])", text) for a in (amount, amount / 1000))


def grounded(rule, contexts):
    """Is the quote really in the passages, and are the extracted amounts in the cited passage? (An LLM can misread
    a flattened table and quote a row that doesn't exist.)"""
    quote = flat(rule.get("quote") or "")
    if not quote or not any(quote in flat(c) for c in contexts):
        return False
    n = number(rule.get("passage"))
    source = contexts[int(n) - 1] if n and 1 <= n <= len(contexts) else " ".join(contexts)
    amounts = [number(rule.get(f)) for f in ("amount_min", "amount_max", "max_amount")]
    return all(stated(a, source) for a in amounts if a is not None)


def compare(r, rule, contexts):
    """Prescription vs extracted rule -> (verdict, reason). All arithmetic happens here, none in the LLM."""
    cite = f" [{rule['passage']}]" if rule.get("passage") else ""
    if not rule.get("covered") and not rule.get("do_not_give"):
        return "not covered", "The retrieved passages give no rule for this drug in this patient."
    if not grounded(rule, contexts):
        return "unsure", f"The extracted rule is not in the passages as quoted ({rule.get('quote')!r}): a person should check."
    if rule.get("do_not_give"):
        return "incorrect", f"The guideline says not to give it: {rule.get('do_not_give_reason') or rule.get('quote')}{cite}"
    lo, hi, cap = number(rule.get("amount_min")), number(rule.get("amount_max")), number(rule.get("max_amount"))
    hi = hi if hi is not None else lo
    if lo is not None and hi < lo:
        return "unsure", f"The extracted rule is inconsistent (minimum {lo:g}, maximum {hi:g}): a person should check."
    problems, compared, expected = [], 0, ""
    if lo is not None:
        compared += 1
        if rule.get("per_kg"):
            lo, hi = lo * r.weight_kg, hi * r.weight_kg
        if cap is not None:
            lo, hi = min(lo, cap), min(hi, cap)
        expected = f"{lo:g}" + (f"–{hi:g}" if hi != lo else "") + f" {r.unit}"
        if not lo * (1 - TOLERANCE) <= r.amount <= hi * (1 + TOLERANCE):
            per_kg = f" ({r.amount / r.weight_kg:.3g} {r.unit}/kg)" if rule.get("per_kg") else ""
            problems.append(f"{r.amount:g} {r.unit}{per_kg} prescribed; the rule gives {expected} for {r.weight_kg:g} kg")
    for field, label in [("every_hours", "hours between doses"), ("n_doses", "doses"),
                         ("duration_days", "days"), ("over_hours", "hours to give it over")]:
        want, got = number(rule.get(field)), number(getattr(r, field))
        if want is not None and got is not None:
            compared += 1
            if abs(got - want) > TOLERANCE * want:
                problems.append(f"{got:g} {label} prescribed; the rule gives {want:g}")
    if problems:
        return "incorrect", "; ".join(problems) + cite
    if not compared:
        return "unsure", f"The extracted rule has nothing to compare (no amount, interval or duration): a person should check.{cite}"
    return "correct", f"Matches the rule{(': ' + expected) if expected else ''}{cite}"


# ---------------------------------------------------------------- one record


def check(r, retriever, settings=rag.Settings(), version="v2", client=None):
    hits = retriever.search(search_query(r), settings.k)
    client = client or rag.llm_client()
    passages = rag.format_passages(hits)
    if version == "v1":
        reply, raw = ask(client, settings, PROMPTS["v1"],
                         f"Passages:\n\n{passages}\n\n{patient(r)}\nPrescription: {r.prescription}")
        verdict, reason, rule = str(reply.get("verdict", "")).lower().strip(), reply.get("reason", raw), None
    else:
        rule, raw = ask(client, settings, PROMPTS["v2"],
                        f"Passages:\n\n{passages}\n\n{patient(r)}\nDrug: {r.drug} (amounts in {r.unit})")
        verdict, reason = compare(r, rule, hits.text.tolist()) if rule else ("", raw)
    return {"id": r.id, "verdict": verdict, "reason": reason, "rule": rule, "raw": raw,
            "contexts": hits.text.tolist(), "sources": [f"{d}:p{p}" for d, p in zip(hits.doc, hits.page)],
            "version": version, "settings": asdict(settings)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("record", help="an id from prescriptions.csv, e.g. rx02")
    ap.add_argument("--version", default="v2", choices=list(PROMPTS))
    ap.add_argument("--model", default=rag.Settings.model)
    ap.add_argument("--k", type=int, default=K)
    ap.add_argument("--retriever", default=RETRIEVER, choices=["tfidf", "embed"])
    a = ap.parse_args()
    s = rag.Settings(model=a.model, k=a.k, retriever=a.retriever)
    r = next(load_records().query("id == @a.record").itertuples())
    out = check(r, rag.build(s), s, a.version)
    print(f"{patient(r)}\nPrescription: {r.prescription}\n\nPassages: {', '.join(out['sources'])}")
    if out["rule"]:
        print("Rule (LLM):", json.dumps(out["rule"], ensure_ascii=False))
    source = f"{r.doc} p.{r.pages}" if r.doc else "no guideline page"
    print(f"\nVerdict: {out['verdict']}\nReason: {out['reason']}\n\nExpected: {r.expected} ({r.error_type or 'no error'}); {source}")


if __name__ == "__main__":
    main()
