"""Shared code for the MLflow lesson: load data, build a model, evaluate it.

Same modelling as the DVC lesson (01-dvc/src), packaged as functions so the
notebooks and train.py can import them instead of copying code.
"""
import hashlib
import subprocess
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score, roc_curve
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

HERE = Path(__file__).parent
RAW = HERE / "data" / "raw"

NUMERIC = ["age_months", "weight_kg", "height_cm", "whz", "muac_cm", "recent_diarrhea",
           "recent_fever", "vaccinated_for_age", "currently_breastfed", "prior_sam_admission",
           "mother_age", "water_source_minutes", "household_size", "lean_season"]
CATEGORICAL = ["region", "residence", "sex", "birth_size", "mother_education"]
FEATURES = NUMERIC + CATEGORICAL
LABEL = "gam_within_90d"
GROUPS = ["sex", "age_band", "region"]


# ---------------------------------------------------------------- data

def simulate(start: str, months: int, scenario: str = "baseline", out: Path = RAW) -> None:
    """Generate monthly extracts with the shared simulator (skips files that already exist)."""
    missing = [m for m in pd.period_range(start, periods=months, freq="M")
               if not (out / f"emr_{m}.csv").exists()]
    for m in missing:
        subprocess.run([sys.executable, str(HERE.parent / "00-data" / "simulate_emr.py"),
                        "--start", str(m), "--scenario", scenario, "--out", str(out)],
                       check=True, capture_output=True)


def load_months(first: str, last: str, raw: Path = RAW) -> pd.DataFrame:
    """Load monthly files from `first` to `last` inclusive (YYYY-MM) and add derived columns."""
    files = [raw / f"emr_{m}.csv" for m in pd.period_range(first, last, freq="M")]
    df = pd.concat(pd.read_csv(f) for f in files)
    df["month"] = df["visit_date"].str[:7]
    df["lean_season"] = pd.to_datetime(df["visit_date"]).dt.month.isin([6, 7, 8, 9]).astype(int)
    df["age_band"] = pd.cut(df["age_months"], [-1, 5, 23, 59], labels=["0-5m", "6-23m", "24-59m"])
    df.attrs["files"] = files
    return df.reset_index(drop=True)


def fingerprint(df: pd.DataFrame) -> str:
    """Short hash identifying exactly which monthly files a dataframe came from.

    Plays the role of the md5 in DVC's data/raw.dvc: log it with a run and you can
    always tell which data a model saw. (In the capstone, the DVC hash itself is logged.)
    """
    h = hashlib.md5()
    for f in df.attrs["files"]:
        h.update(f.name.encode())
        h.update(hashlib.md5(f.read_bytes()).hexdigest().encode())
    return h.hexdigest()[:12]


# ---------------------------------------------------------------- model

def build_model(model: str = "logistic", C: float = 1.0, max_depth: int = 3,
                learning_rate: float = 0.1, n_estimators: int = 200):
    """Preprocessing + classifier in one sklearn Pipeline (identical to 01-dvc/src/train.py)."""
    if model == "logistic":
        clf = LogisticRegression(C=C, max_iter=1000)
    elif model == "gbm":
        clf = HistGradientBoostingClassifier(max_depth=max_depth, learning_rate=learning_rate,
                                             max_iter=n_estimators, random_state=0)
    else:
        raise ValueError(f"unknown model {model!r}")
    pre = ColumnTransformer([
        ("num", make_pipeline(SimpleImputer(strategy="median", add_indicator=True), StandardScaler()), NUMERIC),
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL),
    ])
    return make_pipeline(pre, clf)


# ---------------------------------------------------------------- evaluation

def _summary(y, score, flag):
    return {
        "n": int(len(y)),
        "prevalence": float(y.mean()),
        "roc_auc": float(roc_auc_score(y, score)) if 0 < y.sum() < len(y) else float("nan"),
        "sensitivity": float(flag[y == 1].mean()) if y.sum() else float("nan"),
        "ppv": float(y[flag].mean()) if flag.sum() else float("nan"),
        "alert_rate": float(flag.mean()),
    }


def evaluate(model, df: pd.DataFrame, alert_rate: float = 0.2):
    """Flag the top `alert_rate` share by risk; return (overall, by_group) metric dicts.

    sensitivity = share of children who developed GAM that were flagged
    ppv         = share of flagged children who developed GAM
    """
    y = df[LABEL].to_numpy()
    score = model.predict_proba(df[FEATURES])[:, 1]
    flag = score >= np.quantile(score, 1 - alert_rate)
    overall = _summary(y, score, flag)
    overall["pr_auc"] = float(average_precision_score(y, score))
    by_group = {col: {str(g): _summary(y[idx], score[idx], flag[idx])
                      for g, idx in df.groupby(col, observed=True).indices.items()}
                for col in GROUPS}
    return overall, by_group


def flat_group_metrics(by_group: dict, metrics=("sensitivity", "roc_auc")) -> dict:
    """{'sex': {'F': {...}}} -> {'sensitivity_sex_F': 0.53, ...}: MLflow metric names."""
    return {f"{m}_{col}_{g.replace(' ', '_')}": vals[m]
            for col, groups in by_group.items() for g, vals in groups.items() for m in metrics}


def roc_figure(model, df: pd.DataFrame, title: str = "ROC curve"):
    """A matplotlib ROC figure, for mlflow.log_figure."""
    score = model.predict_proba(df[FEATURES])[:, 1]
    fpr, tpr, _ = roc_curve(df[LABEL], score)
    fig, ax = plt.subplots(figsize=(4.5, 4.5))
    ax.plot(fpr, tpr, color="#2a78d6", linewidth=2)
    ax.plot([0, 1], [0, 1], color="#999999", linewidth=1, linestyle="--")
    ax.set(xlabel="false positive rate", ylabel="true positive rate (sensitivity)", title=title)
    ax.spines[["top", "right"]].set_visible(False)
    plt.close(fig)
    return fig


def git_commit() -> str:
    """Current git commit (so a run records which code produced it); 'unknown' outside git."""
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=HERE, check=True,
                              capture_output=True, text=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"
