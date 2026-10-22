"""Which columns the model uses. Shared by train.py and evaluate.py so they can't disagree.

Not features: visit_id, child_id, visit_date, facility_id (identifiers), month and
age_band (helpers for splitting/evaluation), and the label itself.
"""
NUMERIC = ["age_months", "weight_kg", "height_cm", "whz", "muac_cm", "recent_diarrhea",
           "recent_fever", "vaccinated_for_age", "currently_breastfed", "prior_sam_admission",
           "mother_age", "water_source_minutes", "household_size", "lean_season"]
CATEGORICAL = ["region", "residence", "sex", "birth_size", "mother_education"]
LABEL = "gam_within_90d"   # 1 = developed acute malnutrition within 90 days of the visit
