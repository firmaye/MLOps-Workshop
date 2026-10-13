# 01 – DVC: versioning data and pipelines

A tiny classifier pipeline: `raw.csv -> prepare -> train -> evaluate -> metrics.json`.
The project ships **without** DVC set up. You add it step by step below.

Run everything from inside this `01-dvc/` folder.

## Part 1 – Version a data file

```bash
dvc init --subdir                  # this folder lives inside a bigger git repo
git commit -m "Initialise DVC in 01-dvc"

python src/make_data.py 1000       # pretend we "downloaded" a dataset
dvc add data/raw.csv               # moves it into the DVC cache
cat data/raw.csv.dvc               # tiny pointer file: md5 hash + size
git add data/raw.csv.dvc data/.gitignore
git commit -m "Track raw data with DVC"
```
**Look:** `git status` no longer shows `raw.csv`. Git holds only the pointer.

## Part 2 – A remote (shared storage)

```bash
dvc remote add -d storage ../../dvc-remote   # a local folder stands in for S3/GCS
git add .dvc/config && git commit -m "Add DVC remote"
dvc push                                      # upload data to the remote
```
Prove it works for a "teammate":
```bash
rm -rf data/raw.csv .dvc/cache
dvc pull                                      # data comes back
```

## Part 3 – A pipeline

`dvc.yaml` already defines three stages. Read it, then:
```bash
dvc repro            # runs prepare -> train -> evaluate
cat metrics.json
dvc dag              # draw the pipeline
git add dvc.lock .gitignore metrics.json
git commit -m "First pipeline run" && git tag v1
dvc push
dvc repro            # nothing changed -> everything skipped
```

## Part 4 – What happens when an input changes

DVC treats **everything** a stage depends on as an input: data files, code, and
parameters. Each is hashed; if a hash changes, that stage and everything
downstream reruns. We'll change two different kinds of input.

### 4a – A data change (the core DVC use case)
New data arrives: twice as many rows.
```bash
python src/make_data.py 2000
dvc add data/raw.csv
dvc status           # "prepare: changed deps: modified: data/raw.csv"
dvc repro            # ALL three stages rerun - the data feeds everything
dvc diff             # which tracked files changed (raw, train, test, model)
dvc metrics diff     # how the new data moved accuracy / f1
git add -A && git commit -m "Retrain on 2000 rows" && git tag v2-data
dvc push
```

### 4b – A parameter change (DVC as a reproducible pipeline)
```bash
# edit params.yaml: change train.max_depth from 3 to 8
dvc repro            # ONLY train + evaluate rerun; prepare is skipped
dvc params diff
dvc metrics diff
git commit -am "Deeper trees"
```
**Point to make:** in 4a the data changed, so everything reran. In 4b only a
hyperparameter changed, so DVC skipped `prepare`. Same mechanism, different
inputs.

## Part 5 – Time travel

```bash
git checkout v1
dvc checkout         # data, model.pkl revert to the v1 versions
wc -l data/raw.csv   # 1001 lines: the original 1000-row dataset
cat metrics.json     # the old numbers
git checkout main && dvc checkout
```

## Part 6 (optional) – Read any version from Python

No checkout needed: read a file as it was at any git revision.
```python
import dvc.api, pandas as pd

for rev in ["v1", "v2-data"]:
    # paths are relative to the git root, since this DVC project is in a subfolder
    with dvc.api.open("01-dvc/data/raw.csv", repo="..", rev=rev) as f:
        print(rev, len(pd.read_csv(f)))     # v1 1000, v2-data 2000
```
`repo` can also be a GitHub URL, so a training script on another machine can
load a pinned dataset version straight from the remote.

## Part 7 (optional) – Import data from another repo

Teams often keep datasets in a dedicated "data registry" repo and import a
pinned version of a dataset into each project:
```bash
dvc list https://github.com/iterative/dataset-registry get-started
dvc import https://github.com/iterative/dataset-registry \
    get-started/data.xml -o data/external.xml
cat data/external.xml.dvc   # records the source repo + exact revision
dvc update data/external.xml.dvc   # later: pull the registry's newer version
```
`dvc get` does the same download without tracking where it came from.

## Things to say out loud in the workshop
- Git stores the *pointers* (`.dvc`, `dvc.lock`); DVC stores the *bytes*.
- DVC has two halves: **data versioning** (add/push/pull/checkout) and
  **reproducible pipelines** (dvc.yaml/repro). Say which one you're showing.
- `dvc.lock` records exact hashes, so a run is reproducible.
- Forgetting `dvc push` is the #1 mistake: teammates `dvc pull` and get nothing.
- DVC tracks files and pipelines. Experiment dashboards and model registry are
  MLflow's job; scheduling is Airflow/Prefect's job.

## Exercises
1. Change `test_size` in `params.yaml`. Which stages rerun?
2. Edit only `src/evaluate.py`. Which stages rerun?
3. Run `python src/make_data.py 5000`, then `dvc add data/raw.csv` again. What
   changes in `raw.csv.dvc`? Now `git checkout v2-data && dvc checkout` - how
   many rows?
