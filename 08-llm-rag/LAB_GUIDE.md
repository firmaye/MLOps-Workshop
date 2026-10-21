# LLM guideline assistant: lab guide

Thursday 29 October, 13:30–16:30. A health worker asks a question; the assistant finds passages in Ethiopian
public health guidelines and an open-weight LLM answers from them, citing pages. Today is about how you know
whether it works, and what happens each time you change one of its parts.

Every episode has the same shape: **do the obvious thing → see the problem → PAUSE: what would you do? → the
fix → check it.** At each **PAUSE**, write your answer down (2–5 minutes) before reading on.

Numbers marked ✓ were verified on the committed code. Numbers marked *(key)* come from the facilitators' run with
the workshop's OpenRouter key (21 Oct); the answers and per-question scores are saved in `results/`.

| # | Episode | Time | Needs the key? |
|---|---|---|---|
| 0 | Set up | 10 min | no |
| 1 | It sounds right | 15 min | yes |
| 2 | The search that can't read Amharic | 20 min | no |
| 3 | Three layers of evaluation | 30 min | yes |
| 4 | A cheaper model | 25 min | yes |
| 5 | The guidelines disagree | 15 min | no (search) / yes (answer) |
| 6 | A guideline changes | 15 min | no |
| 7 | Can we trust the judge? *(exercise)* | 20 min | yes |

---

## Episode 0. Set up (10 min)

From the repo root, environment active:
```bash
python scripts/download.py guidelines     # six PDFs from EPHI and the Ministry of Health (26 MB)
cd 08-llm-rag
export OPENROUTER_API_KEY=...             # the shared workshop key (Windows PowerShell: $env:OPENROUTER_API_KEY="...")
python rag.py "What is the community case definition of a suspected cholera case?" --search-only
```
Expected: five passages, the first from the cholera guideline, page 14 ✓. The first run builds the index
(about 25 seconds); later runs reuse it.

## Episode 1. It sounds right (15 min)

Ask a few questions, with and without `--search-only`:
```bash
python rag.py "A child in the outpatient therapeutic programme still hasn't met the cure criteria. How long do we continue?"
python rag.py "What isoniazid dose should I prescribe for TB preventive therapy in adults?"
python rag.py "What is the first-line treatment for uncomplicated falciparum malaria?"
```
The answers are fluent, cite passages, and sound like a guideline. The third question is not covered by any of
the six documents: does the assistant say so?

> **PAUSE.** You have to tell the Ministry whether this assistant is good enough for a pilot. What would you
> need to measure, and on what?

## Episode 2. The search that can't read Amharic (20 min)

The cheapest evaluation needs no LLM at all: did the search return the page that holds the answer?
```bash
python evaluate.py --retrieval-only --run-name "retrieval, k=5"
```
`eval_questions.csv` has 22 answerable questions with the document and page of each answer (20 English, 2
Amharic), plus 4 out-of-scope questions. Expected ✓:

| Passages retrieved | All 22 | English (20) | Amharic (2) |
|---|---|---|---|
| k = 5 | 77% | 85% | **0%** |
| k = 10 (`--k 10`) | 82% | 85% | 50% |
| k = 5, shorter passages (`--chunk-words 120`) | 73% | | |

> **PAUSE.** The right page never reaches the model for the Amharic questions. Why? What would you change?

The index matches words, and the guidelines are in English: Ge'ez script shares no words with them. Fixes to
discuss: translate the question to English before searching; a multilingual embedding retriever; Amharic
versions of the guidelines. Whatever you choose, **evaluate retrieval separately**: no answer model can fix a
passage it never sees.

## Episode 3. Three layers of evaluation (30 min)

```bash
python evaluate.py --run-name baseline
mlflow ui          # open http://127.0.0.1:5000, experiment "guideline-assistant"
```
Each run scores every question three ways:

| Layer | Needs an LLM? | Checks |
|---|---|---|
| Retrieval | no | the right page among the passages |
| Rules | no | cites a passage; refuses exactly the out-of-scope questions; answers Amharic in Amharic |
| Ragas (an LLM judge) | yes | faithfulness to the passages; context recall; factual correctness against the reference answer |

Expected *(key)*: a per-question table in MLflow (`per_question.json`), and these summary scores:

| Retrieval hit | Cites a passage | Refusal correct | Amharic in Amharic | Faithfulness | Context recall | Factual correctness |
|---|---|---|---|---|---|---|
| 77% | 73% | 21 of 26 | 1 of 2 | 0.66 | 0.67 | 0.41 |

The five wrong refusals are answerable questions the model declined: four whose page was never retrieved
(`sam_01`, `sam_02`, `csd_03`, `chol_02_am`) and one whose page was (`tb_01`).

> **PAUSE.** Find a question where faithfulness is high but factual correctness is low. What does that
> combination tell you, and which part of the system is at fault?

High faithfulness with low correctness means the model faithfully repeated the wrong passages: a retrieval
fault. Low faithfulness with good retrieval means the model added things: a generation fault. This is why the
layers are scored separately. (In the facilitators' local test with a 2B model: right page retrieved, wrong
answer, factual correctness 0.33 ✓.)

In the key run *(key)*: `nutr_01` (12% acute malnutrition): right page at rank 1, faithfulness 1.0, factual
correctness 0.00. The model misread the benchmark table and said it lists no interventions for 10–14% without
aggravating factors. Wrong reading of the right passage, and the judge still called it faithful. Check `hit`
before blaming retrieval.

## Episode 4. A cheaper model (25 min)

The smaller model is cheaper and faster. Before running it:

> **PAUSE.** Write your promotion rule now, before you see any results. What must the new version not make
> worse?

A starting point: retrieval hit rate unchanged; every refusal still correct; faithfulness ≥ 0.9; **no
answerable question newly wrong**. Then:
```bash
python evaluate.py --model qwen/qwen3.5-9b --run-name "smaller model"
```
Compare the two runs in MLflow, then the per-question tables. Expected *(key)*:

| Run | Retrieval hit | Cites a passage | Refusal correct | Amharic in Amharic | Faithfulness | Context recall | Factual correctness |
|---|---|---|---|---|---|---|---|
| baseline (gemma-4-26b) | 77% | 73% | 21 of 26 | 1 of 2 | 0.66 | 0.67 | 0.41 |
| smaller model (qwen3.5-9b) | 77% | 95% | 22 of 26 | 0 of 2 | 0.80 | 0.67 | 0.30 |

Averages move in both directions. One answer that changed: `nutr_01` (12% acute malnutrition, no aggravating
factors). The baseline says the benchmarks list no intervention; the smaller model gives the right one (targeted
supplementary feeding, therapeutic feeding, no general ration). Factual correctness 0.00 → 0.50. Apply your rule.
Would you promote it?

With the starting rule *(key)*: **no**. Retrieval is unchanged, but faithfulness is 0.80 (< 0.9), Amharic drops
from 1 of 2 to 0 of 2, and the rule check counts 3 of 4 out-of-scope questions as not refused. Read those three:
the model does refuse, in its own words ("The provided guidelines do not cover…"). The rule matches one exact
sentence. A rule check can be wrong too. (The baseline doesn't reach faithfulness 0.9 either.)

## Episode 5. The guidelines disagree (15 min)

```bash
python rag.py "From what age is a person with acute watery diarrhoea counted as a suspected cholera case?" --search-only
```
Expected ✓: passages from **three** documents: the cholera guideline (page 14: aged 2 years or more), the
climate-sensitive diseases manual (page 108) and the community surveillance manual (page 14), which use 5 years.
Now ask it without `--search-only`: which age does the answer give, and which document does it cite?

> **PAUSE.** Which document should win? Who decides, and where should that decision live in the system?

This is not a model problem. The programme decides (newest? most specific? the PHEM guideline?), and the
decision goes into the prompt or the document set, versioned and evaluated like everything else.

## Episode 6. A guideline changes (15 min)

Every evaluation run logs an **index fingerprint**: a hash of exactly which text was indexed. Change anything
that feeds the index and it changes:
```bash
python evaluate.py --retrieval-only --chunk-words 120 --run-name "shorter passages"
```
Expected ✓: a new fingerprint in MLflow, and the hit rate drops from 77% to 73%.

> **PAUSE.** EPHI publishes a new edition of the cholera guideline. List everything you must re-run or
> re-check before the updated assistant goes live.

Documents, index, prompt and model are all versioned parts. A change to any one of them is a new version of the
system, and gets the same evaluation as the first.

## Episode 7. Can we trust the judge? (exercise, 20 min)

Ragas' scores come from another LLM. Pick 10 answers from the baseline run (in MLflow or `results/`). Grade each
yourself: correct, partly correct, or wrong. Then compare with the `factual_correctness` column.

> **PAUSE.** Where do you and the judge disagree? Who is right? Would you use the judge's scores to promote a
> model?

A judge must be checked against people's grades on a sample before its scores are trusted, and re-checked
whenever the judge model changes.

From the key run *(key)*: `csd_01` repeats the reference word for word and gets factual correctness 0.00 in both
runs. `cebs_02` gets 1.0 for the baseline and 0.00 for the smaller model, though both answers say the same thing.
Three of 132 judge calls hit the output limit and have no score.

---

## Exercises (take-home)

1. **Translate, then search.** Add a step that translates Amharic questions to English (with the same LLM)
   before retrieval. Re-run episode 2: does the Amharic hit rate improve?
2. **A better retriever.** Replace the TF-IDF `Retriever` in `rag.py` with an embedding model. Compare hit rates.
3. **Settle the conflict.** Write prompt `v2` in `rag.PROMPTS` that tells the model which document takes
   precedence. Re-run the evaluation; did anything else change?
4. **More questions.** Add five questions from your own work to `eval_questions.csv`, with the page and a
   verbatim quote. Which layer fails first?
5. **Self-hosted.** Point the assistant at a self-hosted server: `LLM_BASE_URL=http://<server>:11434/v1`
   (Ollama or vLLM) and `LLM_API_KEY=anything`. Nothing else changes.
