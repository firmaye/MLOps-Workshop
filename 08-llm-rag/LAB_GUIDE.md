# LLM guideline assistant: lab guide

Thursday 29 October, 13:30–16:30. One pipeline, two halves. **Part A:** a health worker asks a question; the
assistant finds passages in Ethiopian public health guidelines and an open-weight LLM answers from them, citing
pages. Are the answers good? **Part B:** the same pipeline inside an EMR checks a prescription against the
guidelines. Does it catch the errors?

Every episode has the same shape: **do the obvious thing → see the problem → PAUSE: what would you do? → the
fix → check it.** At each **PAUSE**, write your answer down (2–5 minutes) before reading on.

Numbers marked ✓ were verified on the committed code without the key. Numbers marked *(key)* come from the
facilitators' runs with the workshop's OpenRouter key (21 Oct); the answers, verdicts and per-record scores are
saved in `results/`, so re-running with the same settings is instant and needs no key.

| Part | # | Episode | Time | Needs the key? |
|---|---|---|---|---|
| A | 0 | Set up | 10 min | no |
| A | 1 | It sounds right | 10 min | yes |
| A | 2 | The search that can't read Amharic | 15 min | no |
| A | 3 | Reading the scores, and checking the judge | 30 min | no (saved scores) |
| B | 4 | Does the search find the rule? | 10 min | no |
| B | 5 | The LLM decides everything (v1) | 15 min | no (saved run) |
| B | 6 | The LLM reads, Python counts (v2) | 20 min | no (saved run) |
| B | 7 | A cheaper model | 15 min | no (saved run) |
| B | 8 | The guidelines disagree | 5 min | no |

---

# Part A. Evaluating a RAG system

## Episode 0. Set up (10 min)

From the repo root, environment active:
```bash
python scripts/download.py guidelines     # six PDFs from EPHI and the Ministry of Health (26 MB)
cd 08-llm-rag
export OPENROUTER_API_KEY=...             # the shared workshop key (Windows PowerShell: $env:OPENROUTER_API_KEY="...")
python rag.py "What is the community case definition of a suspected cholera case?" --search-only
python rag.py "cholera" --search-only --retriever embed     # start now: Part B needs it (first run: a few minutes)
```
Expected: five passages, the first from the cholera guideline, page 14 ✓. The first run builds the keyword index
(about 25 seconds). The second downloads a small embedding model (67 MB) and embeds every passage once (about 5
minutes on a laptop); leave it running.

## Episode 1. It sounds right (10 min)

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

## Episode 2. The search that can't read Amharic (15 min)

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
| k = 5, embedding search (`--retriever embed`) | 73% | 80% | **0%** |

> **PAUSE.** The right page never reaches the model for the Amharic questions. Why? What would you change?

The keyword index matches words, and the guidelines are in English: Ge'ez script shares no words with them. The
embedding search matches meaning, but the small model we can ship is English-only, so it fails too. Fixes to
discuss: translate the question to English before searching; a multilingual embedding model (larger: about 1 GB);
Amharic versions of the guidelines. Whatever you choose, **evaluate retrieval separately**: no answer model can
fix a passage it never sees.

## Episode 3. Reading the scores, and checking the judge (30 min)

```bash
python evaluate.py --run-name baseline          # reuses the saved answers; the judge re-scores them (needs the key)
mlflow ui          # open http://127.0.0.1:5000, experiment "guideline-assistant"
```
No key, or the API is down: every score is in `results/per_question_baseline.csv`.
Each run scores every question three ways:

| Layer | Needs an LLM? | Checks |
|---|---|---|
| Retrieval | no | the right page among the passages |
| Rules | no | cites a passage; refuses exactly the out-of-scope questions; answers Amharic in Amharic |
| Ragas (an LLM judge) | yes | the three scores below |

What each Ragas score computes (the judge is `openai/gpt-oss-120b`, a larger open-weight model):

| Score | The judge… | Low means |
|---|---|---|
| Faithfulness | splits the answer into claims, checks each against the retrieved passages; score = share supported | the model added things the passages don't say |
| Context recall | splits the *reference* answer into claims, checks each against the passages | the search missed what the answer needs |
| Factual correctness | compares the answer's claims with the reference answer's, both ways | the answer is wrong or incomplete |

Expected *(key)*, baseline (gemma-4-26b):

| Retrieval hit | Cites a passage | Refusal correct | Amharic in Amharic | Faithfulness | Context recall | Factual correctness |
|---|---|---|---|---|---|---|
| 77% | 73% | 21 of 26 | 1 of 2 | 0.66 | 0.67 | 0.41 |

Read them together. Context recall low → look at the search first. Recall high, faithfulness high, correctness
low → the model read the right passage wrongly, or the judge is wrong. `nutr_01` *(key)*: right page at rank 1,
faithfulness 1.0, factual correctness 0.00: the model misread the benchmark table and said it lists no
interventions for 10–14% acute malnutrition without aggravating factors. The five wrong refusals are answerable
questions the model declined: four whose page was never retrieved (`sam_01`, `sam_02`, `csd_03`, `chol_02_am`)
and one whose page was (`tb_01`).

**The judge is a model too.** In pairs, open `results/per_question_baseline.csv` and grade these five answers
yourself (correct / partly / wrong) against the reference: `csd_01`, `cebs_02`, `nutr_01`, `nutr_02`, `chol_03`.
Then compare with `factual_correctness`.

> **PAUSE.** Where do you and the judge disagree? Who is right? Would you use its scores to promote a model?

*(key)*: `csd_01` repeats the reference word for word and gets factual correctness 0.00. `cebs_02` gets 1.0 for
the baseline and 0.00 for the smaller model, though both answers say the same thing. A judge must be checked
against people's grades on a sample before its scores are trusted, and re-checked whenever it changes.

---

# Part B. A prescription check inside an EMR

Same pipeline, different question once it sits in a workflow: not "are the answers good?" but **"does it catch
the errors?"** The EMR sends a record (sex, age, weight, pregnancy, diagnosis, other conditions, the
prescription); the check retrieves guideline passages and returns **correct / incorrect / not covered**, a
reason and a citation.

`prescriptions.csv` holds **44 simulated records** (no real patients): 21 correct, 22 with a planted error, 1 for a
drug the guidelines don't cover. Errors by type: dose 5, age band 5, contraindication 5, duration/frequency 4,
pregnancy 3. Every record carries the expected verdict and the guideline page and verbatim quote it rests on
(each quote checked against the PDF text ✓). Conditions: cholera (rehydration, antibiotics, zinc), severe and
moderate acute malnutrition (amoxicillin, vitamin A, F-75, IV fluids, albendazole), TB preventive therapy
(isoniazid by weight).

```bash
python check.py rx02 --version v1          # one record: verdict, reason, and what was expected
```

## Episode 4. Does the search find the rule? (10 min)

Evaluate the search first, as in episode 2. Here the query is what the EMR knows: drug, diagnosis, other
conditions.
```bash
python evaluate_check.py --retrieval-only --retriever tfidf --run-name "retrieval, keywords"
python evaluate_check.py --retrieval-only --run-name "retrieval, embedding"
```
Expected ✓ (the right page among the passages, 43 records with a rule):

| | k = 5 | k = 8 (default for the check) |
|---|---|---|
| Keyword search | 33 of 43 | 35 of 43 |
| Embedding search | 36 of 43 | **41 of 43** |

> **PAUSE.** In Part A keywords were as good as embeddings. Why not here?

A question in Part A is written in words like the guideline's. An EMR record isn't: "SAM without medical
complications (OTP)" and amoxicillin, against a table headed "Routine Medication and Treatment in OTP". Embeddings
match meaning, so the record doesn't have to use the guideline's words. Keywords still win on rare exact terms
(drug names), which is why production systems often combine both.

## Episode 5. The LLM decides everything (v1) (15 min)

The obvious version: patient, prescription and passages go to the LLM; it returns the verdict and the reason.
```bash
python evaluate_check.py --version v1 --run-name "v1: LLM decides" --no-judge
```
Two numbers matter, and they pull in opposite directions:
- **Sensitivity:** of the prescriptions with an error, how many does it flag?
- **Specificity:** of the correct ones, how many does it pass? Every false alarm costs a clinician's time, and too
  many teach people to ignore the check.

With 44 records, one record moves a percentage by 2–5 points: **say counts**. Expected *(key)*, gemma-4-26b:

| Errors caught | Correct passed | False alarms | Dose | Age band | Pregnancy | Duration/frequency | Contraindication |
|---|---|---|---|---|---|---|---|
| 15 of 22 | 15 of 21 | 6 of 21 | 2 of 5 | 2 of 5 | 3 of 3 | 4 of 4 | 4 of 5 |

Now read the misses in `results/check_v1_llm_decides.csv`:
- `rx20`: amoxicillin 125 mg for a 12 kg child. Verdict **correct**; the reason then works out 25 mg/kg × 12 kg =
  300 mg and calls 125 mg under-dosing. The verdict came first, the arithmetic after.
- `rx38`: isoniazid 150 mg for a 9 kg child. Verdict correct: "for a 9 kg child the required dose is 150 mg". The
  table says 100 mg for 5.1–9.9 kg; the model misread a weight band.
- `rx03`, `rx07`: correct doses (3.3 mg/kg doxycycline, 20 mg/kg azithromycin) flagged as wrong.

> **PAUSE.** The model reads the guideline well (it caught every pregnancy and duration error) and counts badly.
> How would you change the design, not the prompt?

## Episode 6. The LLM reads, Python counts (v2) (20 min)

Split the work. The LLM only extracts the rule that applies to this patient, as JSON: amount (per kg or
fixed), cap, interval, number of doses, duration, "do not give", and a **verbatim quote**. Python then:
1. checks the quote is really in the passages (and the amounts in the cited passage). If not: **unsure**, a
   person looks;
2. does the arithmetic (mg/kg × weight, the cap) and compares the prescription field by field.
```bash
python check.py rx20                       # v2 is the default
python evaluate_check.py --version v2 --run-name "v2: LLM reads, Python counts" --no-judge
```
Expected *(key)*:

| | Errors caught | Correct passed | False alarms | Unsure (to a person) | Wrong, and said so confidently |
|---|---|---|---|---|---|
| v1 | 15 of 22 | 15 of 21 | 6 | 0 | **13 of 44** |
| v2 | 12 of 22 | 13 of 21 | 2 | 13 | **5 of 44** |

v2 catches fewer errors outright. But it is confidently wrong in 5 records instead of 13, and false alarms drop from
6 to 2: when it can't verify a rule, it says so. `rx20` is now "125 mg (10.4 mg/kg) prescribed; the rule gives 300
mg for 12 kg". `rx38` is now unsure: the model quoted a table row ("< 5 50") that isn't in the text, because the
PDF table comes out flattened (all weight bands, then all doses).

> **PAUSE.** Which version would you put in front of a nurse? What would you do about the 13 "unsure"?

Most "unsure" records come from flattened tables (isoniazid by weight, Plan C fluids). The fix is in the
documents, not the model: extract tables as rows, or write the dosing tables as data once, reviewed by a
clinician, and let the LLM only find which row applies.

**Faithfulness doesn't fit v2.** With the judge on, v1 reasons score 0.63 and v2 reasons 0.24 *(key)*. v2's
reasons contain Python's arithmetic ("300 mg for 12 kg"), which no passage states, so the judge calls them
unsupported. Choose metrics that fit the system.

## Episode 7. A cheaper model (15 min)

> **PAUSE.** Write your promotion rule now, before you see any results. What must the cheaper model not make
> worse?

A starting point: no more confidently wrong verdicts than v2 (5); no more false alarms (2); errors caught not
lower (12 of 22). Then:
```bash
python evaluate_check.py --version v2 --model qwen/qwen3.5-9b --run-name "v2, smaller model" --no-judge
```
Expected *(key)*: errors caught 12 of 22; correct passed 12 of 21; false alarms **6**; unsure 9; confidently
wrong **10 of 44**. The rule fails: it would not be promoted. Same averages for caught errors, different errors:
`rx32` (albendazole in the first trimester) passed; `rx37` (a correct isoniazid dose) flagged.

## Episode 8. The guidelines disagree (5 min)

```bash
python rag.py "From what age is a person with acute watery diarrhoea counted as a suspected cholera case?" --search-only
```
Expected ✓: passages from **three** documents: the cholera guideline (page 14: aged 2 years or more), the
climate-sensitive diseases manual (page 108) and the community surveillance manual (page 14), which use 5 years.

> **PAUSE.** A record says "suspected cholera, 3 years old". What should the check return?

Not a verdict picked by the model. Either the programme decides which document wins (newest? most specific?) and
that rule is written into the system, versioned and evaluated; or the check returns "guidelines disagree" with
both citations, and a person decides.

---

## Exercises (take-home)

1. **Can we trust the judge? (long version)** Grade 20 baseline answers yourselves; compute how often you agree
   with `factual_correctness`. Repeat with another judge model (`--judge-model`).
2. **Translate, then search.** Translate Amharic questions to English (with the same LLM) before retrieval.
   Re-run episode 2: does the Amharic hit rate improve?
3. **A guideline changes.** Every run logs an index fingerprint. Run `python evaluate.py --retrieval-only
   --chunk-words 120`: a new fingerprint, and the hit rate drops from 77% to 73% ✓. List everything you must
   re-run before an updated guideline goes live.
4. **Tables as rows.** Extract the isoniazid and Plan C tables as one row per weight or age band. Re-run v2: how
   many "unsure" remain?
5. **Hybrid search.** Combine the keyword and embedding scores. Compare hit rates in episodes 2 and 4.
6. **More records.** Add five prescriptions from your own work to `prescriptions.csv`, with the page and a
   verbatim quote. Which error type does the check miss first?
7. **Self-hosted.** Point everything at a self-hosted server: `LLM_BASE_URL=http://<server>:11434/v1` (Ollama or
   vLLM) and `LLM_API_KEY=anything`. Real patient records must never go to a hosted service.
