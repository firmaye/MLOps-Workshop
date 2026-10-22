"""Validate EMR extracts against the suite and act as a pipeline gate.

    python validate.py path/to/emr_2025-01.csv [more files or directories ...]
    python validate.py ../01-dvc/data/raw --report reports/validation.json

Each file is validated as its own batch. Exit code 1 if any CRITICAL
expectation fails in any file; warnings are printed but don't block.

Why our own gate? GX marks a run unsuccessful if *any* expectation fails,
whatever its severity. Severity is metadata; the policy is ours.
"""
import argparse
import json
import sys
from pathlib import Path

import great_expectations as gx
import pandas as pd

HERE = Path(__file__).parent


def describe(r):
    cfg, res = r.expectation_config, r.result
    target = cfg.kwargs.get("column", "table")
    detail = ""
    if "unexpected_percent" in res and res.get("unexpected_count"):
        detail = f"{res['unexpected_count']} rows ({res['unexpected_percent']:.1f}%)"
        sample = [v for v in res.get("partial_unexpected_list", []) if v == v][:3]  # drop NaN
        if sample:
            detail += f", e.g. {sample}"
    elif "observed_value" in res:
        detail = f"observed {res['observed_value']}"
    return {"expectation": cfg.type, "column": target, "severity": cfg.severity.value, "detail": detail}


def validate_file(checkpoint, path):
    df = pd.read_csv(path)
    run = checkpoint.run(batch_parameters={"dataframe": df})
    results = [r for vr in run.run_results.values() for r in vr.results]
    failed = [describe(r) for r in results if not r.success]
    return {
        "file": str(path),
        "rows": len(df),
        "evaluated": len(results),
        "critical_failures": [f for f in failed if f["severity"] == "critical"],
        "warnings": [f for f in failed if f["severity"] != "critical"],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", help="CSV files or directories of CSVs")
    ap.add_argument("--report", help="write a JSON summary here")
    args = ap.parse_args()

    files = []
    for p in map(Path, args.paths):
        files += sorted(p.glob("*.csv")) if p.is_dir() else [p]

    ctx = gx.get_context(mode="file", project_root_dir=HERE)
    checkpoint = ctx.checkpoints.get("emr_gate")

    reports = []
    for f in files:
        rep = validate_file(checkpoint, f)
        reports.append(rep)
        status = "FAIL" if rep["critical_failures"] else ("WARN" if rep["warnings"] else "PASS")
        print(f"{status}  {f}  ({rep['rows']} rows, {rep['evaluated']} expectations)")
        for item in rep["critical_failures"] + rep["warnings"]:
            print(f"      [{item['severity']}] {item['expectation']}({item['column']}): {item['detail']}")

    blocked = [r["file"] for r in reports if r["critical_failures"]]
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        json.dump({"passed": not blocked, "blocked_files": blocked, "files": reports},
                  open(args.report, "w"), indent=2)

    docs = HERE / "gx/uncommitted/data_docs/local_site/index.html"
    print(f"\nData Docs: {docs.resolve()}")
    if blocked:
        print(f"BLOCKED: {len(blocked)} file(s) failed critical expectations")
        sys.exit(1)
    print("OK: no critical failures")


if __name__ == "__main__":
    main()
