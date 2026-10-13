# 02 – Great Expectations: stop bad data before it reaches the model

**Where we left off.** At the end of the DVC lesson, one month of EMR data with
MUAC recorded in millimetres dropped ROC-AUC from 0.81 to 0.65, and the
pipeline ran green. DVC versions data faithfully; it has no opinion on whether
the data is *correct*. Great Expectations (GX) adds that opinion: a written,
versioned, testable definition of "a valid monthly extract", plus a gate that
stops the pipeline when it isn't met.

> **Heads-up for the instructor:** GX 1.0 (Aug 2024) replaced the old API.
> Most blog posts and Stack Overflow answers still show 0.x code
> (`great_expectations init`, `ge.from_pandas`, `validator.expect_...`). None of
> that works with this lesson. Tested with GX 1.8.1 and 1.24 (identical results).
> GX 1.x minor versions still add and rename things, so check `gx.__version__`
> when an example from the docs doesn't work. On 1.8 you'll see a harmless
> `pyparsing` deprecation warning.

Run everything from inside this `02-great-expectations/` folder.

---

## Concepts (GX 1.x)

| Concept | In this lesson | What it is |
|---|---|---|
| **Data Context** | `gx/` folder | The project: stores everything below as JSON/YAML, committed to git |
| **Data Source → Asset → Batch Definition** | `emr` → `visits` → `monthly_extract` | How GX gets data. Ours: "a pandas DataFrame we hand you at run time" |
| **Expectation** | `ExpectColumnValuesToBeBetween(column="muac_cm", 8, 25)` | One verifiable assertion about the data |
| **Expectation Suite** | `emr_monthly_extract` (42 expectations) | Everything we expect of one batch |
| **Validation Definition** | `emr_monthly` | Suite + batch definition |
| **Checkpoint** | `emr_gate` | Runs validations, then **actions** (here: rebuild Data Docs; could be Slack/email) |
| **Data Docs** | `gx/uncommitted/data_docs/local_site/index.html` | Human-readable HTML report of suites and results |

Three knobs you'll use constantly:
- **`mostly=0.95`**: pass if at least 95% of rows comply (real data is never perfect).
- **`row_condition="age_months >= 6", condition_parser="pandas"`**: apply only to
  some rows (MUAC isn't measured under 6 months). Recent GX also accepts
  `row_condition=Column("age_months") >= 6`, but that fails on older 1.x releases.
- **`severity="warning"`**: a label. **GX itself still fails the run on a
  warning**; the "block on critical, warn on warning" policy lives in our
  `validate.py`. (This surprises people, so show it.)

## Part 1 – Write the suite

Read `build_suite.py`. The expectations are grouped by the question they answer:

| Group | Example | Catches |
|---|---|---|
| 1. Schema & volume | exact column set; 500–5000 rows | renamed/dropped columns, half-finished exports |
| 2. IDs & formats | unique `visit_id`; date format; facility code regex | duplicate exports, garbled IDs |
| 3. Categorical codes | `sex` in {F, M}; region in the 8 known | "female", "Oromiya": silently breaks one-hot encoding |
| 4. Plausibility | MUAC 8–25 cm; WHZ −5..5 (WHO flag limits) | unit errors, typos |
| 5. Completeness | weight/height/WHZ ≥95% present; MUAC present for ≥6 months | broken scales, skipped fields |
| 6. Cohort | min WHZ ≥ −2; min MUAC ≥ 12.5 | already-malnourished children who should have been referred, not scored |
| 7. Warnings | GAM rate 2–30%; ≥20 facilities; no MUAC under 6 months | odd but possible; a human should look |

```bash
python build_suite.py
#   suite 'emr_monthly_extract' unchanged (42 expectations); nothing written
cat gx/expectations/emr_monthly_extract.json | head -40     # the suite is just JSON, in git
```
The suite is already committed, so nothing is written. Change a rule in
`build_suite.py` and rerun to see it saved; `git diff gx/` shows the change.

> **GX quirks we hit while building this** (worth knowing before participants do):
> - Every save gives each expectation a new random `id`, so re-saving an
>   unchanged suite produces a noisy git diff (and would re-trigger DVC).
>   `build_suite.py` compares rules first and only writes when they changed.
> - Creating a new `gx.ExpectationSuite(name=...)` with the name of a stored
>   suite and calling `add_expectation` on it **writes into the stored suite
>   immediately**, even before you save. Our first version of `build_suite.py`
>   did this and silently doubled the suite to 84 expectations. Read the stored
>   suite first, and only then build the new one.

**Where do thresholds come from?** Two sources, and say both out loud:
domain rules (WHO plausibility limits, the programme's age range, the cohort
definition) and observed history (row counts, GAM rate). Prefer domain rules;
data-derived thresholds encode whatever was normal, including old bugs.

## Part 2 – Validate a year of clean history

```bash
python ../00-data/simulate_emr.py --start 2024-01 --months 12 --out data/history
python validate.py data/history
#   PASS  data/history/emr_2024-01.csv  (2000 rows, 42 expectations)
#   ...  (all 12 months PASS)
#   OK: no critical failures
```
Each monthly file is validated as its own batch, so a failure points at *which
month* is broken. Open the Data Docs link printed at the end.

## Part 3 – Break things

Generate one month per scenario and validate each:
```bash
for s in muac_mm missing_anthro messy_export new_regions concept_shift; do
  python ../00-data/simulate_emr.py --start 2025-01 --scenario $s --out data/scenario_$s
  python validate.py data/scenario_$s; echo "exit code: $?"
done
```

Verified results:

| Scenario | Result | What fired |
|---|---|---|
| `muac_mm` | **FAIL** (exit 1) | `muac_cm` between 8 and 25: 1609 rows (100%), e.g. 147, 128 |
| `missing_anthro` | **FAIL** | weight, height, WHZ not null: 70.3% missing each (limit 5%) |
| `messy_export` | **FAIL**, 5 critical + 1 warning | duplicate `visit_id` (30 rows); `sex` "female"/"male" (42); age 68–70 months (12); MUAC in mm in Amhara only (404 rows, 23.8%); WHZ −3.0 in cohort; *warning*: MUAC recorded for infants |
| `new_regions` | PASS | nothing: every value is valid |
| `concept_shift` | PASS | nothing: every value is valid |

`messy_export` is the realistic one: several small problems, each in a
minority of rows. The `muac_cm` failure hits 24% of rows because only Amhara's
facilities received the EMR update. A mean-based check would have been diluted;
a per-row range check isn't.

**The last two rows are the most important.** Half the visits suddenly coming
from Afar and Somali, or food distribution stopping, produces data that is
*valid but different*. GX asks "is this data broken?"; it doesn't ask "is
this data like what the model was trained on?". That's Evidently (drift), and
later performance monitoring once outcomes arrive.

## Part 4 – Explore interactively

When writing a new expectation, try it on one batch before adding it to the suite:
```python
import great_expectations as gx
import great_expectations.expectations as gxe
import pandas as pd

ctx = gx.get_context(mode="file")
batch_def = ctx.data_sources.get("emr").get_asset("visits").get_batch_definition("monthly_extract")
batch = batch_def.get_batch(batch_parameters={"dataframe": pd.read_csv("data/scenario_messy_export/emr_2025-01.csv")})

r = batch.validate(gxe.ExpectColumnValuesToBeInSet(column="sex", value_set=["F", "M"]))
print(r.success, r.result["unexpected_count"], r.result["partial_unexpected_counts"])
#   False 42 [{'value': 'female', 'count': 14}, {'value': 'male', 'count': 6}]
```
(`partial_unexpected_counts` summarises a sample of the first 20 failures, not all 42.)

## Part 5 – Data Docs

Open `gx/uncommitted/data_docs/local_site/index.html`. Two views:
- **Expectation Suites:** the suite rendered as readable sentences. A clinician
  or data manager can review the rules without reading Python.
- **Validation Results:** one page per run, with failing expectations and sample bad values.

`gx/uncommitted/` is gitignored: suites are code, results are run artefacts.

## Part 6 – Gate the DVC pipeline

Now make `01-dvc` refuse to train on bad data. Add a `validate` stage at the
top of `01-dvc/dvc.yaml`, and make `prepare` depend on its report:
```yaml
stages:
  validate:
    cmd: python ../02-great-expectations/validate.py data/raw --report reports/validation.json
    deps:
      - data/raw
      - ../02-great-expectations/validate.py
      - ../02-great-expectations/gx/expectations/emr_monthly_extract.json
    outs:
      - reports/validation.json:
          cache: false
  prepare:
    cmd: python src/prepare.py
    deps:
      - src/prepare.py
      - data/raw
      - reports/validation.json     # <- new: prepare runs only after validation passes
    ...
```
Then, from `01-dvc/`:
```bash
dvc dag                     # data/raw.dvc -> validate -> prepare -> train -> evaluate
python ../00-data/simulate_emr.py --start 2025-01 --scenario muac_mm --out data/raw
dvc add data/raw
dvc repro
#   FAIL  data/raw/emr_2025-01.csv
#         [critical] expect_column_values_to_be_between(muac_cm): 1609 rows (100.0%), e.g. [147.0, 128.0, 128.0]
#   ERROR: failed to reproduce 'validate': ... exited with 1
#   (prepare, train, evaluate never ran: the old model is untouched)

rm data/raw/emr_2025-01.csv && dvc add data/raw
dvc repro
#   Running stage 'validate':  OK: no critical failures
#   Stage 'train' is cached - skipping run, checking out outputs
```
Two things to point out:
- The suite JSON is a dependency, so **changing the rules re-runs validation**,
  just like changing code re-runs training.
- "`train` is cached": DVC's run-cache remembered it had already trained on
  exactly this data and these params, so it restored the model instead of
  retraining.

---

## Discussion points
- **Block or quarantine?** We block the whole pipeline if any month fails. In
  production you'd often quarantine the bad batch, train on the rest, and alert
  the data owner. What's right for a clinical model?
- **Who owns the rules?** The suite is the contract between the EMR team and
  the ML team. Data Docs make it reviewable by non-programmers.
- **Training vs scoring.** This suite needs `gam_within_90d`, which only
  exists ~90 days after a visit. A scoring-time suite must not require the
  label (exercise 3).
- **Validate early and late.** Here we validate raw extracts. You can also
  validate model inputs after feature engineering, and predictions (e.g. risk
  scores in [0, 1], alert rate near 20%).

## Exercises
1. Generate a month where only one region reports
   (hint: filter a baseline file to `region == "Oromia"` with pandas). Which
   expectations fire, and at what severity? Should "only 5 facilities
   reported" block training?
2. The `messy_export` duplicates are exact copies of real visits. Write an
   expectation that would also catch the same child seen twice on the same day
   at the same facility under different `visit_id`s
   (hint: `ExpectCompoundColumnsToBeUnique`).
3. Create a second suite, `emr_scoring_batch`, for data arriving at
   prediction time: no label column, and the row-count bounds suited to a daily batch.
4. Make the `messy_export` month pass by *fixing the data*, not by loosening
   the rules: write a small `clean.py` that drops duplicates, maps
   "female"/"male", converts MUAC > 50 from mm to cm, and removes out-of-cohort
   rows. Should a cleaning step like this live in the pipeline, or should the
   EMR export be fixed upstream?
