# MLflow cheat sheet (everything used in the workshop)

Mental model: an **experiment** holds **runs**; a run records params, metrics, tags,
artifacts and usually produces a **logged model**; the **registry** gives approved models
a durable name, versions and **aliases** (`@champion`) that software loads.

## Command line

| Command | What it does |
|---|---|
| `mlflow ui --port 5000` | Open the web UI on the local store (`mlflow.db` + `mlruns/` in the **current folder**). Switch the UI to *Model training* mode. |
| `mlflow server --backend-store-uri <db> --artifacts-destination <store> --host 0.0.0.0` | A shared tracking server for a team (database for runs/registry, object store or disk for files). |
| `export MLFLOW_TRACKING_URI=http://server:5000` | Point scripts and notebooks at a shared server instead of the local files. |
| `mlflow models serve -m "models:/gam-risk@champion" --port 5001 --env-manager local` | Serve a model as an HTTP API (`POST /invocations`). `--env-manager local` = use the current environment. |
| `export MLFLOW_DISABLE_TELEMETRY=true` | Turn off MLflow's anonymous usage data. |

## Tracking (Python)

| Call | What it does |
|---|---|
| `mlflow.set_experiment("gam-risk")` | Create or select the experiment that new runs go into. |
| `with mlflow.start_run(run_name="...") as run:` | Start a run; everything logged inside belongs to it. `run.info.run_id` is its ID. |
| `mlflow.log_params({...})` | Settings you chose (stored as text). |
| `mlflow.log_metrics({...})` | Numbers you measured; comparable and sortable across runs. |
| `mlflow.set_tags({...})` | Free-form labels: data version (`data_md5`), `git_commit`, owner... |
| `mlflow.log_dict(d, "file.json")` / `log_figure(fig, "plot.png")` | Save a dict or a matplotlib figure as an artifact (file) of the run. |
| `mlflow.log_input(mlflow.data.from_pandas(df, name=...), context="training")` | Record which dataset was used (schema, row count, a hash). |
| `mlflow.sklearn.log_model(model, name=..., signature=..., input_example=...)` | Save the trained model with its input contract. Returns info with `.model_uri` (`models:/m-...`). |
| `mlflow.sklearn.autolog()` | Log params and *training-set* metrics automatically on `.fit()`. A start, not enough. |
| `mlflow.search_runs(experiment_names=[...], filter_string=..., order_by=[...])` | Runs as a pandas DataFrame (`params.*`, `metrics.*`, `tags.*` columns). |
| `mlflow.search_logged_models(filter_string="source_run_id = '...'")` | Find the model a run produced. |

Options we needed on `log_model` (MLflow 3.17): `pyfunc_predict_fn="predict_proba"`
(return risks, not 0/1) and `skops_trusted_types=[...]` (allow specific classes in the safe
save format).

## Registry (Python, `client = mlflow.MlflowClient()`)

| Call | What it does |
|---|---|
| `mlflow.register_model(model_uri, "gam-risk")` | Add a model as a new **version** of a registered model (creates the name if new). |
| `client.set_registered_model_alias("gam-risk", "champion", version)` | Point an alias at a version. **Promotion and rollback are both this one call.** |
| `client.get_model_version_by_alias("gam-risk", "champion")` | Which version an alias points at (`.version`, `.run_id`, `.tags`). |
| `client.set_model_version_tag(name, version, key, value)` | Record approval status, benchmark, approver... |
| `client.update_model_version(name, version, description=...)` | Human-readable description of a version. |

## Loading a model

| URI | Meaning |
|---|---|
| `models:/gam-risk@champion` | Whatever version the `champion` alias points to (use this in applications). |
| `models:/gam-risk/2` | A specific registered version. |
| `models:/m-...` | A specific logged model, registered or not. |
| `runs:/<run_id>/<name>` | Older style: the model a run logged under that name (still works; registering this way prints a warning in MLflow 3). |

| Call | Returns |
|---|---|
| `mlflow.pyfunc.load_model(uri)` | A generic model; `.predict(df)` checks the signature. Ours returns `[P(no GAM), P(GAM)]`. |
| `mlflow.sklearn.load_model(uri)` | The original scikit-learn object (`.predict_proba`, etc.). |

## Query syntax (`filter_string`, and the UI search box)

```
params.model = 'gbm' and metrics.roc_auc > 0.805
tags.mlflow.runName = 'baseline-logistic'
params.test_until = '2024-12'
```
Params and tags are compared as text (quote the value); metrics as numbers.
