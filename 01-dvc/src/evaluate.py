"""Stage 3 of 3: evaluate on the held-out months, overall and per group.

Input:  model.pkl, data/processed/test.csv, params.yaml (evaluate: section)
Output: metrics.json           overall numbers (DVC "metrics": compared by `dvc metrics diff`)
        metrics_by_group.json  the same numbers per sex, age band and region
        plots/roc.csv, plots/pr.csv   curves for `dvc plots`

Clinical framing: a clinic can only follow up a limited share of children. We flag
the `alert_rate` (e.g. 20%) highest-risk visits and ask:
  sensitivity = of the children who went on to develop GAM, what share did we flag?
  ppv         = of the children we flagged, what share went on to develop GAM?
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
y = df[LABEL].to_numpy()                                       # what actually happened (0/1)
score = model.predict_proba(df[NUMERIC + CATEGORICAL])[:, 1]   # predicted risk, 0..1

# One threshold for everyone: the risk score above which the top `alert_rate` share falls.
threshold = np.quantile(score, 1 - p["alert_rate"])
flag = score >= threshold                                      # True = clinic follows this child up


def summarise(y, score, flag):
    """Metrics for one set of visits (all of them, or one group)."""
    return {
        "n": int(len(y)),                                              # number of visits
        "prevalence": round(float(y.mean()), 4),                       # share who developed GAM
        "roc_auc": round(float(roc_auc_score(y, score)), 4)            # ranking quality, 0.5 = random
                   if 0 < y.sum() < len(y) else None,
        "sensitivity": round(float(flag[y == 1].mean()), 4) if y.sum() else None,
        "ppv": round(float(y[flag].mean()), 4) if flag.sum() else None,
        "alert_rate": round(float(flag.mean()), 4),                    # share of visits flagged
    }


overall = summarise(y, score, flag)
overall["pr_auc"] = round(float(average_precision_score(y, score)), 4)  # precision-recall area
json.dump(overall, open("metrics.json", "w"), indent=2)

# Same metrics within each group, using the SAME threshold as above.
by_group = {col: {str(g): summarise(y[idx], score[idx], flag[idx])
                  for g, idx in df.groupby(col, observed=True).indices.items()}
            for col in ["sex", "age_band", "region"]}
json.dump(by_group, open("metrics_by_group.json", "w"), indent=2)

# Curves for `dvc plots show` / `dvc plots diff`
Path("plots").mkdir(exist_ok=True)
fpr, tpr, _ = roc_curve(y, score)
pd.DataFrame({"fpr": fpr, "tpr": tpr}).to_csv("plots/roc.csv", index=False)
prec, rec, _ = precision_recall_curve(y, score)
pd.DataFrame({"recall": rec, "precision": prec}).to_csv("plots/pr.csv", index=False)

print("overall:", json.dumps(overall))
for col, groups in by_group.items():
    print(f"sensitivity by {col}:", {g: m["sensitivity"] for g, m in groups.items()})
