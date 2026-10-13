"""Feature list shared by train and evaluate. Identifiers and the label are excluded."""
NUMERIC = ["age_months", "weight_kg", "height_cm", "whz", "muac_cm", "recent_diarrhea",
           "recent_fever", "vaccinated_for_age", "currently_breastfed", "prior_sam_admission",
           "mother_age", "water_source_minutes", "household_size", "lean_season"]
CATEGORICAL = ["region", "residence", "sex", "birth_size", "mother_education"]
LABEL = "gam_within_90d"
