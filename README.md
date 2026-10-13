# MLOps Workshop

Hands-on lessons, one per tool, built around one running example: predicting
which children are at risk of acute malnutrition from (synthetic) Ethiopian
EMR data.

| # | Topic | Folder |
|---|-------|--------|
| 0 | Mock EMR data + drift scenarios; [notebook](00-data/explore_data.ipynb) to explore it | [`00-data/`](00-data/) |
| 1 | DVC: data, model and pipeline versioning ([cheat sheet](01-dvc/DVC_CHEATSHEET.md)) | [`01-dvc/`](01-dvc/) |
| 2 | Great Expectations: data validation as a pipeline gate | [`02-great-expectations/`](02-great-expectations/) |

## Setup

**Python 3.12.** (3.10+ works with `requirements.txt`, but the lock file and
all numbers in the READMEs were verified on 3.12.) macOS ships Python 3.9,
which is too old.

Easiest: [uv](https://docs.astral.sh/uv/) installs Python and packages, and is fast:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh     # Windows: see the uv docs
uv python install 3.12
uv venv --python 3.12 .venv
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
