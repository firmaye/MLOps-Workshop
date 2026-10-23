"""Open up one Ragas score: the claims the judge extracted and its verdict on each.

    python explain_score.py results/answers_<key>.jsonl nutr_01      # faithfulness and context recall, claim by claim

Faithfulness: the judge splits the ANSWER into claims and asks, for each, "can it be inferred from the passages?";
score = supported claims / all claims. Context recall: the judge splits the REFERENCE answer into claims and asks,
for each, "is it in the passages?"; score = found claims / all claims. Same judge and cache as evaluate.py, so a
score already computed there costs nothing here.
"""

import argparse
import asyncio
import json
import os

os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")

import evaluate  # noqa: E402
import rag  # noqa: E402


async def explain(answers_file, qid, judge_model=evaluate.JUDGE_MODEL):
    from ragas.cache import DiskCacheBackend
    from ragas.llms import llm_factory
    from ragas.metrics.collections import ContextRecall, Faithfulness
    from ragas.metrics.collections.context_recall.util import ContextRecallInput, ContextRecallOutput

    a = next(x for x in map(json.loads, open(answers_file)) if x["id"] == qid)
    q = evaluate.load_questions().set_index("id").loc[qid]
    judge = llm_factory(judge_model, client=rag.llm_client(async_=True), temperature=0.0, max_tokens=4096,
                        cache=DiskCacheBackend(str(rag.HERE / ".ragas_cache")))
    print(f"QUESTION  {q.question}\nANSWER    {a['answer']}\nREFERENCE {q.reference}\n")

    f = Faithfulness(llm=judge)
    claims = await f._create_statements(q.question, a["answer"])
    verdicts = await f._create_verdicts(claims, "\n".join(a["contexts"]))
    print("FAITHFULNESS: claims in the answer, each checked against the passages")
    for v in verdicts.statements:
        print(f"  {'supported  ' if v.verdict else 'UNSUPPORTED'}  {v.statement}\n               judge: {v.reason}")
    ok = sum(v.verdict for v in verdicts.statements)
    print(f"  score = {ok}/{len(verdicts.statements)}\n")

    r = ContextRecall(llm=judge)
    prompt = r.prompt.to_string(ContextRecallInput(question=q.question, context="\n".join(a["contexts"]),
                                                   answer=q.reference))
    out = await judge.agenerate(prompt, ContextRecallOutput)
    print("CONTEXT RECALL: claims in the reference answer, each looked for in the passages")
    for c in out.classifications:
        print(f"  {'found    ' if c.attributed else 'NOT FOUND'}  {c.statement}\n             judge: {c.reason}")
    found = sum(c.attributed for c in out.classifications)
    print(f"  score = {found}/{len(out.classifications)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("answers_file")
    ap.add_argument("question_id")
    ap.add_argument("--judge-model", default=evaluate.JUDGE_MODEL)
    a = ap.parse_args()
    asyncio.run(explain(a.answers_file, a.question_id, a.judge_model))


if __name__ == "__main__":
    main()
