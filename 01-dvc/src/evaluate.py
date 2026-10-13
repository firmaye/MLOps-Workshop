import json, joblib, pandas as pd
from sklearn.metrics import accuracy_score, f1_score

model = joblib.load("model.pkl")
df = pd.read_csv("data/test.csv")
pred = model.predict(df.drop(columns="label"))
metrics = {"accuracy": round(accuracy_score(df["label"], pred), 4),
           "f1": round(f1_score(df["label"], pred), 4)}
json.dump(metrics, open("metrics.json", "w"), indent=2)
print(metrics)
