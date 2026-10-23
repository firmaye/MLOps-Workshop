# The malnutrition use case, in two blocks

One running example (predict which children are at risk of acute malnutrition from synthetic
Ethiopian EMR data), taught in **two blocks**. Each block ends with one take-home exercise set, not
one per tool.

## Block A: Trust the data (DVC, Great Expectations)

*Question: when something is wrong with the model, can we tell which data and which code made it?
And can we stop bad data before it gets in?*

| Lesson | Core (do in the room) | Optional (read, or do at home) |
|---|---|---|
| [`01-dvc`](01-dvc/) | Parts 0–4 (version a growing dataset, the pipeline, new data, a parameter change), Part 8 (audit), Part 10 (the failure DVC can't see) | Parts 5, 6, 7, 9, 8b; "Sharing with a team" |
| [`02-great-expectations`](02-great-expectations/) | Parts 1–3 (write the suite, validate history, break things), Part 6 (gate the pipeline) | Part 4 (try a rule first), Part 5 (Data Docs) |

## Block B: Trust the model (MLflow, Fairlearn, Evidently, Prefect)

*Question: how do we track, check, watch and re-run a model every month?*

| Lesson | Core (do in the room) | Optional (read, or do at home) |
|---|---|---|
| [`03-mlflow`](03-mlflow/) | `1_tracking.ipynb`, `2_registry.ipynb` (register, promote, roll back) | Serving; "Should we serve with MLflow?"; central MLOps; gotchas; shared server |
| [`04-fairlearn`](04-fairlearn/) | the notebook, sections 1–4 (per-group metrics, the cause, the fix) | "Would a more flexible model fix it?" cell |
| [`05-evidently`](05-evidently/) | the notebook up to the gate and the performance check | "Does the choice of reference change the answer?" cell |
| [`06-prefect`](06-prefect/) | run `python pipeline.py timeline` and read the log; the Prefect UI | writing your own task; `serve` |

## Exercises

- Every lesson ends with exercises, **designed to be done at home** after the block. In the room, use the
  `PAUSE` questions and the cells above instead.
- If you do want to try one, pick one per block, not one per tool.
- Each lesson also has `exercise_solutions.ipynb` with a worked answer to every exercise. It ships without
  outputs: run it to see the answers.

## Where the helper code lives

Each lesson README has a "Helper functions in this lesson" table, so nothing in a notebook is a surprise.
The shared pieces are [`00-data/simulate_emr.py`](00-data/) (the data and the drift scenarios) and
[`03-mlflow/emr_model.py`](03-mlflow/emr_model.py) (the model, the metrics, the data and code fingerprints).
