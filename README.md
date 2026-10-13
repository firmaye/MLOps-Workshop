# MLOps Workshop

Hands-on lessons, one per tool, built around one running example: predicting
which children are at risk of acute malnutrition from (synthetic) Ethiopian
EMR data.

| # | Topic | Folder |
|---|-------|--------|
| 0 | Mock EMR data + drift scenarios | [`00-data/`](00-data/) |
| 1 | DVC: data, model and pipeline versioning | [`01-dvc/`](01-dvc/) |
| 2 | Great Expectations: data validation as a pipeline gate | [`02-great-expectations/`](02-great-expectations/) |

## Setup

**Python 3.10+ required; 3.12 recommended.** macOS ships Python 3.9, which
gets old versions of these tools (or none). The lessons were verified with
Python 3.12/3.13, DVC 3.67, scikit-learn 1.9, pandas 3.0, and GX 1.24.

Easiest: [uv](https://docs.astral.sh/uv/) installs Python and packages, and is fast:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh     # Windows: see the uv docs
uv python install 3.12
uv venv --python 3.12 .venv
source .venv/bin/activate                           # Windows: .venv\Scripts\activate
uv pip install -r requirements.txt
```

Or with a Python 3.12 you already have:
```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Check: `python --version && dvc --version && python -c "import great_expectations as gx; print(gx.__version__)"`
