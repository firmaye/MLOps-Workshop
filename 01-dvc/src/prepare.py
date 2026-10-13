"""Combine monthly EMR batches and split by time: the last N months are the test set.

A random split would leak future information into training. A model is always
trained on the past and used on the future, so we evaluate it that way.
"""
from pathlib import Path

import pandas as pd
import yaml

p = yaml.safe_load(open("params.yaml"))["prepare"]

df = pd.concat(pd.read_csv(f) for f in sorted(Path("data/raw").glob("emr_*.csv")))
df["month"] = df["visit_date"].str[:7]
df["lean_season"] = pd.to_datetime(df["visit_date"]).dt.month.isin([6, 7, 8, 9]).astype(int)
df["age_band"] = pd.cut(df["age_months"], [-1, 5, 23, 59], labels=["0-5m", "6-23m", "24-59m"])

months = sorted(df["month"].unique())
test_months = months[-p["test_months"]:]
is_test = df["month"].isin(test_months)

Path("data/processed").mkdir(parents=True, exist_ok=True)
df[~is_test].to_csv("data/processed/train.csv", index=False)
df[is_test].to_csv("data/processed/test.csv", index=False)
print(f"train: {months[0]}..{months[-p['test_months'] - 1]} ({(~is_test).sum()} visits)  "
      f"test: {test_months[0]}..{test_months[-1]} ({is_test.sum()} visits)")
