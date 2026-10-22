"""Stage 1 of 3: combine the monthly EMR extracts and split them by time.

Input:  data/raw/emr_YYYY-MM.csv   (one file per month, tracked by `dvc add`)
Output: data/processed/train.csv, data/processed/test.csv

The most recent `test_months` months become the test set. A random split would
put future visits into training; in real use a model is always trained on the
past and applied to the future, so we evaluate it the same way.
"""
from pathlib import Path

import pandas as pd
import yaml

# Read this stage's settings from params.yaml. DVC tracks the `prepare:` section,
# so changing test_months makes `dvc repro` rerun this stage.
p = yaml.safe_load(open("params.yaml"))["prepare"]

# Load every monthly file into one table (sorted so the order never changes).
df = pd.concat(pd.read_csv(f) for f in sorted(Path("data/raw").glob("emr_*.csv")))

# Derived columns:
df["month"] = df["visit_date"].str[:7]                                  # "2024-07"
df["lean_season"] = pd.to_datetime(df["visit_date"]).dt.month.isin([6, 7, 8, 9]).astype(int)  # 1 in Jun-Sep
df["age_band"] = pd.cut(df["age_months"], [-1, 5, 23, 59],              # for per-group evaluation
                        labels=["0-5m", "6-23m", "24-59m"])

# Temporal split: the last N months are the test set, everything before is training.
months = sorted(df["month"].unique())
test_months = months[-p["test_months"]:]
is_test = df["month"].isin(test_months)

Path("data/processed").mkdir(parents=True, exist_ok=True)
df[~is_test].to_csv("data/processed/train.csv", index=False)
df[is_test].to_csv("data/processed/test.csv", index=False)
print(f"train: {months[0]}..{months[-p['test_months'] - 1]} ({(~is_test).sum()} visits)  "
      f"test: {test_months[0]}..{test_months[-1]} ({is_test.sum()} visits)")
