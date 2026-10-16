# 08 – LLM use case: a guideline assistant, and how to evaluate it

> **Status: scaffold.** Every step runs end to end: retrieval, answering, rule checks, the Ragas
> judge and MLflow logging, tested with a small open-weight model (Qwen3.5 2B) on a local Ollama server
> through the same OpenAI-compatible API. Runs against the hosted OpenRouter models need the workshop
> key; their numbers come once it exists. The narrative below is the plan for the session.

**The use case.** A health worker or surveillance officer asks a question; the assistant finds the
relevant passages in Ethiopian public health guidelines and an LLM answers **from those passages
only**, citing them. This pattern is called retrieval-augmented generation (RAG).

```
question ──► retrieve k passages (keyword index over the guideline PDFs)
                     │
                     ▼
            LLM: answer only from these passages, cite [1] [2], or say "not covered"
                     │
                     ▼
            answer + citations ──► evaluation: retrieval · rules · Ragas judge ──► MLflow
```

## Setup

From the repo root, environment active:
```bash
python scripts/download.py guidelines        # the six guideline PDFs, from their official sites (26 MB)
cd 08-llm-rag
export OPENROUTER_API_KEY=...                # the shared workshop key (Windows: set OPENROUTER_API_KEY=...)
python rag.py "What is the community case definition of a suspected cholera case?"
python evaluate.py --run-name baseline
mlflow ui                                    # experiment "guideline-assistant"
```
`python rag.py "..." --search-only` and `python evaluate.py --retrieval-only` need no key.

## The guidelines

| Document | Publisher | Pages | Source |
|---|---|---|---|
| National Guideline for Cholera Surveillance and Outbreak Response (2022) | EPHI (PHEM) | 124 | ephi.gov.et |
| Emergency Nutrition Guideline (2022) | EPHI (PHEM) | 92 | ephi.gov.et |
| Climate-Sensitive Diseases Surveillance Manual (2022) | EPHI (PHEM) | 110 | ephi.gov.et |
| Community and Event-Based Surveillance Implementation Manual (2021) | EPHI (PHEM) | 50 | ephi.gov.et |
| National Guideline for the Management of Acute Malnutrition (2019) | Ministry of Health | 156 | copy hosted by the Global Nutrition Cluster |
| National Guidelines for TB, DR-TB and Leprosy, 6th ed. (2017) | Ministry of Health | 217 | copy hosted by WHO AFRO |

Exact URLs and checksums are in [`scripts/downloads.json`](../scripts/downloads.json). The PDFs are
downloaded from the publishers, not stored in this repository. The main PHEM guideline (2nd edition,
2023) is listed on EPHI's site but its page refuses requests from outside Ethiopia; add it to the
manifest from inside the country. Two documents link to the other demos: acute malnutrition (EMR)
and TB (chest X-ray).

## The evaluation framework (`evaluate.py`)

Three layers, cheapest first. Every run logs its settings, the prompt, the index fingerprint, the
scores and a per-question table to MLflow, so versions can be compared side by side.

| Layer | Needs an LLM? | Measures |
|---|---|---|
| Retrieval | no | hit@k: is the page holding the answer among the k passages? rank of the first right page |
| Rules | no | cites a passage; refuses out-of-scope questions (and only those); answers Amharic in Amharic |
| Ragas | yes (a judge model) | **faithfulness** (claims supported by the passages), **context recall** (passages contain what the reference needs), **factual correctness** (agrees with the reference answer) |

The question set (`eval_questions.csv`) holds answerable questions with reference answers, the
document and page, and a verbatim supporting quote; out-of-scope questions; and Amharic versions of
two questions. **It is a draft and needs review by a clinician or PHEM officer** before it is used as
ground truth in front of the room.

Settings are in `rag.Settings`: model, k, passage size, prompt version. Defaults:
answering model `google/gemma-4-26b-a4b-it`, judge `openai/gpt-oss-120b` (both open-weight, hosted
on OpenRouter). A 25-question run costs well under one US cent at current prices.

## Verified so far (no LLM needed)

Retrieval on the 22 answerable questions (keyword index, 200-word passages):

| Passages retrieved (k) | Right page found: all | English (20) | Amharic (2) |
|---|---|---|---|
| 2 | 15 of 22 (68%) | 75% | 0% |
| 5 (default) | 17 of 22 (77%) | 85% | 0% |
| 10 | 18 of 22 (82%) | 85% | 50% |

**Keyword search cannot find Amharic questions in English documents.** The answer model never sees
the right passage, however good it is. Fixes to compare in the room: translate the question to
English before searching, or a multilingual embedding retriever.

**Retrieval right, model wrong (local test, Qwen3.5 2B):** for the cholera-alert question the right
page was retrieved first, but the small model mixed up the alert definition and said the guideline gives
no reporting deadline (it says immediately, within 30 minutes). The judge scored it faithfulness 0.67,
factual correctness 0.33, context recall 1.0: the evaluation localises the fault to the model, not the
search. One question on a tiny model proves the plumbing, not the hosted models' quality.

**The guidelines contradict each other in places** (found while writing the question set):
- suspected cholera case: aged 2 years or more in the cholera guideline (p. 14), 5 years or more in
  the climate-sensitive diseases manual (p. 108) and the CEBS manual (p. 14);
- vitamin A for eye signs in severe malnutrition: day 2 and day 14 in the emergency nutrition
  guideline (p. 81), days 1, 2 and 15 in the acute malnutrition guideline (p. 19).

An assistant that retrieves from both will sometimes answer from the "wrong" one. Which document
wins is a decision for the programme, not the model (newest? most specific?), and it belongs in the
prompt or the index, versioned like everything else.

## Planned narrative (six beats)

1. **Setting:** a surveillance officer during a cholera outbreak, a nurse managing acute malnutrition.
2. **First version:** keyword retrieval + an open-weight model. Ask it a few questions live; it sounds right.
3. **Twists** (each one is a re-run of `evaluate.py` with one setting changed):
   - **Retrieval misses.** Questions phrased in the health worker's words, not the guideline's,
     retrieve the wrong page. The answer stays fluent and even "faithful" (to the wrong passage).
     Only the retrieval layer shows the cause. → evaluate retrieval separately; try a better retriever.
   - **A cheaper model.** Swap in a smaller model: the averages move a little, but specific
     questions (doses, cut-offs) change. → the evaluation set as a regression test; compare per question.
   - **Out of scope and Amharic.** Does it refuse what the guidelines don't cover? Does it answer
     Amharic questions, and in Amharic? → rule checks, per-language results.
   - **Guidelines disagree.** Ask the cholera age question; see which document the answer comes from.
   - **A guideline is updated.** The index fingerprint changes; every earlier score is now about a
     different system. → version the documents (DVC), re-run the evaluation.
4. **Detect:** the MLflow comparison view, per-question tables, the three layers side by side.
5. **Respond:** a promotion rule for assistant versions, written before looking (e.g. no drop in
   retrieval hit rate, faithfulness ≥ 0.9, every refusal correct, no answerable question newly wrong).
6. **Lesson:** an LLM application is a pipeline of versioned parts (documents, index, prompt,
   model); each change needs the same evaluation, and the judge needs checking too.

**Judge check (exercise for the room):** everyone grades 10 answers as correct / partly / wrong;
compare with Ragas' factual-correctness scores. Where they disagree, who is right?

**Hosted vs self-hosted:** the workshop uses hosted open-weight models with mock questions. Real
patient information must never go to a hosted service: that is the reason to self-host. The code
already supports it: set `LLM_BASE_URL` to the self-hosted server's address.

## Files

| File | What |
|---|---|
| `rag.py` | index, retrieve, answer; CLI for single questions |
| `evaluate.py` | the three evaluation layers, MLflow logging; CLI |
| `eval_questions.csv` | the question set (draft, needs clinical review) |
| `results/` | saved answers per settings (reused on re-runs; ignored by git) |
| `index/` | cached passages (ignored by git) |

## Open items

- OpenRouter key: buy credit, set a spending cap, run `evaluate.py` with the default and a smaller
  model, and fill the numbers into this README. Check that OpenRouter accepts the "thinking off"
  switch (`reasoning: {enabled: false}`, taken from third-party sources) for the chosen models.
- A self-hosted server works too: `LLM_BASE_URL=http://<server>:11434/v1 LLM_API_KEY=anything`
  (tested with Ollama 0.40.5; on a 4-core CPU a 2B model took about 3 minutes per answer with 5 passages).
- Clinical review of the question set.
- Optional: a notebook version of the narrative for the session; a dense (embedding) retriever as
  the fix for the retrieval twist.
