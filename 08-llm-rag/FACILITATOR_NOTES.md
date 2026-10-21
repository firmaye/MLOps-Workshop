# Facilitator notes: LLM guideline assistant (Thu 29 Oct, 13:30–16:30)

Facilitator: Yoni. Participants: EAII technical staff; several will know LLMs and RAG better than the workshop
does. Let them say so; the session is about evaluation and change, not about RAG techniques.

**The one idea:** an LLM application is a set of versioned parts (documents, parser, chunking, search, prompt,
model); test each part, then judge the answers with people and with a judge you've checked against people.

## Timeline

| Clock | Block | Lab guide | Notes |
|---|---|---|---|
| 13:30–13:45 | Intro slides: the decision, the six guidelines, today's one idea | – | Simulated cases only, no patient data; hosted because nobody installs a model |
| 13:45–13:55 | Set up, one traced call | Ep 0 | Key on the board. MLflow trace on the projector |
| 13:55–14:45 | Ragas in depth: search is a part | Ep 1 | 1a table → PAUSE; 1b `nutr_01` on the projector; 1c combinations |
| 14:45–15:00 | Break | | |
| 15:00–15:45 | Labels, rubrics, benchmarks | Ep 2 | Silent grading 15 min; agreement; rewrite one criterion; judge; HealthBench |
| 15:45–16:00 | A cheaper model through the promotion rule | Ep 3 | Rule written before the table |
| 16:00–16:30 | Conclusion: how would Ethiopia validate it? | Conclusion | Discussion; owners per row |

If 15 minutes behind: skip 1c (say the table in one sentence) and run Ep 3 as a demo from the saved runs.

## Per episode

**Ep 0.** Expected ✓: cholera guideline page 14 first. The trace shows prompt, passages, model, tokens, cost
($0.0003 per case), seconds. Say: "Everything you'd need to explain this answer next month is here. So is
everything you'd need to leak it: with patient data the trace store is patient data."

**Ep 1.** Same model, six searches; the right-page count ✓, the Ragas scores *(key)*, all in
`results/search_and_ragas.csv`. Point: context recall tracks the free right-page count (0.70 → 0.98 as the count
goes 17 → 19 of 20), and doesn't change when the LLM changes (0.975 with both models on the same search). Honest
note on structure-based chunks: their page *range* is easier to hit than one page; with first-page-only counting the
gain disappears (`data/SOURCES.md`, on the earlier 22-question set). `nutr_01` (`results/explain_nutr_01.txt`): the
model misread the benchmark table; the judge marks all 5 claims supported: faithful to a misreading. Other Ragas
scores: mention, don't run (precision, relevance, answer relevancy). Say: "Each score is a question to a model;
open one up before trusting any."

**Ep 2.** Cases are simulated and ambiguous on purpose; say so before grading. Silent grading matters: if people
talk, agreement is inflated. Expect lowest agreement on *complete* and *grounded* (vague words), highest on
*classification*. `case04` (cholera 2 vs 5 years) and `case10` (age unknown at 6 months) split rooms. Judge *(key)*:
3 of 20 acceptable, 14 of 20 safe; against the facilitator draft (8 answers) it differs most on *grounded* (5 of 8).
The facilitator draft (`grades/facilitator_draft.csv`) is a fallback, written by the AI assistant that built the
lesson and **not reviewed by Yoni or a clinician**: regrade before using it in the room. Show `case20` (planted
instruction repeated), `case13` (night sweats missed, both models, every run), `case19` (Plan C boluses for SAM).
HealthBench figures verified from arXiv 2505.08775 (5,000 conversations, 262 physicians, 60 countries, 48,562
criteria, GPT-4.1 grader macro F1 0.709).

**Ep 3.** Insist on the rule first. The surprise: qwen is dearer per case ($0.22 vs $0.18 per 1,000) because it
writes 298 vs 126 tokens; slower (7.1 vs 2.1 s median); the judge likes it more (6 vs 3 of 20 acceptable); and it
follows the planted instruction fully. Say: "A judge that rewards length will promote the wrong model unless the
rule names safety."

**Conclusion.** The gates and Tier C are from the EAII MLOps Practice Guide v0.1 (opening-session slides, 21 Oct).
**EFDA's current requirements for software as a medical device were not checked:** say "check before stating".
Ask the room who owns each row; push for named people, not units.

## Fallbacks

- **API down:** every run is saved in `results/`; `cases.py cost`, `cases.py agree`, `evaluate.py --retrieval-only`,
  `explain_score.py` output (`results/explain_nutr_01.txt`) need no key.
- **Nobody grades:** `grades/facilitator_draft.csv` (draft, not clinical).
- **Rate limits:** only the facilitator runs live.

## Before the day

- [x] Markdown guidelines committed (LlamaParse, facilitator only; `facilitator/parse_guidelines.py`).
- [x] Runs saved: six searches + cheaper model (`evaluate.py`), cases both models, case13 ×5, judge (21 Oct).
- [ ] **Clinical review of `cases.csv`.** Check first: `case04` (cholera age conflict: is "suspected" right?),
      `case10` (infant near 6 months: which criteria?), `case19` (dehydration in SAM: the expected action), `case13`
      (night sweats alone qualifies?), `case18` (MUAC in a 6-year-old), `case20` (antibiotics in some dehydration),
      `case12` (MUAC < 18.5 cm in older people), `case17` (animal deaths as an unusual event).
- [ ] Yoni regrades `grades/facilitator_draft.csv`.
- [ ] Clinical review of `eval_questions.csv` and `prescriptions.csv` (take-home).
- [ ] Licence: the Markdown is a full-text copy of the guidelines (`data/SOURCES.md`); confirm before publishing.
- [ ] Projector: MLflow UI with `case-assessment` (traces) and `guideline-assistant` open.
