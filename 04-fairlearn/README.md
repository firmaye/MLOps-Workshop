# 04 – Fairlearn: who does the model miss?

**Where we are.** Every lesson so far showed the same number: the model catches fewer
malnourished girls than boys. This lesson measures that properly, finds the cause, and
compares fixes. One notebook: [`fairness.ipynb`](fairness.ipynb) (about 1.5 minutes to run).

**The setting.** A clinic can follow up 20% of visits; the model ranks children by risk
and the top 20% are flagged. The costly error is a **miss** (a child who becomes acutely
malnourished but wasn't flagged).

## Setup

From the repo root, environment active:
```bash
cd 04-fairlearn
```
Open `fairness.ipynb` in VSCode (kernel: `.venv`) and run it top to bottom. It reuses the
MLflow lesson's helper module (`../03-mlflow/emr_model.py`) and generates its own data in
`04-fairlearn/data/`: training on 2024, evaluation on a full year (2025, 24,000 visits).

## What the notebook covers, and the verified results

| Section | Finding |
|---|---|
| 1. `MetricFrame` by sex | Girls and boys develop GAM at the same rate (~11%), but sensitivity is **0.54 vs 0.61**: about 7 more of every 100 malnourished girls are missed. Flags are equally reliable (PPV ~0.32). |
| 2. Which "fair"? | Definitions compared (demographic parity, equal opportunity, equalized odds, predictive parity). With different base rates they conflict. By region, alert rates *should* differ, but sensitivity ranges from **0.15 in Addis Ababa to 0.80 in Afar**. |
| 3. Intersections + uncertainty | Bootstrap intervals (`n_boot`). On 2 months, the youngest children show girls 0.22 vs boys 0.74, from 23 cases each: mostly noise. On 12 months the real gap is at **6–23 months** (0.59 vs 0.68). |
| 4. Why girls are missed | At the same MUAC, girls develop GAM *less* often (their MUAC reads lower at the same nutrition). The model learns "girl = lower risk" through `sex`, ranking malnourished girls lower. Dropping `sex` **halves the gap** (0.071 → 0.036) at no cost in ROC-AUC. |
| 5. Mitigation | **Per-sex thresholds** within the 20% capacity: equal sensitivity (0.58 / 0.58), overall no worse. Fairlearn's `ThresholdOptimizer` with defaults flags **33%** of visits, because its objective ignores capacity. |
| 6. Decide, document, monitor | Trade-off table; write down the definition and tolerance first; gate promotion on it (MLflow lesson); monitor it (Evidently). |

## Key messages for the room

- **Unfairness usually enters through the data, not the code.** Here a measurement
  (MUAC) means different things for girls and boys, and the model inherits that.
- **Choose the fairness definition with the programme owners**, before looking at models.
  For screening, equal opportunity (equal sensitivity) is the usual priority.
- **Small groups produce noisy gaps.** Always report intervals and case counts.
- **Fairness tools optimise what you tell them.** Encode the real constraint (capacity).
- **The same tools give different answers in different settings.** Using sex at decision
  time is normal in clinical care (growth standards are sex-specific); in hiring (the
  resume-matching use case) protected attributes usually can't be used at all.

## Fairlearn cheat sheet

| Call | What it does |
|---|---|
| `MetricFrame(metrics={...}, y_true, y_pred, sensitive_features=df[["sex"]])` | Any metrics, overall and per group (several columns = intersections). |
| `.overall`, `.by_group`, `.difference()`, `.ratio()` | Overall value, per-group table, largest gap, smallest/largest ratio. |
| `MetricFrame(..., n_boot=200, ci_quantiles=[0.05, 0.95])` → `.by_group_ci` | Bootstrap confidence intervals per group. |
| `selection_rate`, `true_positive_rate`, `false_negative_rate`, `false_positive_rate` | Ready-made metrics (alert rate, sensitivity, miss rate, false-alarm rate). |
| `demographic_parity_difference`, `equal_opportunity_difference`, `equalized_odds_difference` | One-number fairness gaps. |
| `ThresholdOptimizer(estimator, constraints=..., objective=..., prefit=True)` | Learns group-specific thresholds under a fairness constraint. |
| `ExponentiatedGradient(estimator, constraints=TruePositiveRateParity())` | Trains a classifier under a fairness constraint (yes/no decisions, not risk scores). |

## Exercises

1. **Per-region thresholds.** Apply `equal_sensitivity_flags` to `evalset["region"]`
   instead of sex. What happens to Addis Ababa, to Afar and Somali, and to overall
   sensitivity? Who pays for equality, and would the nutrition programme accept that?
2. **Thresholds set in advance.** In practice thresholds are chosen on past data. Choose
   per-sex thresholds on Jan–Jun 2025 and apply them unchanged to Jul–Dec 2025. Does
   equal sensitivity hold? What about the alert rate (the lean season starts in June)?
3. **Intersectional thresholds.** Use `sex` and `age_band` together (6 groups). Using
   section 3's intervals, which of these thresholds would you trust?
4. **Log it.** In the MLflow lesson, add `MetricFrame(...).by_group` for sex and region to
   each run (`mlflow.log_dict`) and the girls/boys sensitivity gap as a metric. Then
   tighten the promotion rule to require a gap below 0.03.
5. **Resume matching.** Sketch the same analysis for shortlisting candidates: what is
   the "miss", which groups, which definition, and which mitigations are allowed?
