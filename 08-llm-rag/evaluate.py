"""Evaluate one version of the guideline assistant on a fixed question set, and log it to MLflow.

    python evaluate.py                                   # default settings, all questions
    python evaluate.py --model qwen/qwen3.5-9b --run-name "smaller model"
    python evaluate.py --k 2 --run-name "fewer passages"
    python evaluate.py --retrieval-only                  # no LLM at all: only checks the search step
    python evaluate.py --no-judge                        # answers + rule checks, skip the Ragas judge

Three layers of evaluation, cheapest first:
  1. **Retrieval** (no LLM): did the search return the page that holds the answer?
     hit@k and the rank of the first correct page.
  2. **Rules** (no LLM): checks a program can do on the answer: does it cite a passage? does it
     refuse out-of-scope questions, and only those? is an Amharic question answered in Amharic?
  3. **Ragas** (an LLM judge): faithfulness (is every claim supported by the passages?),
     context recall (do the passages contain what the reference answer needs?), and factual
     correctness against the reference answer. A judge is itself a model: check it against
     people's grades before trusting it (see README).

Answers are saved in results/ and reused when the same settings are run again, so a re-run costs
nothing and the discussion still works if the internet doesn't.
"""

import argparse
import asyncio
import hashlib
import json
import os
import re
from dataclasses import asdict
from pathlib import Path

import pandas as pd

os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")      # no usage telemetry from Ragas
os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")

import rag  # noqa: E402

HERE = Path(__file__).resolve().parent
QUESTIONS = HERE / "eval_questions.csv"
RESULTS = HERE / "results"
JUDGE_MODEL = "openai/gpt-oss-120b"        # open-weight; larger than the answering model on purpose
GEEZ = re.compile(r"[ሀ-፿]")      # Ethiopic script (Amharic)


def load_questions(path=QUESTIONS):
    q = pd.read_csv(path, dtype=str).fillna("")
    q["page_list"] = [[int(p) for p in s.split(";") if p.strip()] for s in q.pages]
    return q


# ---------------------------------------------------------------- 1. retrieval


def retrieval_checks(questions, retriever, k):
    """For each answerable question: is a passage from the right document and page among the top k?"""
    rows = []
    for q in questions.itertuples():
        hits = retriever.search(q.question, k)
        right = [(d == q.doc and p in q.page_list) for d, p in zip(hits.doc, hits.page)]
        rows.append({"id": q.id, "hit": any(right) if q.doc else None,
                     "first_right_rank": (right.index(True) + 1) if any(right) else None})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- answers (cached)


def run_key(settings, n_questions):
    blob = json.dumps(asdict(settings), sort_keys=True) + rag.PROMPTS[settings.prompt_version] + str(n_questions)
    return hashlib.md5(blob.encode()).hexdigest()[:10]


def get_answers(questions, retriever, settings):
    """Answer every question, or reuse saved answers from an identical earlier run."""
    RESULTS.mkdir(exist_ok=True)
    path = RESULTS / f"answers_{run_key(settings, len(questions))}.jsonl"
    if path.exists():
        print(f"reusing saved answers: {path.name}")
        return [json.loads(line) for line in path.read_text().splitlines()], path
    client, out = rag.llm_client(), []
    for i, q in enumerate(questions.itertuples(), 1):
        print(f"  answering {i}/{len(questions)}: {q.id}", flush=True)
        out.append(rag.answer(q.question, retriever, settings, client) | {"id": q.id})
    path.write_text("\n".join(json.dumps(a, ensure_ascii=False) for a in out))
    return out, path


# ---------------------------------------------------------------- 2. rules


def rule_checks(questions, answers):
    rows = []
    for q, a in zip(questions.itertuples(), answers):
        refused = rag.REFUSAL.lower().rstrip(".") in a["answer"].lower()
        rows.append({
            "id": q.id,
            "cites_a_passage": bool(re.search(r"\[\d+\]", a["answer"])) if q.type != "out_of_scope" else None,
            "refusal_correct": refused == (q.type == "out_of_scope"),   # refuses exactly when it should
            "answers_in_amharic": bool(GEEZ.search(a["answer"])) if q.type == "amharic" else None,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- 3. Ragas judge


async def ragas_scores(questions, answers, judge_model=JUDGE_MODEL, concurrency=4):
    from ragas.cache import DiskCacheBackend
    from ragas.llms import llm_factory
    from ragas.metrics.collections import ContextRecall, FactualCorrectness, Faithfulness

    # a hosted judge may reason before scoring (better judgements); a small local judge is too slow for that
    hosted = os.environ.get("LLM_BASE_URL", rag.OPENROUTER).startswith(rag.OPENROUTER)
    judge = llm_factory(judge_model, client=rag.llm_client(async_=True), cache=DiskCacheBackend(str(HERE / ".ragas_cache")),
                        temperature=0.0, max_tokens=4096, **({} if hosted else rag.thinking_switch(False)))
    metrics = {"faithfulness": Faithfulness(llm=judge), "context_recall": ContextRecall(llm=judge),
               "factual_correctness": FactualCorrectness(llm=judge)}
    gate = asyncio.Semaphore(concurrency)

    async def one(q, a):
        row = {"id": q.id}
        if q.type == "out_of_scope":          # nothing to judge: the rule check covers refusals
            return row
        inputs = {"faithfulness": dict(user_input=q.question, response=a["answer"], retrieved_contexts=a["contexts"]),
                  "context_recall": dict(user_input=q.question, retrieved_contexts=a["contexts"], reference=q.reference),
                  "factual_correctness": dict(response=a["answer"], reference=q.reference)}
        for name, metric in metrics.items():
            async with gate:
                try:
                    row[name] = (await metric.ascore(**inputs[name])).value
                except Exception as e:        # a judge can fail to produce valid output; record, don't crash
                    row[name] = None
                    row[f"{name}_error"] = f"{type(e).__name__}: {e}"[:200]
        return row

    return pd.DataFrame(await asyncio.gather(*[one(q, a) for q, a in zip(questions.itertuples(), answers)]))


# ---------------------------------------------------------------- run + log


def summarise(table):
    s = {}
    if "hit" in table:
        answerable = table[table.type != "out_of_scope"]
        s["retrieval_hit_rate"] = answerable.hit.astype(float).mean()
    for col in ["cites_a_passage", "refusal_correct", "answers_in_amharic",
                "faithfulness", "context_recall", "factual_correctness"]:
        if col in table and table[col].notna().any():
            s[col] = pd.to_numeric(table[col], errors="coerce").mean()
    return s


def evaluate(settings=rag.Settings(), run_name=None, retrieval_only=False, judge=True,
             judge_model=JUDGE_MODEL, limit=None, log=True):
    questions = load_questions()
    if limit:
        questions = questions.head(limit)
    retriever = rag.build(settings)
    table = questions[["id", "type", "question", "reference", "doc", "pages"]].merge(
        retrieval_checks(questions, retriever, settings.k), on="id")

    answers_file = None
    if not retrieval_only:
        answers, answers_file = get_answers(questions, retriever, settings)
        table["answer"] = [a["answer"] for a in answers]
        table["sources"] = ["; ".join(a["sources"]) for a in answers]
        table = table.merge(rule_checks(questions, answers), on="id")
        if judge:
            table = table.merge(asyncio.run(ragas_scores(questions, answers, judge_model)), on="id", how="left")

    summary = summarise(table)
    if log:
        import mlflow

        mlflow.set_experiment("guideline-assistant")
        with mlflow.start_run(run_name=run_name):
            mlflow.log_params(asdict(settings) | {
                "index_fingerprint": rag.fingerprint(retriever.passages),
                "n_questions": len(questions), "judge_model": judge_model if judge and not retrieval_only else "-",
                "retriever": "tfidf-1-2gram"})
            mlflow.log_text(rag.PROMPTS[settings.prompt_version], "prompt.txt")
            mlflow.log_metrics({k: float(v) for k, v in summary.items()})
            mlflow.log_table(table.astype(str), "per_question.json")
            if answers_file:
                mlflow.log_artifact(str(answers_file))
    return table, summary


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default=rag.Settings.model)
    ap.add_argument("--k", type=int, default=rag.Settings.k)
    ap.add_argument("--chunk-words", type=int, default=rag.Settings.chunk_words)
    ap.add_argument("--prompt", default=rag.Settings.prompt_version, choices=list(rag.PROMPTS))
    ap.add_argument("--judge-model", default=JUDGE_MODEL)
    ap.add_argument("--run-name")
    ap.add_argument("--limit", type=int, help="only the first N questions (quick test)")
    ap.add_argument("--retrieval-only", action="store_true")
    ap.add_argument("--no-judge", action="store_true")
    a = ap.parse_args()
    settings = rag.Settings(model=a.model, k=a.k, chunk_words=a.chunk_words, prompt_version=a.prompt)
    table, summary = evaluate(settings, a.run_name, a.retrieval_only, not a.no_judge, a.judge_model, a.limit)
    pd.set_option("display.width", 200, "display.max_colwidth", 60)
    cols = [c for c in ["id", "type", "hit", "first_right_rank", "cites_a_passage", "refusal_correct",
                        "faithfulness", "context_recall", "factual_correctness"] if c in table]
    print(table[cols].to_string(index=False))
    print("\nsummary:", {k: round(float(v), 3) for k, v in summary.items()})


if __name__ == "__main__":
    main()
