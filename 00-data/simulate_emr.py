"""Simulate monthly batches of child-visit records from a mock Ethiopian EMR.

Each row is one outpatient / growth-monitoring visit for a child aged 0-59
months who is NOT currently acutely malnourished (children who already meet
the criteria are referred for treatment, so they are outside the prediction
cohort). The label is whether the child develops global acute malnutrition
(GAM: WHZ < -2 or MUAC < 12.5 cm) within the next 90 days.

Everything here is synthetic. Effect directions and rough magnitudes are
inspired by published Ethiopian DHS analyses (water access, birth size,
anaemia/illness, region, lean season), but the numbers are made up.

Usage:
    python simulate_emr.py --start 2024-01 --months 6 --out data/raw
    python simulate_emr.py --start 2025-07 --months 3 --scenario muac_mm --out data/prod
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

# name: (code, share of visits at baseline, extra risk on the logit scale, urban share)
REGIONS = {
    "Addis Ababa": ("AA", 0.08, -0.8, 0.95),
    "Amhara":      ("AM", 0.22,  0.1, 0.15),
    "Oromia":      ("OR", 0.30,  0.0, 0.15),
    "SNNP":        ("SN", 0.15,  0.1, 0.12),
    "Sidama":      ("SI", 0.08,  0.0, 0.12),
    "Tigray":      ("TI", 0.07,  0.3, 0.15),
    "Afar":        ("AF", 0.05,  0.7, 0.10),
    "Somali":      ("SO", 0.05,  0.7, 0.10),
}
FACILITIES_PER_REGION = 5
LEAN_SEASON = {6, 7, 8, 9}  # June-September

SCENARIOS = {
    "baseline":       "No change: same population, same EMR, same relationships.",
    "new_regions":    "Rollout expands to pastoralist regions: Afar + Somali become half of visits (covariate drift).",
    "muac_mm":        "EMR update records MUAC in millimetres instead of cm (data-quality bug).",
    "missing_anthro": "Scales broken / MUAC-only screening: weight, height, WHZ mostly missing (pipeline change).",
    "concept_shift":  "Food distribution suspended: illness and water access become far stronger risk factors (concept drift).",
    "messy_export":   "Several small export bugs at once: one region in mm, free-text sex codes, duplicates, out-of-cohort children.",
}

# rough WHO-style medians, good enough for mock data
_AGE = [0, 6, 12, 24, 36, 48, 60]
_HEIGHT = [49.5, 66.0, 75.0, 86.5, 95.0, 102.5, 109.5]
_LEN = [45, 50, 60, 70, 80, 90, 100, 110, 120]
_WEIGHT = [2.4, 3.3, 5.9, 8.4, 10.6, 12.9, 15.4, 18.3, 22.0]


def _month_seed(month: pd.Period, seed: int) -> int:
    # seed depends only on the month, so batches are identical however they're generated
    return seed * 100_000 + month.year * 100 + month.month


def simulate_month(month: pd.Period, n: int, scenario: str = "baseline", seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(_month_seed(month, seed))
    m = 3 * n  # oversample, then drop children who are already malnourished

    names = list(REGIONS)
    shares = np.array([REGIONS[r][1] for r in names])
    if scenario == "new_regions":
        pastoral = np.isin(names, ["Afar", "Somali"])
        shares = np.where(pastoral, 0.25, shares / shares[~pastoral].sum() * 0.5)
    region = rng.choice(names, size=m, p=shares / shares.sum())
    region_risk = np.array([REGIONS[r][2] for r in region])
    urban_share = np.array([REGIONS[r][3] for r in region])
    pastoral = np.isin(region, ["Afar", "Somali"])

    # younger children visit more often (immunisation, growth monitoring)
    age = np.clip(rng.gamma(1.6, 12, size=m), 0, 59).astype(int)
    female = rng.random(m) < 0.5
    urban = rng.random(m) < urban_share
    lean = month.month in LEAN_SEASON
    age_6_23 = (age >= 6) & (age < 24)

    edu = np.where(urban,
                   rng.choice(["none", "primary", "secondary+"], size=m, p=[0.2, 0.4, 0.4]),
                   rng.choice(["none", "primary", "secondary+"], size=m, p=[0.55, 0.35, 0.10]))
    water_min = np.round(np.where(urban, rng.lognormal(1.5, 0.6, m),
                                  rng.lognormal(3.2 + 0.4 * pastoral, 0.6, m)))
    birth_size = rng.choice(["small", "average", "large"], size=m, p=[0.2, 0.6, 0.2])
    diarrhea = rng.random(m) < (0.12 + 0.10 * age_6_23 + 0.002 * np.minimum(water_min, 60))
    fever = rng.random(m) < 0.18
    vaccinated = rng.random(m) < np.where(urban, 0.85, 0.65 - 0.15 * pastoral)
    breastfed = np.where(age < 24, rng.random(m) < 0.9, rng.random(m) < 0.1)
    prior_adm = rng.random(m) < 0.05
    mother_age = np.clip(rng.normal(27, 6, m), 15, 49).astype(int)
    hh_size = np.clip(rng.poisson(5.5, m), 2, 14)

    # current nutritional status
    whz = rng.normal(-0.3 - 0.3 * region_risk - 0.3 * (birth_size == "small")
                     - 0.3 * diarrhea - 0.2 * lean - 0.2 * age_6_23, 1.0)
    haz = rng.normal(-1.3 - 0.3 * region_risk, 1.2)  # ~40% stunted
    height = np.interp(age, _AGE, _HEIGHT) - 1.0 * female + haz * (1.9 + 0.04 * age)
    weight = np.interp(height, _LEN, _WEIGHT) * (1 + 0.09 * whz) + rng.normal(0, 0.15, m)
    # MUAC reads lower for girls and younger children at the same WHZ, which is
    # why MUAC and WHZ disagree more for those groups in the field.
    muac = (14.2 + 0.7 * whz + 0.02 * (np.minimum(age, 48) - 24)
            - 0.25 * female - 0.3 * (age < 24) + rng.normal(0, 0.4, m))
    muac = np.where(age < 6, np.nan, muac)  # MUAC not used under 6 months

    eligible = (whz >= -2) & ~(muac < 12.5)

    # outcome: GAM within 90 days
    muac_gap = np.nan_to_num(muac - 13.5, nan=0.0)
    illness_w, water_w, intercept = (0.5, 0.008, -3.9)
    if scenario == "concept_shift":
        illness_w, water_w, intercept = (1.3, 0.03, -3.7)
    logit = (intercept - 1.0 * whz - 0.8 * muac_gap + region_risk + 0.6 * lean
             + illness_w * diarrhea + 0.3 * fever + 0.4 * (birth_size == "small")
             + 0.3 * age_6_23 + water_w * water_min + 0.4 * (edu == "none")
             + 0.8 * prior_adm - 0.3 * vaccinated)
    label = rng.random(m) < 1 / (1 + np.exp(-logit))

    day = rng.integers(1, month.days_in_month + 1, size=m)
    facility = [f"{REGIONS[r][0]}-HC{k}" for r, k in
                zip(region, rng.integers(1, FACILITIES_PER_REGION + 1, size=m))]

    df = pd.DataFrame({
        "child_id": [f"C{x:07d}" for x in rng.integers(0, 10_000_000, size=m)],
        "visit_date": [f"{month.year}-{month.month:02d}-{d:02d}" for d in day],
        "facility_id": facility,
        "region": region,
        "residence": np.where(urban, "urban", "rural"),
        "sex": np.where(female, "F", "M"),
        "age_months": age,
        "weight_kg": weight.round(1),
        "height_cm": height.round(1),
        "whz": whz.round(2),
        "muac_cm": muac.round(1),
        "recent_diarrhea": diarrhea.astype(int),
        "recent_fever": fever.astype(int),
        "vaccinated_for_age": vaccinated.astype(int),
        "currently_breastfed": breastfed.astype(int),
        "birth_size": birth_size,
        "prior_sam_admission": prior_adm.astype(int),
        "mother_age": mother_age,
        "mother_education": edu,
        "water_source_minutes": water_min.astype(int),
        "household_size": hh_size,
        "gam_within_90d": label.astype(int),
    })[eligible].head(n)

    if scenario == "muac_mm":
        df["muac_cm"] = (df["muac_cm"] * 10).round(0)
    elif scenario == "missing_anthro":
        gone = rng.random(len(df)) < 0.7
        df.loc[gone, ["weight_kg", "height_cm", "whz"]] = np.nan
    df = df.sort_values("visit_date", kind="stable").reset_index(drop=True)
    df.insert(0, "visit_id", [f"V{month.year}{month.month:02d}-{i:05d}" for i in range(len(df))])
    if scenario == "messy_export":
        df = _make_messy(df, rng)
    return df


def _make_messy(df: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Several small, realistic export problems at once (each affects a minority of rows)."""
    df = df.copy()
    # Amhara facilities got a new EMR version first: MUAC in mm, and recorded for infants too
    amhara = df["region"] == "Amhara"
    infants = amhara & (df["age_months"] < 6)
    df.loc[infants, "muac_cm"] = rng.normal(12.5, 0.6, infants.sum()).round(1)
    df.loc[amhara, "muac_cm"] = (df.loc[amhara, "muac_cm"] * 10).round(0)
    # free-text sex codes from one data clerk
    clerk = rng.choice(df.index, size=40, replace=False)
    df.loc[clerk, "sex"] = df.loc[clerk, "sex"].map({"F": "female", "M": "male"})
    # children who aged out of the 0-59 month programme
    aged_out = rng.choice(df.index, size=12, replace=False)
    df.loc[aged_out, "age_months"] = rng.integers(60, 72, size=12)
    # already-malnourished children who should have been referred, not scored
    referred = rng.choice(df.index, size=25, replace=False)
    df.loc[referred, "whz"] = rng.uniform(-3.0, -2.1, size=25).round(2)
    # a re-run of part of the export appends duplicate visits
    dupes = df.sample(n=15, random_state=int(rng.integers(1_000_000)))
    return pd.concat([df, dupes], ignore_index=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", required=True, help="first month, YYYY-MM")
    ap.add_argument("--months", type=int, default=1)
    ap.add_argument("--rows", type=int, default=2000, help="visits per month")
    ap.add_argument("--scenario", default="baseline", choices=SCENARIOS)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default="data/raw")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    start = pd.Period(args.start, freq="M")
    for i in range(args.months):
        month = start + i
        df = simulate_month(month, args.rows, args.scenario, args.seed)
        path = out / f"emr_{month}.csv"
        df.to_csv(path, index=False)
        print(f"{path}: {len(df)} visits, {df['gam_within_90d'].mean():.1%} GAM within 90d"
              f" [{args.scenario}]")


if __name__ == "__main__":
    main()
