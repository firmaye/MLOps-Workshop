import joblib, pandas as pd, yaml
from sklearn.ensemble import RandomForestClassifier

p = yaml.safe_load(open("params.yaml"))["train"]
df = pd.read_csv("data/train.csv")
model = RandomForestClassifier(n_estimators=p["n_estimators"],
                               max_depth=p["max_depth"], random_state=0)
model.fit(df.drop(columns="label"), df["label"])
joblib.dump(model, "model.pkl")
