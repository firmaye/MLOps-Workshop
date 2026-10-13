"""Create a fake raw dataset (stands in for 'data you downloaded')."""
import sys
import pandas as pd
from sklearn.datasets import make_classification

n_rows = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
X, y = make_classification(n_samples=n_rows, n_features=8, n_informative=5,
                           flip_y=0.1, random_state=0)
df = pd.DataFrame(X, columns=[f"f{i}" for i in range(8)])
df["label"] = y
df.to_csv("data/raw.csv", index=False)
print(f"wrote data/raw.csv with {n_rows} rows")
