# Facilitator notes: LLM guideline assistant (Thu 29 Oct, 13:30–16:30)

Facilitator: Yoni. Participants: EAII technical staff; several will know LLMs and RAG better than the workshop
does. Let them say so; the session is about evaluation and change, not about RAG techniques.

**The one sentence:** an LLM application is a pipeline of versioned parts (documents, index, prompt, model);
every change needs the same evaluation, in layers, and the judge needs checking too.

## Timeline

| Clock | Block | Lab guide | Notes |
|---|---|---|---|
| 13:30–13:45 | Intro slides (setting, the decision, cost of a wrong answer, the six guidelines, today's plan) | – | Say early: test questions only, no patient data; hosted because nobody installs a model |
| 13:45–13:55 | Set up | Ep 0 | Hand out the key (on the board, not by email). Downloads should be done; USB fallback |
| 13:55–14:10 | It sounds right | Ep 1 | Let them ask their own questions too |
| 14:10–14:30 | Retrieval | Ep 2 | No key needed: works even if the API is down |
| 14:30–15:00 | Three layers | Ep 3 | MLflow UI on the projector |
| 15:00–15:15 | Break | | Start the smaller-model run before the break (it takes a few minutes) |
| 15:15–15:40 | A cheaper model | Ep 4 | Rule first, then results |
| 15:40–15:55 | The guidelines disagree | Ep 5 | |
| 15:55–16:05 | A guideline changes | Ep 6 | Short |
| 16:05–16:30 | Judge check + discussion | Ep 7 | Pairs grade 10 answers; compare in the room |

If 15 minutes behind: run episode 6 as a demo on the projector, and make episode 7 the take-home.

## Per episode: what to say, what to expect, what to ask

**Ep 0.** Expected: cholera guideline page 14 first. If `rag.py` says "no PDFs", they skipped the download; if
it says "no API key", the key isn't exported in *this* terminal.

**Ep 1.** The malaria question is deliberately out of scope (none of the six documents covers malaria treatment).
Expected: the answer "The guidelines provided do not cover this." If the model answers anyway, even better for
the PAUSE. PAUSE answers to look for: a fixed question set with reference answers, checked by clinicians;
refusals; Amharic; cost and speed.

**Ep 2.** Verified: 77% overall, 85% English, 0% Amharic at k=5; 82% / 85% / 50% at k=10; 73% with 120-word
passages. Say: "No answer model can fix a passage it never sees." The k=10 Amharic hit is luck (the Latin
abbreviation "INH" in the question), not understanding: point that out.

**Ep 3.** Fill in the summary after the key run. Find a question with high faithfulness and low correctness
before the session so you can show it. Say: "Faithful to the wrong passage is still wrong."

**Ep 4.** Insist the rule is written before the run. Fill in the comparison after the key run; pick one question
whose answer changed for the projector.

**Ep 5.** Verified: the question retrieves passages from all three conflicting documents (cholera p.14 says 2
years; climate-sensitive diseases manual p.108 and CEBS manual p.14 say 5 years). Also known: the vitamin A
schedule for eye signs differs between the emergency nutrition guideline (p.81) and the acute malnutrition
guideline (p.19). Say: "This is a programme decision, not a model decision."

**Ep 6.** Verified: `--chunk-words 120` changes the fingerprint and drops the hit rate to 73%. Link back to DVC
(day 1): the documents are data and should be versioned the same way.

**Ep 7.** Pairs grade, then call out disagreements. Expect the judge to be strict on wording and lenient on
missing details, or the reverse; either way the point is to measure it.

## Fallbacks

- **The API is down or slow:** episodes 2, 5 (search) and 6 need no key. For 3, 4 and 7, open the saved answers
  in `results/` (copied from the facilitators' run onto the USB stick) and the MLflow screenshots.
- **The venue internet is down:** guidelines from the USB stick (`python scripts/download.py guidelines --from <USB>`).
- **Rate limits with 20 people at once:** stagger runs by table; `--limit 10` runs the first ten questions only.

## Discussion questions

1. Which of today's changes (document, index, prompt, model, judge) would your team actually notice in
   production, and how?
2. Who should own the evaluation question set, and how often should it grow?
3. What would have to be true before patient information could go to such an assistant? Hosted or self-hosted?
4. Where would a person stay in the loop: every answer, a sample, or only when the assistant isn't sure?
5. The Amharic result: translate the question, translate the guidelines, or a multilingual model? What does each
   cost to evaluate?

## Before the day

- [ ] Buy the OpenRouter credit, set the spending cap, run `python evaluate.py --run-name baseline` and the
      smaller model; fill the *(key)* numbers into `LAB_GUIDE.md`.
- [ ] Copy `results/` (saved answers) and `.ragas_cache/` to the USB stick as the fallback.
- [ ] Check OpenRouter accepts the "thinking off" switch for the chosen models (`rag.thinking_switch`).
- [ ] Clinical review of `eval_questions.csv`; Amharic review of the two Amharic questions.
