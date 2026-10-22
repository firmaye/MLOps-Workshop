"""Stage 2 of 3: train a risk model.

Input:  data/processed/train.csv, params.yaml (train: section)
Output: model.pkl  (preprocessing + classifier in one object)
"""
import joblib
import pandas as pd
import yaml
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from features import CATEGORICAL, LABEL, NUMERIC

p = yaml.safe_load(open("params.yaml"))["train"]
df = pd.read_csv("data/processed/train.csv")

# Choose the classifier from params.yaml, so experiments are a config change, not a code change.
if p["model"] == "logistic":
    clf = LogisticRegression(C=p["C"], max_iter=1000)
elif p["model"] == "gbm":   # gradient-boosted trees
    clf = HistGradientBoostingClassifier(max_depth=p["max_depth"], learning_rate=p["learning_rate"],
                                         max_iter=p["n_estimators"], random_state=0)
else:
    raise ValueError(f"unknown model {p['model']!r}")

# Preprocessing:
#   numeric columns: fill gaps with the median (and add a "was missing" flag, e.g. MUAC
#                    under 6 months), then scale to mean 0 / std 1
#   categorical:     one column per category (region=Afar, region=Somali, ...);
#                    unseen categories at prediction time are ignored instead of crashing
pre = ColumnTransformer([
    ("num", make_pipeline(SimpleImputer(strategy="median", add_indicator=True), StandardScaler()), NUMERIC),
    ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL),
])

# Preprocessing and classifier are saved together, so whoever uses model.pkl can pass
# raw EMR columns and gets exactly the same transformations as training.
model = make_pipeline(pre, clf).fit(df[NUMERIC + CATEGORICAL], df[LABEL])
joblib.dump(model, "model.pkl")
print(f"trained {p['model']} on {len(df)} visits")
