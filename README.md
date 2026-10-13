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
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```
