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

## Part 4 – The payoff: change a parameter

```bash
# edit params.yaml: change train.max_depth from 3 to 8
dvc repro            # ONLY train + evaluate rerun; prepare is skipped
dvc params diff
dvc metrics diff     # accuracy and f1, before vs after
git commit -am "Deeper trees"
```

## Part 5 – Time travel

```bash
git checkout v1
dvc checkout         # model.pkl and data revert to the v1 versions
cat metrics.json     # the old numbers
git checkout -       # back to the latest (then: dvc checkout)
```

## Things to say out loud in the workshop
- Git stores the *pointers* (`.dvc`, `dvc.lock`); DVC stores the *bytes*.
- `dvc.lock` records exact hashes, so a run is reproducible.
- Forgetting `dvc push` is the #1 mistake: teammates `dvc pull` and get nothing.
- DVC tracks files and pipelines. Experiment dashboards/registry are MLflow's job (next lesson).

## Exercises
1. Change `test_size` in `params.yaml`. Which stages rerun?
2. Edit only `src/evaluate.py`. Which stages rerun?
3. Run `python src/make_data.py 5000`, then `dvc add data/raw.csv` again. What changes in `raw.csv.dvc`?
