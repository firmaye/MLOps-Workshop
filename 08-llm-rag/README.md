# 08 – LLM use case: a guideline assistant and a prescription check, and how to evaluate them

> **Status: ready, pending clinical review.** Both halves run end to end on the hosted OpenRouter models;
> the facilitators' runs (21 Oct) are saved in `results/`, so every episode works without the key.
> `prescriptions.csv` and `eval_questions.csv` still need a clinician's review.

**Part A: the assistant.** A health worker or surveillance officer asks a question; the assistant finds the
relevant passages in Ethiopian public health guidelines and an LLM answers **from those passages
only**, citing them. This pattern is called retrieval-augmented generation (RAG). Are the answers good?

**Part B: the prescription check.** The same pipeline inside an EMR: given a record (age, weight, pregnancy,
diagnosis, prescription), retrieve the guideline and return correct / incorrect / not covered, with a reason and
a citation. Does it catch the errors?

```
question ──► retrieve k passages (keyword or embedding search over the guideline PDFs)
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
python check.py rx02                         # Part B: one prescription
python evaluate_check.py --version v2 --run-name "v2: LLM reads, Python counts"
mlflow ui                                    # experiments "guideline-assistant", "prescription-check"
```
`--search-only`, `--retrieval-only` and re-runs of the saved settings need no key. `--retriever embed` downloads
a 67 MB embedding model (`BAAI/bge-small-en-v1.5`, run on onnxruntime by `fastembed`; no PyTorch) and embeds
every passage once, about 5 minutes on a laptop; the vectors are cached in `index/`.

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

Settings are in `rag.Settings`: model, retriever, k, passage size, prompt version. Defaults:
answering model `google/gemma-4-26b-a4b-it`, judge `openai/gpt-oss-120b` (both open-weight, hosted
on OpenRouter). A 25-question run costs well under one US cent at current prices.

## Results: Part A

Key run (21 Oct), gemma-4-26b vs qwen3.5-9b: retrieval hit 77% both; cites a passage 73% / 95%; refusals
correct 21 / 22 of 26; Amharic in Amharic 1 / 0 of 2; faithfulness 0.66 / 0.80; context recall 0.67 / 0.67;
factual correctness 0.41 / 0.30. Details and examples in the lab guide (episode 3).

## Retrieval (no LLM needed)

Retrieval on the 22 answerable questions (keyword index, 200-word passages):

| Passages retrieved (k) | Right page found: all | English (20) | Amharic (2) |
|---|---|---|---|
| 2 | 15 of 22 (68%) | 75% | 0% |
| 5 (default) | 17 of 22 (77%) | 85% | 0% |
| 10 | 18 of 22 (82%) | 85% | 50% |
| 5, embedding search | 16 of 22 (73%) | 80% | 0% |

**Neither search finds Amharic questions in English documents.** The answer model never sees
the right passage, however good it is. The small embedding model is English-only; a multilingual one
(`google/embeddinggemma-300m`, 1.2 GB) ran out of memory on the 16 GB test machine. Fixes to compare in the
room: translate the question to English before searching, or a larger multilingual model.

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

## Part B: the prescription check (`check.py`, `evaluate_check.py`)

`prescriptions.csv`: **44 simulated records** (no real patients). 21 correct, 22 with one planted error (dose 5,
age band 5, contraindication 5, duration/frequency 4, pregnancy 3), 1 for a drug the guidelines don't cover
(malaria). Only conditions the guidelines dose explicitly: cholera (ORS and Ringer's lactate volumes,
doxycycline, azithromycin, zinc, no anti-emetics), acute malnutrition (amoxicillin, vitamin A, F-75, IV fluids,
albendazole), TB preventive therapy (isoniazid by weight). Every record carries the expected verdict, the error
type, and the document, page and verbatim quote it rests on; every quote was checked against the PDF text.
**The expected verdicts were written from the guideline text, not by a clinician: review before use.**

Two versions:
- **v1, the LLM decides:** record + passages in, verdict + reason out.
- **v2, the LLM reads, Python counts:** the LLM extracts the rule for this patient as JSON (amount, per kg, cap,
  interval, doses, duration, "do not give", verbatim quote). Python checks the quote is in the passages
  ("unsure" if not), then does the arithmetic and the comparison.

The search uses embeddings by default (`check.RETRIEVER`): an EMR record rarely uses the guideline's words.
Right page among 8 passages: embeddings 41 of 43, keywords 35 of 43.

Key runs (21 Oct, embedding search, k=8):

| | Errors caught | Correct passed | False alarms | Unsure | Confidently wrong | Faithfulness of reason |
|---|---|---|---|---|---|---|
| v1, gemma-4-26b | 15 of 22 | 15 of 21 | 6 | 0 | 13 of 44 | 0.63 |
| v2, gemma-4-26b | 12 of 22 | 13 of 21 | 2 | 13 | 5 of 44 | 0.24 |
| v2, qwen3.5-9b | 12 of 22 | 12 of 21 | 6 | 9 | 10 of 44 | 0.20 |

v2 is confidently wrong far less often, at the cost of 13 records for a person to check; most of those come from
dosing tables that the PDF text flattens. Faithfulness penalises v2 for stating Python's arithmetic, which no
passage contains: a metric that doesn't fit the system.

## The session

The walkthrough is [`LAB_GUIDE.md`](LAB_GUIDE.md), in two halves. Part A (episodes 0–3): it sounds right; the
search that can't read Amharic; reading the scores and checking the judge. Part B (episodes 4–8): does the search
find the rule; v1; v2; a cheaper model; the guidelines disagree. Each episode has a PAUSE; take-home exercises at
the end. Timing, what to say and fallbacks are in
[`FACILITATOR_NOTES.md`](FACILITATOR_NOTES.md).

**Hosted vs self-hosted:** the workshop uses hosted open-weight models with test questions. Real patient
information must never go to a hosted service: that is the reason to self-host. The code already supports it:
set `LLM_BASE_URL` to the self-hosted server's address.

## Files

| File | What |
|---|---|
| `LAB_GUIDE.md` | the participant walkthrough (episodes with PAUSEs, exercises) |
| `FACILITATOR_NOTES.md` | timing, what to say, expected output, fallbacks |
| `rag.py` | index, retrieve (keywords or embeddings), answer; CLI for single questions |
| `evaluate.py` | Part A: the three evaluation layers, MLflow logging; CLI |
| `eval_questions.csv` | Part A question set (draft, needs clinical review) |
| `check.py` | Part B: the prescription check, v1 and v2; CLI for one record |
| `evaluate_check.py` | Part B: sensitivity, specificity, per error type, faithfulness, MLflow logging; CLI |
| `prescriptions.csv` | Part B: 44 simulated records with expected verdicts and quotes (needs clinical review) |
| `results/` | the facilitators' saved answers, verdicts and per-record scores (reused on re-runs; the offline fallback) |
| `index/` | cached passages, embedding model and vectors (ignored by git) |

## Open items

- Clinical review of `prescriptions.csv` (records to check first are listed in the facilitator notes) and of
  `eval_questions.csv`; Amharic review of the two Amharic questions.
- A self-hosted server works too: `LLM_BASE_URL=http://<server>:11434/v1 LLM_API_KEY=anything`
  (tested with Ollama 0.40.5; on a 4-core CPU a 2B model took about 3 minutes per answer with 5 passages).
- Dosing tables as data (one row per weight or age band), so v2 doesn't depend on the PDF's flattened tables.
