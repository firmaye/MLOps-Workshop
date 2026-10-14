# MLOps Workshop

Hands-on lessons, one per tool, built around one running example: predicting
which children are at risk of acute malnutrition from (synthetic) Ethiopian
EMR data.

| # | Topic | Folder |
|---|-------|--------|
| 0 | Mock EMR data + drift scenarios; [notebook](00-data/explore_data.ipynb) to explore it | [`00-data/`](00-data/) |
| 1 | DVC: data, model and pipeline versioning ([cheat sheet](01-dvc/DVC_CHEATSHEET.md)) | [`01-dvc/`](01-dvc/) |
| 2 | Great Expectations: data validation as a pipeline gate | [`02-great-expectations/`](02-great-expectations/) |
| 3 | MLflow: experiment tracking, model registry, serving | [`03-mlflow/`](03-mlflow/) |

## Setup

### 1. Get your own copy of the repo

1. On GitHub, click **Fork** on this repo: you get `github.com/<you>/MLOps-Workshop`.
2. Clone **your fork** and connect it to the original, so you can pull lesson updates:
```bash
mkdir mlops && cd mlops          # the DVC lesson creates ../dvc-remote next to the clone
git clone https://github.com/<you>/MLOps-Workshop.git
cd MLOps-Workshop
git remote add upstream https://github.com/ydfriedman/MLOps-Workshop.git
git checkout -b work             # do the lessons on this branch; keep `main` = the lessons as published
```
- `origin` = your fork (you push here). `upstream` = the workshop repo (you only pull from it).
- **Getting lesson updates** during the workshop:
  ```bash
  git checkout main && git pull upstream main     # main = latest lessons
  git checkout work && git merge main             # bring them into your work branch
  ```
- **Starting over** (throws away everything on `work`, including DVC data and models):
  ```bash
  git checkout -f main             # -f: discard uncommitted changes
  git branch -D work
  git clean -fdx -e .venv          # delete untracked + ignored files (DVC cache, data, models); keep .venv
  rm -rf ../dvc-remote             # the DVC lesson's local remote
  git checkout -b work
  ```

### 2. Python environment

**Python 3.12.** (3.10+ works with `requirements.txt`, but the lock file and
all numbers in the READMEs were verified on 3.12.) macOS ships Python 3.9,
which is too old.

Easiest: [uv](https://docs.astral.sh/uv/) installs Python and packages, and is fast:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh     # Windows: see the uv docs
uv python install 3.12
uv venv --python 3.12 --seed .venv                  # --seed: include pip (MLflow warns without it)
source .venv/bin/activate                           # Windows: .venv\Scripts\activate
uv pip sync requirements.lock
```

Or with a Python 3.12 you already have:
```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.lock
```

Check: `python --version && dvc --version && python -c "import great_expectations as gx; print(gx.__version__)"`
(expect 3.12.x, 3.67.1, 1.24.0).

### Two requirements files
- `requirements.txt`: what the project depends on directly, loosely pinned. Edit this one.
- `requirements.lock`: every package, including dependencies of dependencies,
  pinned to the exact versions the lessons were verified with, for macOS,
  Windows and Linux. Install from this one.

After changing `requirements.txt`, regenerate the lock and re-verify the lessons:
```bash
uv pip compile requirements.txt --universal --python-version 3.12 -o requirements.lock
```
Same idea as DVC: `dvc.lock` pins the data and outputs, `requirements.lock`
pins the environment. Reproducibility needs both.
