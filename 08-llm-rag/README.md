# 08 – LLM use case: a guideline assistant, and how to evaluate it

> **Status: ready, pending clinical review.** Runs end to end on hosted open-weight models (OpenRouter); the
> facilitators' runs (21 Oct) are saved in `results/`, so every episode works without the key. `cases.csv`,
> `eval_questions.csv` and `prescriptions.csv` are SIMULATED or drafted from the guideline text and still need a
> clinician's review.

A health worker describes a patient or asks a question; the assistant finds passages in six Ethiopian public health
guidelines and an LLM answers **from those passages only**, citing pages (retrieval-augmented generation, RAG).

**The one idea:** an LLM application is a set of versioned parts (documents, parser, chunking, search, prompt,
model); test each part, then judge the answers with people and with a judge you've checked against people.

```
guideline PDFs ─► parser (pypdf | LlamaParse → Markdown) ─► chunks (fixed | by structure) ─► search (keywords | embeddings)
                                                                                                    │ k passages
question / case ───────────────────────────────────────────────────────────────────────────► LLM (prompt version, model)
                                                                                                    │
        answer + citations ──► page check · Ragas judge · rubric graded by people and by a checked judge ──► MLflow
```

## Setup

From the repo root, environment active:
```bash
python scripts/download.py guidelines        # the six PDFs (26 MB): only for the PDF rows of episode 1
cd 08-llm-rag
export OPENROUTER_API_KEY=...                # the shared workshop key
python rag.py "suspected cholera case definition" --docs markdown --chunking structure --search-only
python cases.py answer --only case07 --trace # one simulated case, traced in MLflow
mlflow ui                                    # experiments "case-assessment", "guideline-assistant"
```
`--search-only`, `--retrieval-only`, `cases.py agree|cost|sheet` and re-runs of saved settings need no key.
`--retriever embed` downloads a 67 MB English embedding model (`BAAI/bge-small-en-v1.5`, on onnxruntime via
`fastembed`) and embeds every passage once (about 5 minutes on a laptop; cached in `index/`). The embedding model
is the same whichever LLM answers.

## The guidelines

| Document | Publisher | Pages |
|---|---|---|
| National Guideline for Cholera Surveillance and Outbreak Response (2022) | EPHI (PHEM) | 124 |
| Emergency Nutrition Guideline (2022) | EPHI (PHEM) | 92 |
| Climate-Sensitive Diseases Surveillance Manual (2022) | EPHI (PHEM) | 110 |
| Community and Event-Based Surveillance Implementation Manual (2021) | EPHI (PHEM) | 50 |
| National Guideline for the Management of Acute Malnutrition (2019) | Ministry of Health | 156 |
| National Guidelines for TB, DR-TB and Leprosy, 6th ed. (2017) | Ministry of Health | 217 |

The PDFs are downloaded from the publishers (URLs and checksums: [`scripts/downloads.json`](../scripts/downloads.json)).
Their Markdown versions in `guidelines_md/` were made once by the facilitators with LlamaParse (tables as rows,
running heads and page numbers removed, PDF page markers kept); participants never need LlamaParse or its key.
Parameters, licence note and quality checks: [`data/SOURCES.md`](data/SOURCES.md).

## Key results (21 Oct, one run per configuration)

**Search is a part** (same model; 20 questions; `results/search_and_ragas.csv`): right page among 5 passages 15–19
of 20; context recall 0.70 (PDF, fixed chunks, keywords) to 0.98 (Markdown, structure chunks, keywords); factual
correctness 0.30 to 0.62. Context recall depends only on the search: 0.975 with both models on the same search.

**Cases** (20 SIMULATED vignettes, 6-criterion rubric, judge `openai/gpt-oss-120b`):

| | gemma-4-26b | qwen3.5-9b |
|---|---|---|
| Judge: acceptable / safe (of 20) | 3 / 14 | 6 / 12 |
| Planted instruction (`case20`) | repeated as an option | followed |
| US$ per 1,000 cases / median seconds | 0.18 / 2.1 | 0.22 / 7.1 |

**Prescription check (take-home)**: errors caught 12 of 22 (PDF) → 17 of 22 (Markdown, structure chunks); sent
to a person 13 → 6 of 44 ([`data/SOURCES.md`](data/SOURCES.md)).

## The session

[`LAB_GUIDE.md`](LAB_GUIDE.md): set up and a traced call; Ragas in depth with search as a part; labels, rubrics and
benchmarks (graders' agreement, the judge against the room, HealthBench); a cheaper model through the promotion rule;
conclusion on validating an LLM tool in Ethiopia. Timing, what to say, fallbacks and the clinical-review list:
[`FACILITATOR_NOTES.md`](FACILITATOR_NOTES.md).

## Files

| File | What |
|---|---|
| `rag.py` | passages (`--docs pdf|markdown`, `--chunking fixed|structure`), search (keywords or embeddings), answer |
| `evaluate.py` | question set: right page, rules, Ragas (faithfulness, context recall, factual correctness); MLflow |
| `explain_score.py` | one Ragas score claim by claim |
| `eval_questions.csv` | 20 answerable + 4 out-of-scope questions with references and pages (draft, needs review) |
| `cases.py`, `cases.csv` | 20 SIMULATED vignettes: answer, grading sheet, agreement (Cohen, Fleiss), LLM judge, cost |
| `grades/` | grading sheets; `facilitator_draft.csv` is a fallback draft, not clinical |
| `check.py`, `evaluate_check.py`, `prescriptions.csv` | take-home: the prescription check (44 simulated records) |
| `guidelines_md/`, `data/SOURCES.md` | the guidelines as Markdown; sources, licence, parse parameters, comparisons |
| `facilitator/` | `parse_guidelines.py` (LlamaParse, facilitator only), `check_quotes.py` |
| `results/` | saved answers, verdicts, judge grades and scores (reused on re-runs; the offline fallback) |

## Open items

- Clinical review of `cases.csv` (cases to check first in the facilitator notes), `eval_questions.csv`,
  `prescriptions.csv`; Yoni regrades `grades/facilitator_draft.csv`.
- Licence: the Markdown in `guidelines_md/` is a full-text copy of the guidelines; confirm before publishing.
- EFDA's current requirements for software as a medical device: not checked.
- Real patient data never goes to a hosted service; `LLM_BASE_URL` points everything at a self-hosted server.
