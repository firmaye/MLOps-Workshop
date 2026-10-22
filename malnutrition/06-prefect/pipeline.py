"""The monthly MLOps pipeline for the malnutrition-risk model, orchestrated with Prefect.

Every month a new EMR extract arrives. The pipeline:

  1. ingest       get the month's extract (retries if the EMR export fails)
  2. validate     Great Expectations gate; a broken month is QUARANTINED and the run stops
  3. version      DVC tracks the accepted data (the data version is recorded everywhere)
  4. score        risk for every visit with the MLflow model aliased @champion
  5. monitor      Evidently gate on the new batch (drift, missing values)
  6. performance  outcomes arrive ~3 months later: check that month's predictions
  7. retrain      if performance slipped: train a challenger on recent months, compare on
                  a fixed benchmark (ROC-AUC, calibration, per-sex sensitivity with
                  Fairlearn) and promote it only if the written rule says so
  8. report       one row per month in reports/monitoring_log.csv + a Prefect artifact

Run from this folder (environment active), with a Prefect server running (see README):
    python pipeline.py bootstrap                     # 2024 history + first champion
    python pipeline.py month 2025-03 new_regions     # one month, one scenario
    python pipeline.py timeline                      # Jan 2025 - Mar 2026, scripted events
    python pipeline.py serve                         # schedule: every month, 06:00 on the 2nd
"""
import json
import shutil
import subprocess
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from prefect import flow, get_run_logger, task
from prefect.artifacts import create_markdown_artifact, create_table_artifact

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "03-mlflow"))               # data / model / evaluation helpers
sys.path.insert(0, str(ROOT / "02-great-expectations"))   # the GX gate from lesson 02
warnings.filterwarnings("ignore")

import emr_model as em            # noqa: E402

# ------------------------------------------------------------------ settings (the "policy")

TIMELINE = {"2025-01": "baseline", "2025-02": "messy_export", "2025-03": "new_regions"} | {
    m: "concept_shift" for m in [f"2025-{i:02d}" for i in range(4, 13)] + ["2026-01", "2026-02", "2026-03"]}
OUTCOME_DELAY = 3            # months until we know who developed GAM
CAPACITY = 0.20              # share of visits the clinics can follow up
TRAIN_WINDOW = 4             # challengers train on the most recent N months with outcomes
CALIBRATION_OK = (0.67, 1.5) # observed / predicted GAM rate outside this -> performance alert
MIN_AUC = 0.75
MODEL_NAME = "gam-risk"
REFERENCE_MONTHS = [str(p) for p in pd.period_range("2024-01", "2024-12", freq="M")]  # approved drift reference

DATA = HERE / "data"
INCOMING, QUARANTINE, RAW, PRED = DATA / "incoming", DATA / "quarantine", DATA / "raw", DATA / "predictions"
REPORTS = HERE / "reports"
LOG = REPORTS / "monitoring_log.csv"
LOG_COLUMNS = ["month", "scenario (hidden truth)", "status", "details", "data_version", "model_version",
               "mean_risk", "flagged", "drift_gate", "outcomes_for", "obs/pred", "auc", "retrain"]
for d in (INCOMING, QUARANTINE, RAW, PRED, REPORTS):
    d.mkdir(parents=True, exist_ok=True)


def _mlflow():
    """MLflow store for this lesson: ./mlflow.db + ./mlruns, whatever the working directory."""
    import mlflow
    mlflow.set_tracking_uri(f"sqlite:///{HERE / 'mlflow.db'}")
    if mlflow.get_experiment_by_name("gam-risk-pipeline") is None:
        mlflow.create_experiment("gam-risk-pipeline", artifact_location=(HERE / "mlruns").as_uri())
    mlflow.set_experiment("gam-risk-pipeline")
    return mlflow


def accepted_months():
    return sorted(p.stem.removeprefix("emr_") for p in RAW.glob("emr_*.csv"))


def load(months):
    return pd.concat([em.load_months(m, m, raw=RAW) for m in months], ignore_index=True)


# ------------------------------------------------------------------ tasks

_attempts = {}


@task(retries=2, retry_delay_seconds=2)
def ingest(month: str, scenario: str = "baseline", flaky: bool = False) -> Path:
    """Fetch the month's EMR extract. `flaky=True` makes the first attempt fail, to show retries."""
    logger = get_run_logger()
    _attempts[month] = _attempts.get(month, 0) + 1
    if flaky and _attempts[month] == 1:
        raise ConnectionError(f"EMR export for {month} timed out")
    em.simulate(month, 1, scenario=scenario, out=INCOMING)      # stand-in for the real export
    path = INCOMING / f"emr_{month}.csv"
    logger.info(f"received {path.name} ({scenario}) on attempt {_attempts[month]}")
    return path


@task
def validate(path: Path) -> dict:
    """Run lesson 02's Great Expectations checkpoint on the file."""
    import great_expectations as gx
    import validate as gx_gate                                    # 02-great-expectations/validate.py
    context = gx.get_context(mode="file", project_root_dir=ROOT / "02-great-expectations")
    report = gx_gate.validate_file(context.checkpoints.get("emr_gate"), path)
    return {"passed": not report["critical_failures"],
            "critical": [f"{f['expectation']}({f['column']})" for f in report["critical_failures"]],
            "warnings": [f"{f['expectation']}({f['column']})" for f in report["warnings"]]}


@task
def quarantine(path: Path) -> Path:
    target = QUARANTINE / path.name
    shutil.move(path, target)
    get_run_logger().warning(f"QUARANTINED {path.name}: fix upstream, then re-run this month")
    return target


@task
def version(path: Path) -> str:
    """Move the accepted file into data/raw and version the folder with DVC. Returns its hash."""
    shutil.move(path, RAW / path.name)
    if not (HERE / ".dvc").exists():
        subprocess.run(["dvc", "init", "--subdir", "-q"], cwd=HERE, check=True)
    subprocess.run(["dvc", "add", "-q", "data/raw"], cwd=HERE, check=True)
    md5 = (HERE / "data" / "raw.dvc").read_text().split("md5: ")[1].split()[0]
    get_run_logger().info(f"data/raw is now version {md5[:12]} ({len(accepted_months())} months)")
    return md5


@task
def score(month: str) -> dict:
    """Score the month with the current champion; write the predictions (the 'batch scoring' output)."""
    mlflow = _mlflow()
    champion = mlflow.MlflowClient().get_model_version_by_alias(MODEL_NAME, "champion")
    model = mlflow.sklearn.load_model(f"models:/{MODEL_NAME}@champion")
    df = em.load_months(month, month, raw=RAW)
    risk = model.predict_proba(df[em.FEATURES])[:, 1]
    flagged = risk >= np.quantile(risk, 1 - CAPACITY)
    out = df[["visit_id", "facility_id", "sex", "age_band", "region"]].assign(
        risk=risk.round(4), flagged=flagged, model_version=champion.version)
    out.to_csv(PRED / f"pred_{month}.csv", index=False)       # what the clinics would receive
    return {"model_version": f"v{champion.version}", "mean_risk": round(float(risk.mean()), 3),
            "flagged": int(flagged.sum())}


@task
def drift_gate(month: str) -> list:
    """Evidently gate: the new batch vs the approved reference (2024), same season.

    The reference is fixed on purpose. Re-deriving it from each new champion's training
    months would quietly import whatever was unusual in those months (e.g. March 2025's
    regional shift) and cause false alarms. Changing the reference is a deliberate decision.
    """
    from evidently import DataDefinition, Dataset, Report
    from evidently.metrics import MissingValueCount, ValueDrift
    from evidently.tests import lte
    mlflow = _mlflow()
    model = mlflow.sklearn.load_model(f"models:/{MODEL_NAME}@champion")
    ref = load(REFERENCE_MONTHS)
    lean = int(month[5:7]) in {6, 7, 8, 9}
    ref = ref[ref["lean_season"] == int(lean)]                  # same season as the new month
    cur = em.load_months(month, month, raw=RAW)
    for d in (ref, cur):
        d["risk"] = model.predict_proba(d[em.FEATURES])[:, 1]
    num = [c for c in em.NUMERIC if c != "lean_season"] + ["risk"]
    definition = DataDefinition(numerical_columns=num, categorical_columns=em.CATEGORICAL)
    cols = num + em.CATEGORICAL
    snap = Report([
        ValueDrift(column="risk", tests=[lte(0.1)]),
        ValueDrift(column="region", tests=[lte(0.1)]),
        ValueDrift(column="muac_cm", tests=[lte(0.1)]),
        MissingValueCount(column="weight_kg", share_tests=[lte(0.05)]),
    ]).run(Dataset.from_pandas(cur[cols], data_definition=definition),
           Dataset.from_pandas(ref[cols], data_definition=definition))
    snap.save_html(str(REPORTS / f"drift_{month}.html"))
    return [t["name"].split(":")[0] for t in snap.dict()["tests"] if str(t["status"]).endswith("FAIL")]


def _group_sensitivity(y, risk, sex):
    """Sensitivity at the clinic's capacity, overall and per sex (Fairlearn MetricFrame)."""
    from fairlearn.metrics import MetricFrame, true_positive_rate
    flags = (risk >= np.quantile(risk, 1 - CAPACITY)).astype(int)
    mf = MetricFrame(metrics=true_positive_rate, y_true=y, y_pred=flags, sensitive_features=sex)
    return mf.overall, mf.by_group.to_dict()


@task
def performance(month: str) -> dict | None:
    """Outcomes for `month` are now known: how did that month's predictions do?"""
    from sklearn.metrics import roc_auc_score
    if month not in accepted_months() or not (PRED / f"pred_{month}.csv").exists():
        return None                                          # quarantined or never scored
    pred = pd.read_csv(PRED / f"pred_{month}.csv")
    outcome = em.load_months(month, month, raw=RAW)[["visit_id", em.LABEL]]
    df = pred.merge(outcome, on="visit_id")
    sens, by_sex = _group_sensitivity(df[em.LABEL], df["risk"], df["sex"])
    obs_pred = df[em.LABEL].mean() / df["risk"].mean()
    return {"month": month, "scored_by": f"v{df['model_version'].iloc[0]}",
            "roc_auc": roc_auc_score(df[em.LABEL], df["risk"]),
            "observed/predicted": obs_pred, "sensitivity": sens,
            "sens_F": by_sex["F"], "sens_M": by_sex["M"],
            "alert": not (CALIBRATION_OK[0] <= obs_pred <= CALIBRATION_OK[1])
                     or roc_auc_score(df[em.LABEL], df["risk"]) < MIN_AUC}


def _benchmark(model, bench):
    from sklearn.metrics import roc_auc_score
    risk = model.predict_proba(bench[em.FEATURES])[:, 1]
    sens, by_sex = _group_sensitivity(bench[em.LABEL], risk, bench["sex"])
    return {"roc_auc": roc_auc_score(bench[em.LABEL], risk), "obs/pred": bench[em.LABEL].mean() / risk.mean(),
            "sens_F": by_sex["F"], "sens_M": by_sex["M"]}


@task
def retrain_and_decide(month: str) -> dict:
    """Train a challenger on recent months, compare with the champion on a fixed benchmark, decide."""
    from mlflow.models import infer_signature
    mlflow = _mlflow()
    client = mlflow.MlflowClient()
    known = [m for m in accepted_months() if pd.Period(m) <= pd.Period(month) - OUTCOME_DELAY]
    bench_months, train_months = known[-2:], known[:-2][-TRAIN_WINDOW:]
    bench, train = load(bench_months), load(train_months)

    challenger = em.build_model("logistic").fit(train[em.FEATURES], train[em.LABEL])
    champion = mlflow.sklearn.load_model(f"models:/{MODEL_NAME}@champion")
    champ, chall = _benchmark(champion, bench), _benchmark(challenger, bench)

    # The written promotion rule
    reasons = []
    if chall["roc_auc"] < champ["roc_auc"] - 0.005:
        reasons.append("ranking worse")
    if abs(np.log(chall["obs/pred"])) >= abs(np.log(champ["obs/pred"])) - 0.05:
        reasons.append("calibration not better")
    for g in ("sens_F", "sens_M"):
        if champ[g] - chall[g] > 0.02:
            reasons.append(f"{g} drops")
    promote = not reasons

    with mlflow.start_run(run_name=f"challenger-{month}"):
        mlflow.log_params({"train_months": ",".join(train_months), "benchmark": ",".join(bench_months)})
        mlflow.set_tags({"data_version": (HERE / "data" / "raw.dvc").read_text().split("md5: ")[1].split()[0]})
        mlflow.log_metrics({f"champion_{k.replace('/', '_')}": v for k, v in champ.items()})
        mlflow.log_metrics({f"challenger_{k.replace('/', '_')}": v for k, v in chall.items()})
        info = mlflow.sklearn.log_model(
            challenger, name="logistic-regression", pyfunc_predict_fn="predict_proba",
            signature=infer_signature(bench[em.FEATURES], challenger.predict_proba(bench[em.FEATURES])),
            skops_trusted_types=["numpy.dtype"])
    if promote:
        mv = mlflow.register_model(info.model_uri, MODEL_NAME)
        client.set_model_version_tag(MODEL_NAME, mv.version, "train_months", json.dumps(train_months))
        client.set_model_version_tag(MODEL_NAME, mv.version, "promoted_in", month)
        client.set_registered_model_alias(MODEL_NAME, "champion", mv.version)
    fmt = lambda d: ", ".join(f"{k} {v:.3f}" for k, v in d.items())
    get_run_logger().info(f"benchmark {bench_months} | champion: {fmt(champ)} | challenger "
                          f"(trained {train_months[0]}..{train_months[-1]}): {fmt(chall)} -> "
                          f"{'PROMOTE' if promote else 'keep: ' + ', '.join(reasons)}")
    return {"decision": "PROMOTE" if promote else "keep", "reasons": reasons,
            "champion": champ, "challenger": chall}


@task
def report(row: dict) -> None:
    pd.DataFrame([row]).reindex(columns=LOG_COLUMNS).to_csv(LOG, mode="a", header=not LOG.exists(), index=False)
    create_markdown_artifact(key=f"month-{row['month']}", description=f"Pipeline result for {row['month']}",
                             markdown="\n".join(f"- **{k}**: {v}" for k, v in row.items()))


# ------------------------------------------------------------------ flows

@flow(name="bootstrap")
def bootstrap():
    """2024 history: ingest, validate and version 12 months; train and register the first champion."""
    logger = get_run_logger()
    for month in [str(p) for p in pd.period_range("2024-01", "2024-12", freq="M")]:
        if month in accepted_months():
            continue
        path = ingest(month)
        if validate(path)["passed"]:
            version(path)
    mlflow = _mlflow()
    if MODEL_NAME in [m.name for m in mlflow.search_registered_models()]:
        logger.info("champion already registered")
        return
    train_months = [str(p) for p in pd.period_range("2024-01", "2024-10", freq="M")]
    train = load(train_months)
    model = em.build_model("logistic").fit(train[em.FEATURES], train[em.LABEL])
    from mlflow.models import infer_signature
    with mlflow.start_run(run_name="bootstrap-2024"):
        info = mlflow.sklearn.log_model(
            model, name="logistic-regression", pyfunc_predict_fn="predict_proba",
            signature=infer_signature(train[em.FEATURES], model.predict_proba(train[em.FEATURES])),
            skops_trusted_types=["numpy.dtype"])
    mv = mlflow.register_model(info.model_uri, MODEL_NAME)
    client = mlflow.MlflowClient()
    client.set_model_version_tag(MODEL_NAME, mv.version, "train_months", json.dumps(train_months))
    client.set_registered_model_alias(MODEL_NAME, "champion", mv.version)
    logger.info(f"registered {MODEL_NAME} v{mv.version} as @champion")


@flow(name="monthly-pipeline", log_prints=True)
def monthly_pipeline(month: str | None = None, scenario: str = "baseline", flaky: bool = False) -> dict:
    """One month: ingest -> validate -> version -> score -> monitor -> performance -> (retrain)."""
    month = month or str(pd.Timestamp.today().to_period("M") - 1)    # default: last month
    row = {"month": month, "scenario (hidden truth)": scenario}
    if month in accepted_months():
        print(f"{month} already processed; skipping")
        return row

    path = ingest(month, scenario, flaky)
    check = validate(path)
    if not check["passed"]:
        quarantine(path)
        row |= {"status": "BLOCKED by GX",
                "details": f"{len(check['critical'])} critical checks failed, e.g. {check['critical'][0]}"}
        report(row)
        return row

    row["data_version"] = version(path)[:12]
    row |= score(month)
    failed = drift_gate(month)
    row["drift_gate"] = "ALERT: " + "; ".join(failed) if failed else "ok"

    perf = performance(str(pd.Period(month) - OUTCOME_DELAY))
    if perf is None:
        earlier = str(pd.Period(month) - OUTCOME_DELAY)
        why = ("quarantined" if (QUARANTINE / f"emr_{earlier}.csv").exists()
               else "history, not scored by the pipeline" if earlier in accepted_months() else "not received")
        row["outcomes_for"] = f"{earlier} ({why})"
    else:
        row |= {"outcomes_for": f"{perf['month']} (scored by {perf['scored_by']})",
                "obs/pred": round(perf["observed/predicted"], 2), "auc": round(perf["roc_auc"], 3)}
        if perf["alert"] and perf["scored_by"] != row["model_version"]:
            # The model that made those predictions has already been replaced: retraining
            # again now would only react to the old model's error.
            row["retrain"] = f"skipped ({perf['scored_by']} already replaced by {row['model_version']})"
        elif perf["alert"]:
            decision = retrain_and_decide(month)
            row["retrain"] = decision["decision"] + (f" ({', '.join(decision['reasons'])})"
                                                     if decision["reasons"] else "")
    row["status"] = "ok"
    report(row)
    return row


@flow(name="timeline-2025")
def timeline(months: list[str] | None = None):
    """Run the scripted 2025 story month by month (each month is its own sub-flow)."""
    bootstrap()
    rows = [monthly_pipeline(m, TIMELINE[m], flaky=(m == "2025-01")) for m in (months or list(TIMELINE))]
    table = pd.DataFrame(rows).reindex(columns=LOG_COLUMNS).fillna("").astype(str)
    create_table_artifact(key="monitoring-log", table=table.to_dict(orient="records"),
                          description="One row per month: gate results, scoring, performance, retraining")
    print(table.to_string(index=False))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "timeline"
    if cmd == "bootstrap":
        bootstrap()
    elif cmd == "month":
        monthly_pipeline(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "baseline")
    elif cmd == "timeline":
        timeline()
    elif cmd == "serve":   # a deployment: Prefect runs it on schedule while this process is up
        monthly_pipeline.serve(name="monthly-emr", cron="0 6 2 * *")
    else:
        sys.exit(__doc__)
