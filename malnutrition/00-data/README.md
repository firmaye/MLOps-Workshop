# 00 – Mock EMR data: child malnutrition risk

`simulate_emr.py` generates monthly extracts from a fictional Ethiopian EMR.
**All data is synthetic.** Effect directions are loosely based on published
Ethiopian DHS analyses; the numbers are invented.

**Start here:** open [`explore_data.ipynb`](explore_data.ipynb) in VSCode (select
the `.venv` kernel) and run it top to bottom. It looks at the outcome rate by
month/region/age/sex, the MUAC vs WHZ difference between girls and boys, and what
each drift scenario looks like next to normal data.

## The prediction task

- **Cohort:** visits by children aged 0–59 months who are *not* currently
  acutely malnourished (those already meeting criteria are referred for
  treatment, so there's nothing to predict).
- **Label `gam_within_90d`:** the child develops global acute malnutrition
  (WHZ < −2 or MUAC < 12.5 cm) within 90 days.
- **Why not predict current malnutrition?** It's defined by thresholds on WHZ
  and MUAC, which are in the record. A model would just relearn the cut-offs:
  high accuracy, zero clinical value (label leakage).

## Columns

| Column | Notes |
|---|---|
| `visit_id`, `child_id`, `visit_date`, `facility_id` | identifiers; never used as features |
| `region`, `residence` | 8 regions; Afar and Somali (pastoralist) carry higher risk; Addis Ababa lower |
| `sex`, `age_months` | risk peaks at 6–23 months |
| `weight_kg`, `height_cm`, `whz`, `muac_cm` | MUAC not measured under 6 months (NaN) |
| `recent_diarrhea`, `recent_fever`, `vaccinated_for_age`, `currently_breastfed` | |
| `birth_size`, `prior_sam_admission` | |
| `mother_age`, `mother_education`, `water_source_minutes`, `household_size` | water access is a top predictor in DHS studies |
| `gam_within_90d` | the label (outcome becomes known ~90 days after the visit) |

Built-in realism:
- **Lean season (Jun–Sep):** risk rises from ~9% to ~15%.
- **MUAC vs WHZ:** at the same WHZ, MUAC reads lower for girls and under-2s,
  mirroring field findings that the two criteria disagree most for those groups.
- **Deterministic:** each month's seed depends only on the month, so a file
  is byte-identical however and whenever it's generated.

## Drift scenarios (`--scenario`)

| Scenario | What happens | Kind | Tool that should catch it |
|---|---|---|---|
| `baseline` | nothing changes | | |
| `new_regions` | rollout to pastoralist regions: Afar + Somali become half of visits | covariate drift | Evidently, Fairlearn (per region) |
| `muac_mm` | EMR update stores MUAC in mm (137 instead of 13.7) | data-quality bug | Great Expectations |
| `missing_anthro` | broken scales / MUAC-only screening: 70% of weight, height, WHZ missing | pipeline change | Great Expectations, then Evidently |
| `concept_shift` | food distribution suspended: illness and water access matter far more | concept drift | performance monitoring once labels arrive |
| `messy_export` | several small bugs at once: Amhara MUAC in mm (and recorded for infants), "female"/"male" codes, 15 duplicate visits, children aged 60+, already-malnourished children | data-quality bugs | Great Expectations |

```bash
python simulate_emr.py --start 2024-01 --months 12 --out data/raw            # training history
python simulate_emr.py --start 2025-01 --scenario muac_mm --out data/prod    # a broken batch
python simulate_emr.py --help
```
