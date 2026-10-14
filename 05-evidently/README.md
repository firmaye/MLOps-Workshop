# 05 – Evidently: monitoring drift and performance

**Where we are.** Great Expectations asks *"is this data broken?"*. Evidently asks *"is
this data different from what the model learned from?"* and, once outcomes arrive,
*"is the model still right?"*. One notebook: [`monitoring.ipynb`](monitoring.ipynb)
(about a minute to run).

| Kind of monitoring | Needs outcomes? | Available |
|---|---|---|
| Data drift (inputs) | no | when a batch arrives |
| Prediction drift (risk scores) | no | when a batch is scored |
| Performance | **yes** | ~90 days later |

## Setup

From the repo root, environment active:
```bash
cd 05-evidently
```
Open `monitoring.ipynb` in VSCode (kernel: `.venv`) and run it. It reuses
`../03-mlflow/emr_model.py`, trains the 2024 model, and generates 2025 months with the
simulator's scenarios in `05-evidently/data/`. HTML reports go to `05-evidently/reports/`
(open them in a browser; ~5 MB each, not committed). On first import Evidently prints a
harmless `SyntaxWarning`.

## Verified results

**Drift by scenario** (January 2025 vs a same-season 2024 reference):

| Scenario | Drifted columns | Mean predicted risk | Actual GAM rate |
|---|---|---|---|
| baseline | – | 9.2% | 8.2% |
| new_regions | risk, region, water_source_minutes | 13.0% | 11.8% |
| muac_mm | muac_cm, risk | **1.4%** | 8.2% |
| missing_anthro | risk *(70% missing weights not seen by drift)* | 7.7% | 8.2% |
| concept_shift | **– (nothing)** | 9.2% | **19.5%** |
| messy_export | muac_cm, risk | 7.7% | 8.1% |

**Monitoring log, first half of 2025** (gate: risk / region / MUAC / WHZ drift ≤ 0.1,
≤ 5% missing weight and height):

| Month | Hidden truth | Gate | Observed / predicted GAM (+90 days) |
|---|---|---|---|
| Jan, Feb | baseline | ok | 0.89, 0.96 |
| Mar | new_regions | **ALERT** (risk, region) | 1.04 |
| Apr | muac_mm | **ALERT** (risk, MUAC) | 6.13 |
| May, Jun | concept_shift | ok | **2.23, 1.91** |

## Key messages for the room

- **Drift means different, not wrong.** A normal January "drifted" against all of 2024
  because of the lean season: the **reference** must match the season.
- **Watch predicted risk first.** It drifted in 4 of 5 problem scenarios and needs no outcomes.
- **Drift ignores missing values.** 70% missing weights barely registered; check missingness explicitly.
- **Default verdicts mislead.** Evidently's dataset-level drift needs ≥ 50% of columns to
  drift; the region change moved 3 of 19. Write your own gate.
- **Concept drift is invisible without outcomes**, which arrive ~90 days late. Prediction
  drift is the early warning; performance is the confirmation and the retraining trigger.
- **Who acts on what:** data broken → GX / EMR team; population changed → check fairness
  (Fairlearn) and performance; model wrong → retrain a challenger (MLflow registry).

## Evidently cheat sheet (0.7 API)

Older tutorials (`ColumnMapping`, `TestSuite`, `metric_preset`) use the pre-0.7 API and won't work.

| Code | What it does |
|---|---|
| `DataDefinition(numerical_columns=[...], categorical_columns=[...])` | Tell Evidently each column's type. |
| `Dataset.from_pandas(df, data_definition=...)` | Wrap a DataFrame. |
| `Report([DataDriftPreset()]).run(current, reference)` | Drift test for every column; returns a snapshot. |
| `snapshot.save_html("x.html")` / `snapshot.dict()` | Interactive report for people / results for code. |
| `ValueDrift(column="risk", tests=[lte(0.1)])` | Drift score for one column, with a pass/fail test. |
| `MissingValueCount(column=..., share_tests=[lte(0.05)])` | Missing values; `tests=` checks the count, `share_tests=` the share. |
| `snapshot.dict()["tests"]` | Each test's `name` and `status` (PASS / FAIL). |
| `DataDefinition(classification=[BinaryClassification(target=..., prediction_probas=...)])` | Declare outcome + predicted probability for performance metrics. |
| `RocAuc()`, `MeanValue(column=...)`, `ClassificationPreset()` | Performance metrics once outcomes are known. |

Drift methods by default: normalised Wasserstein distance (numeric), Jensen–Shannon
distance (categorical); a column counts as drifted at ≥ 0.1. `ValueDrift(method=..., threshold=...)` changes both.

## Exercises

1. **Missing values the naive way.** Remove the two `MissingValueCount` checks from the
   gate and rerun the scenarios. Which scenario now passes, and why is that dangerous?
2. **Earlier detection of concept shift?** Nothing in the inputs changed. Is there any
   label-free signal you could add (e.g. referral counts, clinic-reported admissions)?
   What would the EMR need to record?
3. **Thresholds.** Lower the risk-drift threshold to 0.05. Do normal months start to
   alert? What does a false alarm cost the team each month?
4. **Per-group drift.** Run the gate separately for Afar + Somali visits in March. Is the
   change concentrated there? (Hint: filter both current and reference.)
5. **Wire it up.** Write a function that takes a month's file and returns
   `{"month", "status", "failed_checks", "mean_risk"}` as a dict, ready for the Prefect
   pipeline to log or alert on.
