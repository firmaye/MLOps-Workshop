# Facilitator notes: EMR malnutrition, lessons 00–06 (Tue 27 Oct)

Facilitator: Yoni. Two blocks: 10:45–12:30 (data, DVC, Great Expectations, MLflow tracking) and 14:00–16:30
(MLflow registry, Fairlearn, Evidently, Prefect). Participants: EAII technical staff; most know modelling, fewer
know the tools. The use cases on Wednesday–Thursday reuse these tools without re-teaching them, so today has to
land the tools. Notes for the other use cases: [`07-tb-xray/FACILITATOR_NOTES.md`](../07-tb-xray/FACILITATOR_NOTES.md),
[`08-llm-rag/FACILITATOR_NOTES.md`](../08-llm-rag/FACILITATOR_NOTES.md).

**The one sentence:** every tool exists to catch a specific failure; one year of a simulated EMR shows each failure
and the tool that catches it.

## Timeline

| Clock | Block | Lesson | Notes |
|---|---|---|---|
| 10:45–10:55 | The data and the task | 00 | Projector only: the label, leakage, MUAC vs WHZ by sex. PAUSE before section 4 |
| 10:55–11:35 | DVC | 01, parts 0–3, 8 | Parts 4–7 and 9 optional. Two PAUSEs (v2 better?, the audit) |
| 11:35–12:05 | Great Expectations | 02, parts 1–3, 6 | The muac_mm teaser from DVC leads in. Parts 4–5 optional |
| 12:05–12:30 | MLflow tracking | 03, notebook 1 | `mlflow ui` on the projector |
| 13:30–14:00 | Team presentation 1 | | |
| 14:00–14:25 | MLflow registry and serving | 03, notebook 2 | Insist the promotion rule is written before the challenger runs |
| 14:25–15:05 | Fairlearn | 04 | The heart of the afternoon |
| 15:05–15:20 | Break | | |
| 15:20–15:55 | Evidently | 05 | |
| 15:55–16:30 | Prefect: the year replayed, then discussion | 06 | `python pipeline.py timeline` takes a few minutes: start it, then talk |

The morning is tight. If 15 minutes behind at 12:00: show MLflow notebook 1 on the projector only, and let
participants run it after lunch while the registry starts. If behind in the afternoon: run Prefect as a demo and
discuss from the timeline table in the README.

## Per lesson: what to say, what to expect, what to ask

**00 Data.** Say: "All of this is synthetic, the directions loosely from Ethiopian DHS." Explain why the label is
GAM *within 90 days*: predicting current GAM relearns the WHZ/MUAC cut-offs (leakage). Point at the MUAC vs WHZ
plot: the label itself means something different for girls. PAUSE answers to look for: "we wouldn't notice until
someone complained"; that's the day's starting point.

**01 DVC.** Expected: v1 ROC-AUC 0.8022; v2 0.8122 with PPV 0.33 → 0.26; gbm 0.8038 (discard). PAUSE on v2: the
test set changed too (May–Jun 12% prevalence vs Nov–Dec 9%); diffs compare like with like only on fixed evaluation
data. PAUSE on the audit: most teams can't answer. Say: "Git stores the pointers, DVC the bytes. Forgetting `dvc
push` is the #1 mistake." Close with the teaser: muac_mm drops ROC-AUC 0.81 → 0.65 and nothing complains.

**02 Great Expectations.** Expected: muac_mm, missing_anthro, messy_export FAIL; new_regions and concept_shift
PASS. PAUSE answers: most predict muac_mm and messy_export; few predict the passes. Say: "GX asks *is this data
broken?*, not *is it like the training data?*" Part 6 is the payoff: the gated `dvc repro` stops at validate and
the old model is untouched. Discussion: block or quarantine; who owns the rules.

**03 MLflow.** Notebook 1: baseline logistic 0.8122; best ROC-AUC isn't the smallest girls/boys gap (gbm depth 2
has 0.558 for girls). PAUSE: a decision for people, not `ORDER BY`. Notebook 2: champion 0.8256 vs challenger
0.8363 on May–Jun 2025 (prevalence 24%); rule (ROC-AUC +0.005, no sex group losing >0.02 sensitivity) → PROMOTE.
Serving gives `[[0.107, 0.893]]` for the example child. Say: "The registry is where the evidence for a decision
lives."

**04 Fairlearn.** Expected: sensitivity girls 0.54 vs boys 0.61 at the same GAM rate; regions 0.15 (Addis) to
0.80 (Afar); the 2-month intersection gap (0.22 vs 0.74, 23 cases each) is mostly noise. PAUSE 1 answers: the
measurement (MUAC reads lower for girls), not the code. Dropping `sex` halves the gap (0.071 → 0.036). PAUSE 2:
per-sex thresholds within 20% capacity give 0.58 / 0.58; `ThresholdOptimizer` with defaults flags 33%. Say:
"Fairness tools optimise what you tell them. Choose the definition with the programme first."

**05 Evidently.** PAUSE 1: the lean season; the reference must match the season. PAUSE 2: most predict all five;
concept_shift shows nothing (mean risk 9.2%, actual GAM 19.5%). PAUSE 3: only outcomes reveal it, ~90 days late;
observed/predicted 2.23 in May. Say: "Drift means different, not wrong. Watch predicted risk first. Drift ignores
missing values."

**06 Prefect.** Expected timeline: February blocked by GX; March drift alert; April shift invisible; July outcomes
→ retrain → keep; November → PROMOTE (observed/predicted 1.88 → 0.98); retraining skipped on months scored by the
replaced model. PAUSE answers: earlier signals (prediction drift, programme information such as "food
distribution stopped"), shorter outcome delay, retraining on fewer post-shift months (riskier). Show the UI: runs,
the January retry, the monthly artifacts.

## Fallbacks

- **Notebooks (00, 03, 04, 05) are committed executed:** if a laptop fails, participants read the outputs.
- **DVC, GX, Prefect:** every expected output is in the lesson README; run on the projector and let people follow.
- **DVC remote problems:** the remote is a local folder (`../dvc-remote`); if `dvc push` fails, check they cloned
  inside a parent folder (`mkdir mlops && cd mlops`).
- **Port clashes:** `mlflow ui --port 5001`; Prefect's server uses 4200.
- **Starting over:** the "Starting over" commands in the main README.

## Discussion questions (end of day, 15 min if time)

1. Which of today's failures has your team already met? Which tool would have caught it?
2. Who owns the GX rules, the fairness definition and the promotion rule in your organisation?
3. Automatic promotion or a human in the loop, for a clinical model?
4. Outcomes arrive 90 days late. What earlier signals do you have in your own projects?
5. What runs centrally and what runs at the edge, for your deployments? (See "Where each tool runs" in the README.)

## Before the day

- [ ] Fresh clone on a Windows laptop: run 00–06 end to end; check numbers match the READMEs.
- [ ] `../dvc-remote` exists; `mlflow ui` and the Prefect server start.
- [ ] Start the Prefect timeline once beforehand so the UI has runs to show if the live run is slow.
- [ ] Projector: VS Code font size, terminal width for `dvc metrics diff` tables.
