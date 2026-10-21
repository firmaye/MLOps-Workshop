# Facilitator notes: LLM guideline assistant (Thu 29 Oct, 13:30–16:30)

Facilitator: Yoni. Participants: EAII technical staff; several will know LLMs and RAG better than the workshop
does. Let them say so; the session is about evaluation and change, not about RAG techniques.

**The one sentence:** an LLM application is a pipeline of versioned parts (documents, index, prompt, model);
every change needs the same evaluation, in layers, and the judge needs checking too.

**The link between the halves:** same pipeline, different question once it sits in a workflow. Part A asks "are
the answers good?"; Part B asks "does it catch the errors?", and counts what each kind of mistake costs.

## Timeline

| Clock | Block | Lab guide | Notes |
|---|---|---|---|
| 13:30–13:40 | Intro slides (setting, the decision, cost of a wrong answer, the six guidelines, today's plan) | – | Say early: test questions and simulated records only, no patient data; hosted because nobody installs a model |
| 13:40–13:50 | Set up | Ep 0 | Hand out the key (on the board, not by email). Start the embedding build now; it runs during Ep 1–2 |
| 13:50–14:00 | It sounds right | Ep 1 | Let them ask their own questions too |
| 14:00–14:15 | Retrieval | Ep 2 | No key needed: works even if the API is down |
| 14:15–14:45 | Reading the scores + judge check | Ep 3 | MLflow UI on the projector. Pairs grade 5 answers |
| 14:45–15:00 | Break | | |
| 15:00–15:10 | Part B intro + does the search find the rule? | Ep 4 | Say the link sentence. Records are simulated: say so |
| 15:10–15:25 | v1: the LLM decides | Ep 5 | Sensitivity, specificity, counts not percentages |
| 15:25–15:45 | v2: the LLM reads, Python counts | Ep 6 | The PAUSE matters more than the numbers |
| 15:45–16:00 | A cheaper model | Ep 7 | Rule first, then results |
| 16:00–16:05 | The guidelines disagree | Ep 8 | Short |
| 16:05–16:30 | Discussion | – | Questions below |

If 15 minutes behind: shorten Ep 3's judge check to two answers on the projector, and run Ep 7 as a demo.

## Per episode: what to say, what to expect, what to ask

**Ep 0.** Expected: cholera guideline page 14 first. If `rag.py` says "no PDFs", they skipped the download; if
it says "no API key", the key isn't exported in *this* terminal. The embedding build downloads 67 MB and takes
about 5 minutes on a laptop CPU (286 s on the test machine); if the venue internet is slow, copy `index/` from the
USB stick into `08-llm-rag/` instead.

**Ep 1.** The malaria question is deliberately out of scope. Expected: "The guidelines provided do not cover
this." If the model answers anyway, even better for the PAUSE. PAUSE answers to look for: a fixed question set
with reference answers, checked by clinicians; refusals; Amharic; cost and speed.

**Ep 2.** Verified: 77% overall, 85% English, 0% Amharic at k=5; 82% / 85% / 50% at k=10; 73% with 120-word
passages; embedding search 73% / 80% / 0%. Say: "No answer model can fix a passage it never sees." The k=10
Amharic hit is luck (the Latin abbreviation "INH" in the question). The embedding model is English-only: a
multilingual one is about 1 GB and ran out of memory on the 16 GB test machine.

**Ep 3.** Key run (gemma-4-26b): hit 77%, cites 73%, refusals 21 of 26, Amharic 1 of 2, faithfulness 0.66,
context recall 0.67, factual correctness 0.41. Walk the table of what each score computes, slowly; no shock
needed. Show `nutr_01` (right page at rank 1, faithfulness 1.0, correctness 0.00: misread table). Judge check:
`csd_01` matches the reference and scores 0.00; `cebs_02` scores 1.0 for one model and 0.00 for the other on the
same content. Three of 132 judge calls hit the output limit and have no score. Say: "A judge is a model; measure
it like one."

**Ep 4.** Say the link sentence. Verified (43 records with a rule): keywords 33 / 35 of 43 at k=5 / 8, embeddings
36 / **41** of 43. Keyword misses at k=8 include `rx20`, `rx21` (amoxicillin "SAM without medical complications
(OTP)": the guideline's table says "Routine Medication and Treatment in OTP"). Honest note: an earlier draft of
the records used the guideline's own words in the diagnoses and keyword search then found 42 of 43. Test data
written by someone who has read the documents flatters keyword search. Ask: who should write evaluation records?

**Ep 5.** Key run (v1, gemma): caught 15 of 22, passed 15 of 21, 6 false alarms; by type dose 2 of 5, age band
2 of 5, pregnancy 3 of 3, duration 4 of 4, contraindication 4 of 5. On the projector: `rx20` (verdict "correct",
reason then computes 300 mg and calls 125 mg under-dosing) and `rx38` (misread weight band). Five v1 replies weren't
valid JSON (quotation marks inside the reason); their verdict is read from the reply. In all five the reason
contradicts the verdict (`rx03` "incorrect", then "100 mg falls within the required range"; `rx25` "correct",
then "the prescription only provides 100,000 IU"): a model that writes the verdict before the reasoning. The pregnancy traps (`rx04`
doxycycline, `rx40` isoniazid, `rx33` albendazole in the 3rd trimester: all correct per the guidelines) passed:
point out that a model's general knowledge could have flagged them, and the guideline is what counts here.

**Ep 6.** Key run (v2, gemma): caught 12 of 22, passed 13 of 21, 2 false alarms, 13 unsure, confidently wrong 5
of 44 (v1: 13). Don't sell v2 as "better"; sell the trade: silent errors down, work for people up. Most unsure
records are flattened tables (`rx37`–`rx42` isoniazid, `rx10`/`rx11` Plan C). Remaining v2 errors are reading
errors: `rx13` (took a fixed 2200–4000 ml range instead of 75 ml/kg), `rx29` (wrong F-75 row), `rx09` (cap read
as 1 mg instead of 1 g). Faithfulness: v1 0.63, v2 0.24, because Python's arithmetic isn't in any passage.
Honest note: the first v2 run had four bugs in its Python (order of checks, "matches" with nothing compared,
hyphenated PDF words, an impossible min > max). They were fixed and v2 re-scored from the saved LLM replies, at no
cost. Say: "When the Python half is wrong you can see it, fix it and re-score for free."

**Ep 7.** Insist the rule is written before the run. Key run (v2, qwen3.5-9b): caught 12 of 22, passed 12 of 21,
**6** false alarms, 9 unsure, confidently wrong **10** of 44. The starting rule fails on false alarms and
confident errors. Same count of caught errors, different errors: `rx32` (first-trimester albendazole) passed.

**Ep 8.** Verified: the question retrieves passages from all three conflicting documents (cholera p.14 says 2
years; climate-sensitive diseases manual p.108 and CEBS manual p.14 say 5 years). Also known: vitamin A for eye
signs (emergency nutrition guideline p.81 vs acute malnutrition guideline p.19), and adult Plan C fluids within
the cholera guideline (p.29: 70 ml/kg over 2½ hours; p.35: over 3–4 hours). Say: "This is a programme decision,
not a model decision."

## Fallbacks

- **The API is down or slow:** episodes 2, 4 and 8 need no key. Episodes 5–7 reuse the saved verdicts in
  `results/` with no key (add `--no-judge`). Episode 3: `results/per_question_baseline.csv` and the MLflow
  screenshots.
- **The venue internet is down:** guidelines from the USB stick (`python scripts/download.py guidelines --from <USB>`);
  the embedding model and vectors: copy `index/` from the USB stick.
- **Rate limits with 20 people at once:** everyone reuses the saved runs; only the facilitator runs live, with
  `--limit 10`.

## Discussion questions

1. v1 or v2 in front of a nurse? What does a false alarm cost, and what does a missed error cost? Who decides the
   trade?
2. Who should write and own the evaluation records (questions, prescriptions), and how often should they grow?
3. The 13 "unsure": fix the documents (tables as data), or accept the human work?
4. What would have to be true before real patient records could go to such a check? Hosted or self-hosted?
5. The Amharic result: translate the question, translate the guidelines, or a multilingual model? What does each
   cost to evaluate?

## Before the day

- [x] Buy the OpenRouter credit, set the spending cap, run `python evaluate.py --run-name baseline` and the
      smaller model; fill the *(key)* numbers into `LAB_GUIDE.md`. (21 Oct; answers and scores in `results/`.)
- [x] Check OpenRouter accepts the "thinking off" switch for the chosen models (`rag.thinking_switch`). Gemma and
      Qwen: yes. gpt-oss-120b refuses it (400); the judge doesn't send it on OpenRouter.
- [x] Run the prescription check: v1, v2, v2 with the smaller model (21 Oct; verdicts in `results/`).
- [ ] **Clinical review of `prescriptions.csv`** (simulated records; expected verdicts written from the guideline
      text, not by a clinician). Check first: `rx42` (6-year-old contact: IPT is for under-fives per the 2017
      guideline, and 200 mg is also below the 250 mg for 20–24.9 kg: two errors in one record); `rx04`, `rx40`
      (doxycycline and isoniazid in pregnancy, marked correct per the guidelines); `rx43` (ethionamide in pregnancy:
      the guideline says avoid; the shorter regimen uses prothionamide); `rx10` (adult Plan C: the guideline gives
      2½ hours on p.29 and 3–4 hours on p.35); `rx28` (IV fluids in SAM with dehydration, not in shock); `rx23`
      (vitamin A in OTP on RUTF, marked incorrect); `rx35` (vitamin A 200,000 IU, breastfeeding, 3 weeks after
      delivery); `rx29`/`rx30` (F-75 daily totals from the annex table); `rx22` (210 mg for 8.4 kg, rounding).
- [ ] Clinical review of `eval_questions.csv`; Amharic review of the two Amharic questions.
- [ ] Copy `index/` (embedding model and vectors, about 70 MB) and `.ragas_cache/` to the USB stick.
- [ ] Projector: MLflow UI with both experiments (`guideline-assistant`, `prescription-check`) open.
