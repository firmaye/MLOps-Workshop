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

if p["model"] == "logistic":
    clf = LogisticRegression(C=p["C"], max_iter=1000)
elif p["model"] == "gbm":
    clf = HistGradientBoostingClassifier(max_depth=p["max_depth"], learning_rate=p["learning_rate"],
                                         max_iter=p["n_estimators"], random_state=0)
else:
    raise ValueError(f"unknown model {p['model']!r}")

# preprocessing lives inside the saved model, so serving gets raw EMR fields
pre = ColumnTransformer([
    ("num", make_pipeline(SimpleImputer(strategy="median", add_indicator=True), StandardScaler()), NUMERIC),
    ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL),
])
model = make_pipeline(pre, clf).fit(df[NUMERIC + CATEGORICAL], df[LABEL])
joblib.dump(model, "model.pkl")
print(f"trained {p['model']} on {len(df)} visits")
