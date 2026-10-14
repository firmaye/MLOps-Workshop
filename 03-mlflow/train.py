"""Train one model and log everything about it to MLflow.

Used by the notebooks (imported) and from the command line, e.g.:
    python train.py --model gbm --max-depth 2 --learning-rate 0.05
    python train.py --model logistic --C 0.1 --run-name small-C

Run from this folder: MLflow stores runs in ./mlflow.db and ./mlruns.
"""
import argparse
import warnings

import mlflow
import mlflow.sklearn
from mlflow.models import infer_signature

import emr_model as em

EXPERIMENT = "gam-risk"
# Name each logged model by its algorithm, so the Models list is readable.
# (The *registered* model, "gam-risk", is a separate name: see 2_registry.ipynb.)
MODEL_NAMES = {"logistic": "logistic-regression", "gbm": "gradient-boosting"}

# Two harmless MLflow warnings that would otherwise appear on every run:
warnings.filterwarnings("ignore", message=".*Inferred schema contains integer column.*")
warnings.filterwarnings("ignore", message=".*dataset source can be interpreted in multiple ways.*")


def train_and_log(model="logistic", C=1.0, max_depth=3, learning_rate=0.1, n_estimators=200,
                  train_from="2024-01", train_until="2024-10", test_from="2024-11",
                  test_until="2024-12", alert_rate=0.2, run_name=None):
    """Train on [train_from, train_until], evaluate on [test_from, test_until], log one MLflow run.

    Returns (run_id, overall_metrics, model_uri). In MLflow 3 the model is its own object
    with its own URI (models:/m-...), linked to the run that produced it.
    """
    train = em.load_months(train_from, train_until)
    test = em.load_months(test_from, test_until)
    params = {"model": model, "alert_rate": alert_rate,
              "train_from": train_from, "train_until": train_until,
              "test_from": test_from, "test_until": test_until}
    params |= {"C": C} if model == "logistic" else {
        "max_depth": max_depth, "learning_rate": learning_rate, "n_estimators": n_estimators}

    mlflow.set_experiment(EXPERIMENT)
    with mlflow.start_run(run_name=run_name) as run:
        mlflow.log_params(params)                                    # what we chose
        mlflow.set_tags({"data_md5": em.fingerprint(train),          # which data
                         "git_commit": em.git_commit()})             # which code

        fitted = em.build_model(model, C, max_depth, learning_rate, n_estimators)
        fitted.fit(train[em.FEATURES], train[em.LABEL])

        overall, by_group = em.evaluate(fitted, test, alert_rate)
        mlflow.log_metrics({k: v for k, v in overall.items() if k != "n"})   # how it did
        mlflow.log_metrics(em.flat_group_metrics(by_group))                  # ... per group
        mlflow.log_dict(by_group, "metrics_by_group.json")                   # full detail
        mlflow.log_figure(em.roc_figure(fitted, test), "roc.png")

        mlflow.log_input(mlflow.data.from_pandas(train, source=str(em.RAW), name="emr_train",
                                                 targets=em.LABEL), context="training")
        info = mlflow.sklearn.log_model(                                     # the model itself
            fitted, name=MODEL_NAMES[model],
            # the input "contract": column names and types, checked on every prediction
            signature=infer_signature(test[em.FEATURES], fitted.predict_proba(test[em.FEATURES])),
            input_example=test[em.FEATURES].head(3),
            # loaded models return risk probabilities, not 0/1 labels
            pyfunc_predict_fn="predict_proba",
            # MLflow saves sklearn models with skops (safer than pickle) and refuses types
            # it hasn't been told to trust. Both are numpy/sklearn internals, listed with
            # skops.io.get_untrusted_types(): the encoder's dtype and the gbm tree predictor.
            skops_trusted_types=["numpy.dtype",
                                 "sklearn.ensemble._hist_gradient_boosting.predictor.TreePredictor"],
        )
        return run.info.run_id, overall, info.model_uri


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default="logistic", choices=["logistic", "gbm"])
    ap.add_argument("--C", type=float, default=1.0)
    ap.add_argument("--max-depth", type=int, default=3)
    ap.add_argument("--learning-rate", type=float, default=0.1)
    ap.add_argument("--n-estimators", type=int, default=200)
    ap.add_argument("--run-name")
    a = ap.parse_args()
    em.simulate("2024-01", 12)
    run_id, overall, model_uri = train_and_log(a.model, a.C, a.max_depth, a.learning_rate,
                                               a.n_estimators, run_name=a.run_name)
    print(f"run {run_id}: roc_auc={overall['roc_auc']:.4f} sensitivity={overall['sensitivity']:.4f}"
          f"  model {model_uri}")


if __name__ == "__main__":
    main()
