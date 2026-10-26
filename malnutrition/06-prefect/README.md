# 06 – Prefect: the monthly pipeline that ties everything together

Every earlier lesson built one piece. This one runs them **in order, every month, without
anyone remembering to**: [`pipeline.py`](pipeline.py) is a Prefect pipeline that ingests
the month's EMR extract, validates it, versions it, scores it, monitors it, checks
performance when outcomes arrive, and retrains when needed.

```
 ingest ──► validate ──► version ──► score ──► monitor ──► performance (3 months back) ──► retrain?
 (retries)   GX gate      DVC        MLflow    Evidently    outcomes now known            challenger vs champion
             └─ broken? ─► QUARANTINE, stop                                               (ROC-AUC, calibration,
                                                                                            Fairlearn per-sex)
                                       every step ─► reports/monitoring_log.csv + Prefect artifact
```

| Step | Tool (lesson) | What it does here |
|---|---|---|
| ingest | Prefect | gets the extract; **retries** if the EMR export fails |
| validate | Great Expectations (02) | the lesson-02 suite; a broken month is moved to `data/quarantine/` and the run stops |
| version | DVC (01) | `dvc add data/raw`; the hash is recorded in the log and in MLflow |
| score | MLflow (03) | loads `models:/gam-risk@champion`, writes `data/predictions/pred_YYYY-MM.csv` (top 20% flagged) |
| monitor | Evidently (05) | drift gate (risk, region, MUAC, missing weights) vs a fixed, same-season 2024 reference |
| performance | scikit-learn + Fairlearn (04) | outcomes for 3 months ago are now known: observed/predicted, ROC-AUC, per-sex sensitivity |
| retrain | MLflow + Fairlearn | challenger on the 4 most recent months with outcomes; written promotion rule; promote = move `@champion` |

**Design decision: Prefect owns the order of steps.** DVC can also define pipelines
(`dvc repro`), but here Prefect decides what runs when (schedules, retries, branching:
"if the gate fails, quarantine and stop"), and DVC only versions the data. Having both
define the order invites them to disagree. (The alternative, a Prefect task that just
calls `dvc repro`, is reasonable when the DVC pipeline already exists.)

## Setup

Two terminals, both at the repo root with the environment active.

**Terminal 1: the Prefect server** (keeps run history; web UI at http://127.0.0.1:4200)
```bash
export PREFECT_SERVER_ANALYTICS_ENABLED=false   # no usage data; also avoids a noisy startup error
prefect server start
```

**Terminal 2: the pipeline**
```bash
prefect config set PREFECT_API_URL=http://127.0.0.1:4200/api    # once: talk to that server
export MLFLOW_DISABLE_TELEMETRY=true DVC_NO_ANALYTICS=1          # optional: no usage data
cd malnutrition/06-prefect
python pipeline.py timeline          # bootstrap + 15 months, ~3 minutes
```
Without a server, Prefect starts a temporary one for each command (slower, no lasting UI).

Other commands:
```bash
python pipeline.py bootstrap                    # only the 2024 history + first champion
python pipeline.py month 2025-03 new_regions    # one month with a chosen scenario
python pipeline.py serve                        # a scheduled deployment (06:00 on the 2nd of each month)
```

The pipeline creates (all ignored by git except the DVC files): `data/raw/` (accepted
months, DVC-tracked), `data/quarantine/`, `data/predictions/`, `reports/` (monitoring log
+ Evidently HTML), `mlflow.db` + `mlruns/`, and a DVC project in this folder (`.dvc/`,
`data/raw.dvc`). The first run of `dvc init` stages its files in git; commit them on your
`work` branch if you want the data versions recorded, or unstage with `git restore --staged .`.

## Showing the results

The terminal output is hard to read on a projector, so after `python pipeline.py timeline` finishes open
[`timeline_results.ipynb`](timeline_results.ipynb) in VSCode (kernel `.venv`) and run it. It reads the pipeline's log
and draws the year in one picture (predicted vs real rate, the calibration check, and the data and drift gates month by
month) plus a colour-coded table. It is saved with its outputs, so it works even if a laptop can't run the pipeline.

A suggested run of the session (about 35 minutes):
1. **Frame it (3 min):** the step diagram above. What Prefect adds: order, retries, a stop when a check fails, a
   history of runs, a schedule.
2. **Read `monthly_pipeline` in `pipeline.py` (5 min):** about 40 lines. Point at `@flow`/`@task`, `retries=2` on `ingest`,
   the "if the gate fails, quarantine and stop" branch, and the retrain rule.
3. **Start `timeline` and ask the first PAUSE (3 min):** it takes about 3 minutes; ask which month the pipeline will notice.
4. **Walk the picture, then the table (10 min).** Top panel first: the model's average risk stays flat while the real rate
   jumps. Then the calibration panel: it only notices in July, three months late. Then the gate strip: February stop,
   March drift, November promote. The Prefect UI is a two-minute side trip (Runs, the January retry, Artifacts).
5. **Discuss (10 min):** the "seven months" PAUSE; automatic promotion; who owns each number.

## Verified result: the 2025 timeline

> **PAUSE (3 min).** Food distribution stops in April 2025. Before running the timeline:
> in which month will the pipeline notice, and when will a better model be in service?

`python pipeline.py timeline` replays a scripted year (the "hidden truth" column is what
the simulator did; the pipeline doesn't know it):

| Month | Hidden truth | What the pipeline did |
|---|---|---|
| 2025-01 | normal | EMR export **failed once, retried, succeeded**; scored with v1; all ok |
| 2025-02 | messy export | **BLOCKED by GX** (5 critical checks), file quarantined, nothing scored |
| 2025-03 | new regions | scored; **drift ALERT** (risk, region) |
| 2025-04 | food distribution stops | scored; nothing looks wrong (inputs unchanged) |
| 2025-06 | (lean season) | mean risk rises to 0.15, but the same-season reference keeps the drift gate quiet |
| 2025-07 | | outcomes for April arrive: **observed/predicted 2.14 → retrain → keep** (challenger not better yet) |
| 2025-08 – 10 | | alerts continue; each challenger still mostly trained on pre-shift months → keep |
| **2025-11** | | challenger trained on Mar–Jun 2025: ROC-AUC 0.810 → 0.826, observed/predicted 1.88 → **0.98**, both sexes better → **PROMOTE** (v2 = `@champion`) |
| 2025-12 – 2026-02 | | outcomes for Sep–Nov still show the alert, but those months were scored by v1, already replaced: **retraining skipped** |
| 2026-03 | | outcomes for December, scored by v2: observed/predicted **1.18**. The alert stops. |

**Seven months from the shift (April) to an adapted model (November).** Outcomes take 3
months to arrive, and a challenger needs enough post-shift months to beat the champion.
That lag is real, and it's why early signals (prediction drift, programme information
like "food distribution stopped") matter.

> **PAUSE (3 min).** Seven months from the shift to an adapted model. What could shorten
> that, and what would each option cost?

## In the Prefect UI (http://127.0.0.1:4200)

- **Runs:** each `timeline-2025` run with its 15 `monthly-pipeline` sub-runs; open one to
  see each task, its logs, duration and state (the January ingest shows the retry).
- **Artifacts:** one markdown card per month (`month-2025-03`, ...) and the
  `monitoring-log` table.
- **Deployments:** after `python pipeline.py serve`, `monthly-pipeline/monthly-emr` with its
  schedule; you can also start a run from here with custom parameters.

## The commands, in plain words

| Command | What it does | When |
|---|---|---|
| `bootstrap` | builds the 2024 history, versions it with DVC, trains the first champion | once, first |
| `month 2025-03 [scenario]` | runs the whole flow for **one** month. `scenario` picks what the simulator does to that month: `baseline` (default), `new_regions`, `muac_mm`, `concept_shift`, `missing_anthro`, `messy_export` | to try one failure on purpose |
| `timeline` | `bootstrap` + all 15 months of 2025 in a row, with the scenarios built in, so the story plays out | the demo |
| `serve` | registers a deployment that runs `month` by itself at 06:00 on the 2nd of each month | what production would be |

`timeline` is only a loop over `month`; in real life nobody would run it.

**Observed / predicted** is the calibration check. Observed = the share of children who actually became
malnourished; predicted = the average risk the model gave them. A ratio near 1 means the risk numbers mean
what they say. 2.0 means twice as many fell ill as predicted, and the pipeline's acceptable range is 0.67 to 1.5.
It is checked three months after scoring because that is when outcomes are known.

**Example.** 1,000 children scored. Average predicted risk 0.10 (about 100 expected cases); 120 actually became
malnourished (observed 0.12). Ratio 0.12 / 0.10 = 1.2: slightly more illness than the model expected, inside the
0.67–1.5 range. A ratio of 2.0 or 0.5 would be flagged.

**When does calibration matter?**
- *Top 20% by rank* (our setup): barely. The cut-off is a rank, so doubling every risk flags the same children.
- *Fixed probability cut-off or a target sensitivity* (e.g. "flag risk ≥ 0.15, which caught 80% last year"):
  a lot. If risks drift up you flag too many; if they drift down you miss cases and sensitivity falls below target.
  The true sensitivity is only known when outcomes arrive, so a drifting ratio is the early warning that the
  threshold no longer means what you chose. Re-pick or recalibrate on recent labelled data.
- *Per-group thresholds* (lesson 04) are tuned on each group's scores, so calibration moving differently by sex
  quietly breaks the equal-sensitivity guarantee.

**Why a CLI and not a notebook?** A notebook is for exploring and teaching one step; this is the part that runs
unattended, with retries and a schedule, so it must be a script. The earlier notebooks explain each piece. Open
`pipeline.py` and read the `@flow` and `@task` functions as the table of contents.

## Helper functions in this lesson

`pipeline.py` reuses `emr_model.py` from lesson 03. Its own tasks: `ingest` (read, with retries),
`validate` (GX checkpoint), `quarantine` (move a failed month aside), `version` (`dvc add`), `score` (champion by
alias), `drift_gate` (Evidently checks), `performance` (observed/predicted, ROC-AUC, per-sex sensitivity),
`retrain_and_decide` (challenger vs champion, promotion rule) and `report` (append to
`reports/monitoring_log.csv`). Flows: `bootstrap`, `monthly-pipeline`, `timeline-2025`.

## Prefect concepts used

| Concept | In `pipeline.py` |
|---|---|
| `@task` | one step (`ingest`, `validate`, ...): logged, timed, retryable |
| `@task(retries=2, retry_delay_seconds=2)` | `ingest`: transient failures are retried automatically |
| `@flow` | `monthly_pipeline`: ordinary Python control flow (`if not passed: quarantine; return`) |
| sub-flow | `timeline` calls `monthly_pipeline` once per month; each is its own run in the UI |
| logging | `get_run_logger()` / `log_prints=True`: logs land in the UI per task |
| artifacts | `create_markdown_artifact`, `create_table_artifact`: results people read in the UI |
| deployment + schedule | `monthly_pipeline.serve(name=..., cron="0 6 2 * *")`; production setups use work pools / workers |

## Things to discuss

- **The policy lives in code.** The capacity (20%), outcome delay (3 months), training
  window (4 months), alert thresholds and promotion rule are all at the top of
  `pipeline.py`, versioned in git and reviewable. Who should own each number?
- **Automatic promotion?** Here the rule promotes on its own. Many teams pause for a human
  (Prefect can wait for input mid-run, exercise 2). For a clinical model, which is right?
- **The reference stays fixed.** Deriving it from each champion's training months caused
  false drift alerts when we tried it (March's regional shift ended up in the reference).
- **Don't retrain on stale evidence.** Months scored by a replaced model still show the
  old error; retraining on that signal is wasted work.
- **Where would this run?** A ministry server on a schedule (this design), triggered by a
  new EMR export landing, or partly at the edge (see "Where each tool runs" in the main README).

## Start over

Stop the pipeline, then from `06-prefect/`:
```bash
rm -rf data reports mlflow.db mlruns .dvc .dvcignore
```
(The Prefect server keeps its run history; that's harmless.)

## Exercises

1. **Alert someone.** When a month is BLOCKED, the pipeline only logs it. Add a
   notification (Prefect *Automations* in the UI can react to a flow's state, or call a
   webhook from the flow).
2. **Human approval.** Before `set_registered_model_alias(..., "champion", ...)`, pause and
   ask a person: look up `prefect.flow_runs.pause_flow_run(wait_for_input=...)`. What
   should the approver see?
3. **Training window.** Set `TRAIN_WINDOW = 6` and rerun (start over first). When is the
   challenger promoted, and how close to 1 is observed/predicted afterwards? Why?
4. **Fix and re-run February.** Clean the quarantined file (GX lesson exercise 4), put it
   back in `data/incoming/`, and run `python pipeline.py month 2025-02 messy_export`.
   What does the monitoring log show?
5. **An edge bundle.** Add a final task that exports the champion as a points table plus
   input rules for offline devices (see the main README). When should it run?

Try the exercises first (they are take-home). Stuck, or short on time? [`exercise_solutions.ipynb`](exercise_solutions.ipynb) holds a worked answer to each; it ships without outputs, so run it to see them.
