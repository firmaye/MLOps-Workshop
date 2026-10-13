# 01 – DVC: versioning EMR data, models, and pipelines

**Scenario.** Health centres across Ethiopia record child visits in an EMR.
Every month a new extract arrives. We train a model that flags children at
risk of developing acute malnutrition (GAM) in the next 90 days, so the clinic
can prioritise follow-up. The data is synthetic, from `../00-data/simulate_emr.py`
(see [`00-data/README.md`](../00-data/README.md); to *look* at the data first,
open [`00-data/explore_data.ipynb`](../00-data/explore_data.ipynb)).

Before starting, follow the setup in the [main README](../README.md): your own
fork, and a `work` branch. Run everything from inside this `01-dvc/` folder.
Numbers shown are from a
verified run; yours should match exactly (the simulator is deterministic).
Every command used here is also listed in [`DVC_CHEATSHEET.md`](DVC_CHEATSHEET.md).

---

## Why DVC? The honest version

Git is great for code and bad for data: large files bloat the repo forever, and
git can't diff a 2 GB CSV meaningfully. So teams end up with
`data_final_v3_REAL.csv` on a shared drive, and nobody can say which data a
given model was trained on.

DVC keeps **git as the single history** but stores the **bytes** elsewhere:

```
  your laptop                                         shared storage
  ┌────────────────────────────────────────┐          ┌──────────────────────┐
  │ git repo:  code, dvc.yaml, params.yaml │ git push │ GitHub               │
  │            data/raw.dvc  (tiny pointer)│ ───────► │ (code + pointers)    │
  │            dvc.lock      (pointers)    │          └──────────────────────┘
  │                                        │          ┌──────────────────────┐
  │ .dvc/cache: the actual data + models,  │ dvc push │ DVC remote: S3, GCS, │
  │            stored by content hash      │ ───────► │ Azure, SSH, GDrive...│
  └────────────────────────────────────────┘          └──────────────────────┘
```

One git commit then pins *code + data + model + metrics* together. What that buys you:

| Value | Without DVC | With DVC |
|---|---|---|
| **Lineage / audit** | "Which data trained the model we used in June?" Nobody knows. | `git checkout <tag> && dvc checkout` gives the exact data, code, params and model. For a clinical model this is the core value. |
| **Sharing data** | Email a link, hope it's the right version | `git clone` + `dvc pull` gives everyone identical files |
| **Reproducibility** | A notebook run in some order on some data | `dvc repro` reruns the declared pipeline; `dvc.lock` records exact hashes |
| **Not wasting compute** | Rerun everything, or forget to rerun something | Only stages whose inputs changed rerun |
| **Rollback** | Hope someone kept a copy | Check out any previous version |

**When it's *not* worth it:** one person, small data, no pipeline, nobody will
ever ask "which version?". Its value grows with team size, data size, model
lifetime, and how much someone (a regulator, a ministry, a clinician) may ask you
to justify a model's output.

**What DVC doesn't do:** validate data (Great Expectations), give experiments a
UI or register models (MLflow), check fairness (Fairlearn), detect drift
(Evidently), schedule runs (Prefect/Airflow).

---

## Part 0 – Setup

```bash
# DVC sends anonymous usage statistics by default. To opt out, either:
dvc config --global core.analytics false   # permanently, for every DVC project on this machine
# or: export DVC_NO_ANALYTICS=1            # just for this terminal session
```

## Part 1 – Version a growing dataset

```bash
dvc init --subdir                  # make this folder a DVC project; --subdir because it's inside a
                                   #   bigger git repo (normally you'd run `dvc init` at the repo root)
git commit -m "Initialise DVC"     # dvc init already staged its files (.dvc/config, .dvcignore)

# The first six monthly extracts arrive (Jan-Jun 2024, 2000 visits each)
python ../00-data/simulate_emr.py --start 2024-01 --months 6 --out data/raw

dvc add data/raw                   # 1. hash every file, copy it into .dvc/cache
                                   # 2. write the pointer file data/raw.dvc
                                   # 3. add data/raw to data/.gitignore so git ignores the real files
cat data/raw.dvc                   # the pointer: one hash for the whole folder + nfiles: 6
git add data/raw.dvc data/.gitignore
git commit -m "EMR visits Jan-Jun 2024"   # git now records WHICH version of the data, not the data

dvc remote add -d storage ../../dvc-remote    # where `dvc push` sends data; -d = make it the default.
                                               #   A local folder stands in for S3/GCS/Azure/GDrive
git add .dvc/config && git commit -m "Add remote"   # the remote's address lives in .dvc/config, in git
dvc push                           # upload cached data to the remote: "7 files pushed"
                                   #   (6 CSVs + 1 directory manifest, explained below)
```

### Under the hood: what is that hash?

```yaml
# data/raw.dvc
outs:
- md5: 1d72721a38d0ab9f98abf9a425b2921d.dir   # <- the ID of this version of the folder
  size: 1346145
  nfiles: 6
  path: raw
```
Yes: **the md5 is the identity of the data version.** Change one byte in one file
and the hash changes. It's also the *address* in the cache:

```bash
find .dvc/cache -type f            # files/md5/1d/72721a38...dir   <- the folder's manifest
                                   # files/md5/78/529d5cf2...      <- emr_2024-01.csv
                                   # ... one file per CSV, named by ITS md5
cat .dvc/cache/files/md5/1d/72721a38d0ab9f98abf9a425b2921d.dir
                                   # [{"md5": "78529d5c...", "relpath": "emr_2024-01.csv"}, ...]
md5sum data/raw/emr_2024-01.csv    # 78529d5c... : same hash, so same content
                                   # (macOS: `md5 data/raw/emr_2024-01.csv`)
```
So `raw.dvc` → manifest `.dir` → one cache file per CSV. This is *content
addressing*: identical files are stored once, and adding a month only adds that
month's file plus a new manifest. That's why Part 3 pushes 7 files, not 12.
The remote has exactly the same layout as `.dvc/cache`.

## Part 2 – The pipeline

Read `dvc.yaml` (the stages and what each reads/writes) and `params.yaml` (the
settings) first. Both are commented.

| Stage | What it does | Why it matters |
|---|---|---|
| `prepare` | Combines monthly files; **temporal split**: last 2 months = test | A random split leaks the future into training |
| `train` | Logistic regression or gradient boosting; preprocessing saved inside the model | Whoever uses the model can send raw EMR fields |
| `evaluate` | Flags the top 20% riskiest visits (clinic capacity); reports sensitivity / PPV overall and per group | A clinically meaningful metric, not just accuracy |

```bash
dvc dag              # draw the stage graph: data/raw.dvc -> prepare -> train -> evaluate
dvc repro            # run every stage whose inputs changed (here: all of them, first run)
```
Output, explained:
```
train: 2024-01..2024-04 (8000 visits)  test: 2024-05..2024-06 (4000 visits)    <- prepare
trained logistic on 8000 visits                                                 <- train
overall: {"n": 4000, "prevalence": 0.12, "roc_auc": 0.8022, "sensitivity": 0.5521, "ppv": 0.3312, ...}
sensitivity by sex: {'F': 0.5146, 'M': 0.5892}                                  <- evaluate
sensitivity by age_band: {'0-5m': 0.431, '24-59m': 0.4844, '6-23m': 0.6054}
sensitivity by region: {'Addis Ababa': 0.0714, 'Afar': 0.5957, ...}
```
- **overall**: `roc_auc` = how well the model *ranks* risky above non-risky
  children (0.5 = random, 1.0 = perfect). `sensitivity` = share of children who
  developed GAM that we flagged. `ppv` = share of flagged children who developed GAM.
- **per-group lines are sensitivity, not AUC**: of the girls who developed GAM,
  we flagged 51%; of the boys, 59%. Full per-group numbers (AUC, PPV, ...) are in
  `metrics_by_group.json`.

Now save this state:
```bash
git status --short                 # what repro changed: dvc.lock, metrics, plots, and two .gitignore
                                   #   files (DVC gitignores its outputs: model.pkl, data/processed)
git add dvc.lock .gitignore data/.gitignore metrics.json metrics_by_group.json plots
git commit -m "Baseline model"     # dvc.lock = exact hashes of every input and output of this run
git status --short                 # empty = everything committed (needed before switching versions)
git tag v1                         # give this commit a permanent, human-readable name
dvc push                           # upload the new outputs (processed data, model.pkl)
git push -u origin work --tags     # upload code + pointers (+ tags) to YOUR fork on GitHub
dvc repro                          # nothing changed -> "Data and pipelines are up to date."
```

**`git tag`**: a named bookmark on one commit. `v1` will always mean "this exact
commit", so `git checkout v1` later is easier than remembering `eb86ed3`.
Think of it as labelling a checkpoint you may want to return to, compare
against, or say "this is the model we deployed".

**`dvc push` is not `git push`.** They are separate commands to separate places:
`git push` sends code and pointer files to GitHub; `dvc push` sends the actual
data and models to the DVC remote. Forget `dvc push` and your teammate's
`dvc pull` fails: the pointer exists, the data doesn't. Check with
`dvc status --cloud` (lists anything not yet pushed).
DVC can install git hooks (`dvc install`) so that `git push` also runs `dvc push`,
but they don't work when the DVC project is in a subfolder, as here.

## Part 3 – New data arrives (the core DVC use case)

```bash
python ../00-data/simulate_emr.py --start 2024-07 --months 6 --out data/raw   # Jul-Dec 2024
dvc status           # "prepare: changed deps: modified: data/raw": DVC noticed the new files
dvc add data/raw     # new folder hash -> data/raw.dvc changes
dvc push             # 7 files pushed: only the 6 NEW months + the new manifest
dvc repro            # all stages rerun: the data feeds everything
dvc diff             # what changed vs the last commit: 6 files added; processed data + model modified
dvc metrics diff     # compare metrics.json: last commit (HEAD) vs your current files (workspace)
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
with like when the evaluation data is fixed.

## Part 4 – A parameter change

```bash
# edit params.yaml: train.model: logistic -> gbm
dvc repro            # prepare SKIPPED (its inputs didn't change); train + evaluate rerun
dvc params diff      # train.model: logistic -> gbm
dvc metrics diff     # roc_auc 0.8122 -> 0.8038: gradient boosting is NOT better here
```
Same mechanism as Part 3: DVC hashes every input (data, code, params) and
reruns only the stages downstream of a change.

**Decision: discard it.** The gbm model is worse, so go back to the committed state:
```bash
git restore .        # git files back to the last commit: params.yaml, dvc.lock, metrics.json, plots
dvc checkout         # DVC files back to what dvc.lock says: model.pkl is the logistic model again
```
You need both: git restores the *pointers*, `dvc checkout` makes the real files
match them. (If gbm had been better, you'd commit instead.)

## Part 5 – Comparing more than two versions

`dvc metrics diff` with no arguments compares **HEAD** (your last commit) with
the **workspace** (current files, possibly uncommitted). You can compare any two
commits or tags, or list all of them:

```bash
dvc metrics diff v1 v2-data        # any two versions
dvc metrics show --all-tags        # one row per tag: a table of every model you've tagged
```
```
Revision    Path          ...  ppv     pr_auc    prevalence    roc_auc    sensitivity
workspace   metrics.json  ...  0.2587  0.3375    0.0907        0.8122     0.5702
v1          metrics.json  ...  0.3312  0.3736    0.12          0.8022     0.5521
v2-data     metrics.json  ...  0.2587  0.3375    0.0907        0.8122     0.5702
```
Add a third model: commit it, tag it (`v3-...`), and it appears as another row.

**Is this a model registry?** No, and it's fair to say so. It's a lightweight
history of metrics stored in git, useful for "did this change help?" (and in CI
on pull requests). It has no UI, no stage labels like *staging* / *production*,
no approvals. MLflow (next lesson) does that properly; DVC keeps the data lineage.

## Part 6 – Experiments without committing (optional for DVC regulars)

Every Part 4–style trial normally means edit, run, commit-or-discard. DVC
experiments let you try many settings without touching git history:
```bash
dvc exp run -n try-c01 -S train.C=0.1      # -n names it; -S overrides a param for this run only
dvc exp run --queue -S train.model=gbm -S 'train.max_depth=2,4' -S 'train.learning_rate=0.05,0.1'
                                           # queue a 2 x 2 grid (4 runs), don't run yet
dvc queue start -j 2                       # run the queue, 2 at a time
dvc queue status                           # wait until all show Success
dvc exp show --only-changed --sort-by roc_auc --sort-order desc   # compare all runs as a table
```
Logistic regression (your `work` branch, 0.812) still beats every gbm variant (0.802–0.808).

**Promoting an experiment** = turning the one you chose into a normal commit:
```bash
dvc exp apply try-c01      # put its params, dvc.lock, metrics and model into your workspace
git add -A && git commit -m "Use C=0.1"
```
Experiments are stored as hidden git refs, not commits, so until you promote
one it doesn't appear in `git log`. Worth showing if your participants use DVC;
otherwise skip, since MLflow covers experiment tracking with a UI.

## Part 7 – Plots

```bash
dvc plots diff v1 -o plots_html    # ROC + PR curves, v1 vs now; open plots_html/index.html
```

## Part 8 – The audit question: which data made this model?

*"In June the model flagged a child who wasn't followed up and later became
severely malnourished. Which model was running, and what was it trained on?"*

```bash
git log --oneline --decorate       # find the version: tags show as (tag: v1), (tag: v2-data)
git checkout v1                    # code, params, pointers as they were at v1
dvc checkout                       # data, processed files, model.pkl as they were at v1
ls data/raw | wc -l                # 6 months: Jan-Jun 2024
cat metrics.json                   # how it scored at the time
cat params.yaml                    # how it was configured
git checkout - && dvc checkout     # back to the present (`-` = the branch you were on)
ls data/raw | wc -l                # 12 months
```
If the data was pushed, a colleague with a fresh clone can do the same thing
(`git checkout v1 && dvc pull`). This is the question DVC exists to answer.

### 8b (optional) – Read a pinned version from code, without checking out

Same idea, from Python. Typical use: a scoring service or another team loads
*exactly* the model tagged for release, without cloning and checking out.
```python
import dvc.api, joblib

print(dvc.api.params_show(rev="v1")["train"])     # what was v1 trained with?
print(dvc.api.metrics_show(rev="v1"))             # how did it score?

# file paths are relative to the git root, since this DVC project is in a subfolder
with dvc.api.open("01-dvc/model.pkl", repo="..", rev="v1", mode="rb") as f:
    model_v1 = joblib.load(f)                     # the exact v1 model object
```
`repo` can also be a GitHub URL, given access to the DVC remote.

## Part 9 – Housekeeping

```bash
dvc gc --all-tags --all-branches -f     # delete cached files no tag or branch points to
```
Careful: `dvc gc -w` keeps **only the current workspace**, so old tagged models
vanish from the local cache (and Part 8b fails) until you `dvc pull` them back.

---

## Sharing with a team: remotes and data registries

**Remote** = where `dvc push` puts the bytes. What teams actually use:

| Setting | Typical remote |
|---|---|
| Cloud teams | S3 / GCS / Azure Blob bucket, access via the cloud's IAM roles |
| On-premises (e.g. a ministry data centre) | an SSH server, a network share, or MinIO (self-hosted, S3-compatible) |
| Small teams / workshops | Google Drive, or a hosted service such as DagsHub |

Everyone points at the same remote (it's in `.dvc/config`, in git), so `git pull`
+ `dvc pull` gives everyone the same data. Credentials stay out of git
(`dvc remote modify --local ...` writes them to `.dvc/config.local`, which is gitignored).

**Data registry** = an ordinary git + DVC repository whose *only job* is to hold
curated datasets, e.g. `moh-nutrition-data` containing `emr_extracts/`. It's
not a server or a special DVC product:
- **git** (GitHub) holds the `.dvc` pointer files and history: the *metadata*;
- the **registry's DVC remote** (a bucket) holds the *data*.

Projects consume a pinned version:
```bash
dvc import https://github.com/<org>/moh-nutrition-data emr_extracts -o data/raw --rev v2024.12
cat data/raw.dvc          # records the source repo + exact commit: lineage across repos
dvc update data/raw.dvc   # later: move to the registry's newest version, deliberately
```
`dvc import` downloads from the registry's remote; your project's `.dvc` file
remembers where it came from. One team curates and validates the data; many
projects use it; everyone can say exactly which release they trained on.
(`dvc get` downloads the same way but without recording the source.)

---

## Things to say out loud
- Git stores the *pointers* (`.dvc`, `dvc.lock`); DVC stores the *bytes*.
- DVC has two halves: **data versioning** (Parts 1, 3, 8) and **reproducible
  pipelines** (Parts 2, 4, 6). Say which one you're showing.
- Forgetting `dvc push` is the #1 mistake.
- DVC works for any file type. Here it's CSV; for images or audio, track the
  directory exactly as in Part 1.

## Teasers for later lessons
Open `metrics_by_group.json` (sensitivity at one shared threshold):
- **Girls 0.53 vs boys 0.60.** In the simulator, MUAC reads lower for girls at
  the same WHZ (see the notebook), mirroring field studies where MUAC and WHZ
  disagree more for girls. → Fairlearn.
- **Addis Ababa: only ~2% of children flagged.** One global threshold, very
  different base rates. → Fairlearn.
- Add one broken month and rerun:
  ```bash
  python ../00-data/simulate_emr.py --start 2025-01 --scenario muac_mm --out data/raw
  dvc add data/raw && dvc repro      # roc_auc 0.81 -> 0.65, and no error anywhere
  ```
  The EMR started storing MUAC in mm (137 instead of 13.7). The pipeline ran
  green and produced a much worse model. Nothing stopped it. → Great Expectations.
  (Undo: `rm data/raw/emr_2025-01.csv && dvc add data/raw && dvc repro`.)

## Exercises
1. Set `prepare.test_months: 3`. Which stages rerun? Why does `train` rerun?
2. Edit only `src/evaluate.py` (e.g. change a print). Which stages rerun?
3. Change `evaluate.alert_rate` to 0.3. What happens to sensitivity and PPV,
   and what does that mean for a clinic's workload?
4. Add month 2025-01 with `--scenario new_regions`. How many files does
   `dvc push` upload, and why?
5. Delete `data/raw/emr_2024-03.csv` by accident. How do you get it back?
   (Hint: `dvc checkout`.) What if you also deleted `.dvc/cache`?
