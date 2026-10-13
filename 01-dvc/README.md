# 01 – DVC: versioning EMR data, models, and pipelines

**Scenario.** Health centres across Ethiopia record child visits in an EMR.
Every month a new extract arrives. We train a model that flags children at
risk of developing acute malnutrition (GAM) in the next 90 days, so the clinic
can prioritise follow-up. Data comes from `../00-data/simulate_emr.py`
(synthetic; see [`00-data/README.md`](../00-data/README.md)).

**What DVC gives us here**
- Every model is tied to the exact monthly extracts it was trained on.
- New months are stored incrementally (only new files are uploaded).
- The pipeline reruns only what changed: data, code, or parameters.
- Experiments and metric comparisons without a separate server.

Run everything from inside this `01-dvc/` folder. The numbers below are from a
verified run; yours should match (the simulator is deterministic).

---

## Part 1 – Version a growing dataset

```bash
dvc init --subdir                  # DVC project inside a bigger git repo
git commit -m "Initialise DVC"

# The first six monthly extracts arrive
python ../00-data/simulate_emr.py --start 2024-01 --months 6 --out data/raw
dvc add data/raw                   # track the whole DIRECTORY as one unit
cat data/raw.dvc                   # one hash (....dir) + nfiles: 6
git add data/raw.dvc data/.gitignore
git commit -m "EMR visits Jan-Jun 2024"

dvc remote add -d storage ../../dvc-remote    # local folder standing in for S3/GCS/Azure
git add .dvc/config && git commit -m "Add remote"
dvc push                                       # 7 files pushed (6 CSVs + 1 directory manifest)
```

## Part 2 – The pipeline

Read `dvc.yaml` and `params.yaml` first. Three stages:

| Stage | What it does | Why it matters |
|---|---|---|
| `prepare` | Combines monthly files; **temporal split**: last 2 months = test | A random split leaks the future into training |
| `train` | Logistic regression or gradient boosting; preprocessing saved inside the model | Serving can send raw EMR fields |
| `evaluate` | Flags the top 20% riskiest children (clinic capacity); reports sensitivity / PPV, plus per-group results | A clinically meaningful metric, not just accuracy |

```bash
dvc dag
dvc repro
#   train: 2024-01..2024-04 (8000 visits)  test: 2024-05..2024-06 (4000 visits)
#   {"roc_auc": 0.8022, "sensitivity": 0.5521, "ppv": 0.3312, ...}
git add dvc.lock .gitignore metrics.json metrics_by_group.json plots
git commit -m "Baseline model" && git tag v1
dvc push
dvc repro            # nothing changed -> every stage skipped
```

## Part 3 – New data arrives (the core DVC use case)

```bash
python ../00-data/simulate_emr.py --start 2024-07 --months 6 --out data/raw
dvc status           # prepare: changed deps: modified: data/raw
dvc add data/raw
dvc push             # 7 files pushed: only the 6 NEW months + the new manifest
dvc repro            # all stages rerun: the data feeds everything
dvc diff             # 6 files added; processed data + model modified
dvc metrics diff
git add -A && git commit -m "EMR visits Jul-Dec 2024" && git tag v2-data
dvc push
```

```
Path          Metric       HEAD    workspace    Change
metrics.json  ppv          0.3312  0.2587       -0.0725
metrics.json  prevalence   0.12    0.0907       -0.0293
metrics.json  roc_auc      0.8022  0.8122       0.01
metrics.json  sensitivity  0.5521  0.5702       0.0181
```

**Discussion: is v2 better than v1?** Careful. Because the split is temporal,
the *test set changed too*: v1 was tested on May–Jun (start of the lean
season, 12% prevalence), v2 on Nov–Dec (9%). PPV fell because there are fewer
cases to find, not because the model got worse. Metric diffs only compare like
with like when the evaluation data is fixed. That's one reason for a fixed
benchmark set and a model registry (MLflow, next lesson).

## Part 4 – A parameter change

```bash
# edit params.yaml: train.model: logistic -> gbm
dvc repro            # prepare SKIPPED; only train + evaluate rerun
dvc params diff
dvc metrics diff     # roc_auc 0.8122 -> 0.8038: gradient boosting is NOT better here
git restore . && dvc checkout     # discard the change (git files AND DVC outputs)
```
Same mechanism as Part 3: DVC hashes every input (data, code, params) and
reruns only the stages downstream of a change. A fancier model not winning is
a real and common result. Say so out loud.

## Part 5 – Experiments without committing

```bash
# queue a 2 x 2 grid plus one more run, then execute 2 at a time
dvc exp run --queue -S train.model=gbm -S 'train.max_depth=2,4' -S 'train.learning_rate=0.05,0.1'
dvc exp run --queue -S train.C=0.1
dvc queue start -j 2
dvc queue status                   # wait until all show Success
dvc exp show --only-changed --sort-by roc_auc --sort-order desc
```
Logistic regression (`main`, 0.812) still beats every gbm variant (0.802–0.808).
To promote an experiment: `dvc exp apply <name>` and commit, or
`dvc exp branch <name> <branch>`.

**Where DVC experiments stop:** no UI, no shared server, no model registry.
That's what MLflow adds.

## Part 6 – Plots

```bash
dvc plots diff v1 -o plots_html    # ROC + PR curves, v1 vs now: open plots_html/index.html
```

## Part 7 – Time travel

```bash
git checkout v1 && dvc checkout
ls data/raw | wc -l      # 6 months
cat metrics.json         # the v1 numbers
git checkout main && dvc checkout
ls data/raw | wc -l      # 12 months
```

## Part 8 – Use a pinned version from Python

Typical use: a scoring service loads *exactly* the model tagged for release.
```python
import dvc.api, joblib, pandas as pd

print(dvc.api.params_show(rev="v1")["train"])     # what was it trained with?
print(dvc.api.metrics_show(rev="v1"))             # how did it score?

# file paths are relative to the git root, since this DVC project is in a subfolder
with dvc.api.open("01-dvc/model.pkl", repo="..", rev="v1", mode="rb") as f:
    model = joblib.load(f)

visits = pd.read_csv("data/raw/emr_2024-12.csv")
visits["lean_season"] = pd.to_datetime(visits["visit_date"]).dt.month.isin([6, 7, 8, 9]).astype(int)
risk = model.predict_proba(visits)[:, 1]
```
`repo` can also be a GitHub URL, so another machine can load the model without
cloning, given access to the DVC remote.

## Part 9 – Housekeeping

```bash
dvc gc --all-tags --all-branches -f     # drop cache not used by any tag or branch
```
Careful: `dvc gc -w` keeps **only the current workspace**, so old tagged models
vanish from the local cache and Part 8 fails until you `dvc pull` them back
from the remote.

## Optional – Import from a data registry

Teams often keep datasets in a dedicated registry repo and import pinned versions:
```bash
dvc import https://github.com/iterative/dataset-registry get-started/data.xml -o data/external.xml
cat data/external.xml.dvc          # records the source repo + exact revision
dvc update data/external.xml.dvc   # later: move to the registry's newer version
```

---

## Things to say out loud
- Git stores the *pointers* (`.dvc`, `dvc.lock`); DVC stores the *bytes*.
- DVC has two halves: **data versioning** (Parts 1, 3, 7) and **reproducible
  pipelines** (Parts 2, 4, 5). Say which one you're showing.
- Forgetting `dvc push` is the #1 mistake: teammates `dvc pull` and get nothing.
- DVC works for any file type. Here it's CSV; for images or audio, track the
  directory exactly as in Part 1.
- DVC doesn't validate data (Great Expectations), give experiments a UI or
  register models (MLflow), check fairness (Fairlearn), detect drift
  (Evidently), or schedule runs (Prefect/Airflow).

## Teasers for later lessons
Open `metrics_by_group.json` (sensitivity at one shared threshold):
- **Girls 0.53 vs boys 0.60.** In the simulator, MUAC reads lower for girls at
  the same WHZ, mirroring field studies where MUAC and WHZ disagree more for
  girls. → Fairlearn.
- **Addis Ababa: only ~2% of children flagged.** One global threshold, very
  different base rates. → Fairlearn.
- Add one broken month and rerun:
  ```bash
  python ../00-data/simulate_emr.py --start 2025-01 --scenario muac_mm --out data/raw
  dvc add data/raw && dvc repro      # roc_auc 0.81 -> 0.65, and no error anywhere
  ```
  The EMR started storing MUAC in mm (137 instead of 13.7). The pipeline ran
  green and produced a much worse model. Nothing stopped it. → Great Expectations.
  (Undo with `git restore . && dvc checkout`, then delete the 2025 file.)

## Exercises
1. Set `prepare.test_months: 3`. Which stages rerun? Why does `train` rerun?
2. Edit only `src/evaluate.py` (e.g. change a print). Which stages rerun?
3. Change `evaluate.alert_rate` to 0.3. What happens to sensitivity and PPV,
   and what does that mean for a clinic's workload?
4. Add month 2025-01 with `--scenario new_regions`. How many files does
   `dvc push` upload, and why?
