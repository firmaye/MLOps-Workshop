"""Define what a valid monthly EMR extract looks like, and save it to gx/.

The suite is stored as JSON in gx/expectations/, so it is versioned in git
alongside the code. Rerun this script after editing; it overwrites the suite.

Severity is our own convention for the gate in validate.py:
  critical -> the batch is unusable; stop the pipeline
  warning  -> suspicious; log it, let a human look, keep going
"""
import json
from pathlib import Path

import great_expectations as gx
import great_expectations.expectations as gxe

HERE = Path(__file__).parent
SUITE = "emr_monthly_extract"

COLUMNS = ["visit_id", "child_id", "visit_date", "facility_id", "region", "residence", "sex",
           "age_months", "weight_kg", "height_cm", "whz", "muac_cm", "recent_diarrhea",
           "recent_fever", "vaccinated_for_age", "currently_breastfed", "birth_size",
           "prior_sam_admission", "mother_age", "mother_education", "water_source_minutes",
           "household_size", "gam_within_90d"]
REGIONS = ["Addis Ababa", "Amhara", "Oromia", "SNNP", "Sidama", "Tigray", "Afar", "Somali"]
BINARY = ["recent_diarrhea", "recent_fever", "vaccinated_for_age", "currently_breastfed",
          "prior_sam_admission", "gam_within_90d"]


def only_if(condition):
    """Apply an expectation only to rows matching a pandas query string.

    The string form works on every GX 1.x release; the newer
    `row_condition=Column("age_months") >= 6` syntax needs a recent GX.
    """
    return {"row_condition": condition, "condition_parser": "pandas"}


def expectations():
    warn = {"severity": "warning"}

    # 1. Schema and volume: did the export run correctly at all?
    yield gxe.ExpectTableColumnsToMatchSet(column_set=COLUMNS, exact_match=True)
    yield gxe.ExpectTableRowCountToBeBetween(min_value=500, max_value=5000)

    # 2. Identifiers and formats
    yield gxe.ExpectColumnValuesToBeUnique(column="visit_id")
    yield gxe.ExpectColumnValuesToNotBeNull(column="visit_id")
    yield gxe.ExpectColumnValuesToMatchStrftimeFormat(column="visit_date", strftime_format="%Y-%m-%d")
    yield gxe.ExpectColumnValuesToMatchRegex(column="facility_id", regex=r"^(AA|AM|OR|SN|SI|TI|AF|SO)-HC\d+$")

    # 3. Categorical codes: a new spelling ("female", "Oromiya") silently breaks one-hot encoding
    yield gxe.ExpectColumnValuesToBeInSet(column="region", value_set=REGIONS)
    yield gxe.ExpectColumnValuesToBeInSet(column="sex", value_set=["F", "M"])
    yield gxe.ExpectColumnValuesToBeInSet(column="residence", value_set=["urban", "rural"])
    yield gxe.ExpectColumnValuesToBeInSet(column="birth_size", value_set=["small", "average", "large"])
    yield gxe.ExpectColumnValuesToBeInSet(column="mother_education", value_set=["none", "primary", "secondary+"])
    for col in BINARY:
        yield gxe.ExpectColumnValuesToBeInSet(column=col, value_set=[0, 1])
        yield gxe.ExpectColumnValuesToNotBeNull(column=col)

    # 4. Physiological plausibility (units!). Ranges are deliberately wide:
    #    they catch impossible values, not unusual children.
    yield gxe.ExpectColumnValuesToNotBeNull(column="age_months")
    yield gxe.ExpectColumnValuesToBeBetween(column="age_months", min_value=0, max_value=59)
    yield gxe.ExpectColumnValuesToBeBetween(column="muac_cm", min_value=8, max_value=25)       # cm, not mm
    yield gxe.ExpectColumnValuesToBeBetween(column="weight_kg", min_value=1, max_value=35)
    yield gxe.ExpectColumnValuesToBeBetween(column="height_cm", min_value=38, max_value=130)
    yield gxe.ExpectColumnValuesToBeBetween(column="whz", min_value=-5, max_value=5)           # WHO flag limits
    yield gxe.ExpectColumnValuesToBeBetween(column="mother_age", min_value=12, max_value=55)
    yield gxe.ExpectColumnValuesToBeBetween(column="water_source_minutes", min_value=0, max_value=720)
    yield gxe.ExpectColumnValuesToBeBetween(column="household_size", min_value=1, max_value=30)

    # 5. Completeness: the model needs anthropometry. `mostly` tolerates a few gaps.
    for col in ["weight_kg", "height_cm", "whz"]:
        yield gxe.ExpectColumnValuesToNotBeNull(column=col, mostly=0.95)
    yield gxe.ExpectColumnValuesToNotBeNull(column="muac_cm", mostly=0.95, **only_if("age_months >= 6"))

    # 6. Cohort definition: children already acutely malnourished should have
    #    been referred for treatment, not sent to a risk model.
    yield gxe.ExpectColumnMinToBeBetween(column="whz", min_value=-2, max_value=None)
    yield gxe.ExpectColumnMinToBeBetween(column="muac_cm", min_value=12.5, max_value=None)

    # 7. Warnings: plausible but worth a human look
    yield gxe.ExpectColumnValuesToBeNull(column="muac_cm", mostly=0.95, **only_if("age_months < 6"),
                                         **warn)  # protocol: no MUAC under 6 months
    yield gxe.ExpectColumnMeanToBeBetween(column="gam_within_90d", min_value=0.02, max_value=0.30, **warn)
    yield gxe.ExpectColumnMedianToBeBetween(column="age_months", min_value=6, max_value=36, **warn)
    yield gxe.ExpectColumnUniqueValueCountToBeBetween(column="facility_id", min_value=20, max_value=None, **warn)


def _rules(exps):
    """Expectation content, ignoring the random ids GX assigns on every save."""
    return sorted(json.dumps({k: v for k, v in e.configuration.to_json_dict().items() if k != "id"},
                             sort_keys=True) for e in exps)


def main():
    ctx = gx.get_context(mode="file", project_root_dir=HERE)
    new = list(expectations())

    # Saving rewrites every id, which would show up as a git diff and make DVC
    # re-run validation. Only save when the rules actually changed.
    # (Read the stored suite BEFORE creating a new ExpectationSuite object with
    # the same name: adding expectations to that object writes to the store.)
    try:
        existing = ctx.suites.get(SUITE)
    except gx.exceptions.DataContextError:
        existing = None  # first build
    if existing is not None:
        if _rules(existing.expectations) == _rules(new):
            print(f"suite '{SUITE}' unchanged ({len(new)} expectations); nothing written")
            return
        ctx.suites.delete(SUITE)

    suite = ctx.suites.add(gx.ExpectationSuite(name=SUITE))
    for exp in new:
        suite.add_expectation(exp)

    # Batches arrive as pandas DataFrames, so one in-memory asset serves every file
    asset = (ctx.data_sources.add_or_update_pandas("emr")
             .add_dataframe_asset("visits"))
    batch_def = asset.add_batch_definition_whole_dataframe("monthly_extract")

    vd = ctx.validation_definitions.add_or_update(
        gx.ValidationDefinition(name="emr_monthly", data=batch_def, suite=suite))
    ctx.checkpoints.add_or_update(gx.Checkpoint(
        name="emr_gate",
        validation_definitions=[vd],
        actions=[gx.checkpoint.UpdateDataDocsAction(name="update_data_docs")],
        result_format={"result_format": "SUMMARY"},
    ))
    n_warn = sum(e.severity.value == "warning" for e in suite.expectations)
    print(f"suite '{SUITE}': {len(suite.expectations)} expectations "
          f"({len(suite.expectations) - n_warn} critical, {n_warn} warning)")


if __name__ == "__main__":
    main()
