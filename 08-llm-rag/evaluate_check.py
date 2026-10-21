"""Evaluate one version of the prescription check on prescriptions.csv, and log it to MLflow.

    python evaluate_check.py --version v1 --run-name "v1: LLM decides"
    python evaluate_check.py --version v2 --run-name "v2: LLM reads, Python counts"
    python evaluate_check.py --version v2 --model qwen/qwen3.5-9b --run-name "v2, smaller model"
    python evaluate_check.py --retrieval-only           # no LLM: is the right guideline page among the passages?
    python evaluate_check.py --retrieval-only --retriever tfidf     # the same, with rag.py's keyword search
    python evaluate_check.py --version v2 --docs markdown --run-name "v2, Markdown"   # the guidelines as Markdown
    python evaluate_check.py --no-judge                 # skip the Ragas judge

What matters once the check sits in a workflow:
  - **Sensitivity**: of the prescriptions with an error, how many does it flag as incorrect?
  - **Specificity**: of the correct prescriptions, how many does it pass? (Every false alarm costs a clinician's time.)
  - Per **error type** (dose, age band, pregnancy, duration/frequency, contraindication), as counts: "3 of 5".
    With 44 records, one record moves a percentage by 2–5 points. Say counts.
  - **Faithfulness** of the reason to the retrieved passages (Ragas judge): does the reason say only what the
    guideline says?

Verdicts are saved in results/ and reused when the same settings are run again.
"""

import argparse
import asyncio
import hashlib
import json
import os
import re
from dataclasses import asdict

import pandas as pd

os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")
os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")

import check  # noqa: E402
import rag  # noqa: E402
from evaluate import JUDGE_MODEL, RESULTS  # noqa: E402

ERROR_TYPES = ["dose", "age_band", "pregnancy", "duration_frequency", "contraindication"]


def retrieval_checks(records, retriever, k):
    rows = []
    for r in records.itertuples():
        pages = [int(p) for p in str(r.pages).split(";") if p.strip()]
        hits = retriever.search(check.search_query(r), k)
        rows.append({"id": r.id, "hit": any(d == r.doc and p in pages for d, p in zip(hits.doc, hits.page))
                     if pages else None})
    return pd.DataFrame(rows)


def get_verdicts(records, retriever, settings, version):
    """Check every record, or reuse saved verdicts from an identical earlier run."""
    RESULTS.mkdir(exist_ok=True)
    blob = json.dumps(rag.run_params(settings), sort_keys=True) + version + check.PROMPTS[version] + str(len(records))
    path = RESULTS / f"check_{version}_{hashlib.md5(blob.encode()).hexdigest()[:10]}.jsonl"
    if path.exists():
        print(f"reusing saved verdicts: {path.name}")
        saved = [json.loads(line) for line in path.read_text().splitlines()]
        for r, v in zip(records.itertuples(), saved):     # re-read the saved replies: fixing Python costs no LLM calls
            if version == "v1":
                reply = check.parse(v["raw"])
                v["verdict"], v["reason"] = str(reply.get("verdict", "")).lower().strip(), reply.get("reason", v["raw"])
            elif v["rule"]:
                v["verdict"], v["reason"] = check.compare(r, v["rule"], v["contexts"])
        return saved
    client, out = rag.llm_client(), []
    for i, r in enumerate(records.itertuples(), 1):
        print(f"  checking {i}/{len(records)}: {r.id}", flush=True)
        out.append(check.check(r, retriever, settings, version, client))
    path.write_text("\n".join(json.dumps(v, ensure_ascii=False) for v in out))
    return out


async def faithfulness(records, verdicts, judge_model=JUDGE_MODEL, concurrency=4):
    from ragas.cache import DiskCacheBackend
    from ragas.llms import llm_factory
    from ragas.metrics.collections import Faithfulness

    judge = llm_factory(judge_model, client=rag.llm_client(async_=True), cache=DiskCacheBackend(str(rag.HERE / ".ragas_cache")),
                        temperature=0.0, max_tokens=8192)
    metric, gate = Faithfulness(llm=judge), asyncio.Semaphore(concurrency)

    async def one(r, v):
        async with gate:
            try:
                score = (await metric.ascore(user_input=f"{check.patient(r)}\nPrescription: {r.prescription}",
                                             response=f"{v['verdict']}: {v['reason']}",
                                             retrieved_contexts=v["contexts"])).value
                return {"id": r.id, "faithfulness": score}
            except Exception as e:        # a judge can fail to produce valid output; record, don't crash
                return {"id": r.id, "faithfulness": None, "faithfulness_error": f"{type(e).__name__}: {e}"[:200]}

    return pd.DataFrame(await asyncio.gather(*[one(r, v) for r, v in zip(records.itertuples(), verdicts)]))


def summarise(table):
    s, counts = {}, {}
    if "hit" in table:
        s["retrieval_hit_rate"] = table.hit.dropna().astype(float).mean()
    if "verdict" not in table:
        return s, counts
    errors, fine = table[table.expected == "incorrect"], table[table.expected == "correct"]
    counts["errors caught"] = (int((errors.verdict == "incorrect").sum()), len(errors))
    counts["correct passed"] = (int((fine.verdict == "correct").sum()), len(fine))
    counts["false alarms"] = (int((fine.verdict == "incorrect").sum()), len(fine))
    counts["'unsure' (sent to a person)"] = (int((table.verdict == "unsure").sum()), len(table))
    counts["said 'not covered' on a covered record"] = (int(((table.expected != "not covered") & (table.verdict == "not covered")).sum()),
                                                        int((table.expected != "not covered").sum()))
    counts["'not covered' record recognised"] = (int(((table.expected == "not covered") & (table.verdict == "not covered")).sum()),
                                                 int((table.expected == "not covered").sum()))
    for t in ERROR_TYPES:
        e = errors[errors.error_type == t]
        counts[f"caught: {t}"] = (int((e.verdict == "incorrect").sum()), len(e))
    s["sensitivity"] = counts["errors caught"][0] / counts["errors caught"][1]
    s["specificity"] = counts["correct passed"][0] / counts["correct passed"][1]
    s["verdict_accuracy"] = (table.verdict == table.expected).mean()
    if "faithfulness" in table and table.faithfulness.notna().any():
        s["faithfulness"] = pd.to_numeric(table.faithfulness, errors="coerce").mean()
    return s, counts


def evaluate(settings, version="v2", run_name=None, retrieval_only=False, judge=True, judge_model=JUDGE_MODEL, limit=None, log=True):
    records = check.load_records()
    if limit:
        records = records.head(limit)
    retriever = rag.build(settings)
    table = records[["id", "expected", "error_type", "prescription", "doc", "pages"]].merge(
        retrieval_checks(records, retriever, settings.k), on="id")
    if not retrieval_only:
        verdicts = get_verdicts(records, retriever, settings, version)
        table["verdict"] = [v["verdict"] for v in verdicts]
        table["reason"] = [v["reason"] for v in verdicts]
        table["sources"] = ["; ".join(v["sources"]) for v in verdicts]
        if judge:
            table = table.merge(asyncio.run(faithfulness(records, verdicts, judge_model)), on="id", how="left")
    summary, counts = summarise(table)
    if not retrieval_only:
        RESULTS.mkdir(exist_ok=True)
        slug = re.sub(r"[^a-z0-9]+", "_", (run_name or f"{version} {settings.model}").lower()).strip("_")
        table.to_csv(RESULTS / f"check_{slug}.csv", index=False)
    if log:
        import mlflow

        mlflow.set_experiment("prescription-check")
        with mlflow.start_run(run_name=run_name):
            mlflow.log_params(asdict(settings) | {
                "version": version, "index_fingerprint": rag.fingerprint(retriever.passages), "n_records": len(records),
                "judge_model": judge_model if judge and not retrieval_only else "-",
                "retriever_detail": "tfidf-1-2gram" if settings.retriever == "tfidf" else rag.EMBED_MODEL})
            if not retrieval_only:
                mlflow.log_text(check.PROMPTS[version], "prompt.txt")
            mlflow.log_metrics({k: float(v) for k, v in summary.items()}
                               | {re.sub(r"[^a-z0-9_]+", "_", k.lower()).strip("_"): float(n) for k, (n, _) in counts.items()})
            mlflow.log_table(table.astype(str), "per_record.json")
    return table, summary, counts


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", default="v2", choices=list(check.PROMPTS))
    ap.add_argument("--model", default=rag.Settings.model)
    ap.add_argument("--k", type=int, default=check.K)
    ap.add_argument("--retriever", default=check.RETRIEVER, choices=["tfidf", "embed"])
    ap.add_argument("--docs", default=rag.Settings.docs, choices=["pdf", "markdown"])
    ap.add_argument("--judge-model", default=JUDGE_MODEL)
    ap.add_argument("--run-name")
    ap.add_argument("--limit", type=int, help="only the first N records (quick test)")
    ap.add_argument("--retrieval-only", action="store_true")
    ap.add_argument("--no-judge", action="store_true")
    a = ap.parse_args()
    settings = rag.Settings(model=a.model, k=a.k, retriever=a.retriever, docs=a.docs)
    table, summary, counts = evaluate(settings, a.version, a.run_name, a.retrieval_only, not a.no_judge, a.judge_model, a.limit)
    pd.set_option("display.width", 200, "display.max_colwidth", 70)
    cols = [c for c in ["id", "expected", "error_type", "hit", "verdict", "faithfulness", "reason"] if c in table]
    print(table[cols].to_string(index=False))
    print()
    for k, (n, of) in counts.items():
        print(f"{k:42s} {n} of {of}")
    print("\nsummary:", {k: round(float(v), 3) for k, v in summary.items()})


if __name__ == "__main__":
    main()
