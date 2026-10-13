"""Overall and per-group metrics, plus curves for `dvc plots`.

Clinical framing: a clinic can follow up a limited share of children. We flag
the top `alert_rate` fraction by risk and ask what share of the children who
go on to develop GAM we caught (sensitivity) and how many flags were right (PPV).
"""
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import yaml
from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score, roc_curve

from features import CATEGORICAL, LABEL, NUMERIC

p = yaml.safe_load(open("params.yaml"))["evaluate"]
model = joblib.load("model.pkl")
df = pd.read_csv("data/processed/test.csv")
y = df[LABEL].to_numpy()
score = model.predict_proba(df[NUMERIC + CATEGORICAL])[:, 1]
threshold = np.quantile(score, 1 - p["alert_rate"])
flag = score >= threshold


def summarise(y, score, flag):
    return {
        "n": int(len(y)),
        "prevalence": round(float(y.mean()), 4),
        "roc_auc": round(float(roc_auc_score(y, score)), 4) if 0 < y.sum() < len(y) else None,
        "sensitivity": round(float(flag[y == 1].mean()), 4) if y.sum() else None,
        "ppv": round(float(y[flag].mean()), 4) if flag.sum() else None,
        "alert_rate": round(float(flag.mean()), 4),
    }


overall = summarise(y, score, flag)
overall["pr_auc"] = round(float(average_precision_score(y, score)), 4)
json.dump(overall, open("metrics.json", "w"), indent=2)

by_group = {col: {str(g): summarise(y[idx], score[idx], flag[idx])
                  for g, idx in df.groupby(col, observed=True).indices.items()}
            for col in ["sex", "age_band", "region"]}
json.dump(by_group, open("metrics_by_group.json", "w"), indent=2)

Path("plots").mkdir(exist_ok=True)
fpr, tpr, _ = roc_curve(y, score)
pd.DataFrame({"fpr": fpr, "tpr": tpr}).to_csv("plots/roc.csv", index=False)
prec, rec, _ = precision_recall_curve(y, score)
pd.DataFrame({"recall": rec, "precision": prec}).to_csv("plots/pr.csv", index=False)

print(json.dumps(overall))
for col, groups in by_group.items():
    print(col, {g: m["sensitivity"] for g, m in groups.items()})
