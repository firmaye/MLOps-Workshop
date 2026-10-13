import pandas as pd, yaml
from sklearn.model_selection import train_test_split

p = yaml.safe_load(open("params.yaml"))["prepare"]
df = pd.read_csv("data/raw.csv")
train, test = train_test_split(df, test_size=p["test_size"], random_state=p["seed"])
train.to_csv("data/train.csv", index=False)
test.to_csv("data/test.csv", index=False)
print(f"train={len(train)} test={len(test)}")
