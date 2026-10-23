# 07 – TB chest X-ray screening: one model, three clinics, two kinds of drift

**Use case demo.** The EMR lessons introduced the tools; this one shows what happens when an **image** model
moves to new clinics and new patients. One notebook: [`tb_screening.ipynb`](tb_screening.ipynb), under a
minute to run, CPU only.

**The data** are real: a prospective study by Google and CIDRZ at three clinics in Lusaka, Zambia, where
1,828 adults had a chest X-ray **and** a lab test (culture / GeneXpert), with HIV status recorded. We replay a
staged rollout of our own model:

| Step | Who | What changes | Label-free checks | Lab results (our model) |
|---|---|---|---|---|
| 1 | Kanyama, HIV-negative | built and validated here | – | ROC-AUC 0.80, sensitivity 0.84 |
| 2 | Chawama, HIV-negative | new clinic, **same machine** | quiet (feature drift 0.65) | ROC-AUC 0.74, sensitivity 0.61: case mix differs |
| 3 | Chainda South, HIV-negative | **different machine** (Konica vs Fujifilm): acquisition drift | **all fire**: headers 99% different, feature drift 0.995, **flag rate 0** | **0 of 7 TB cases found** |
| 3b | same, with a pipeline bug | images inverted (header ignored) | **only the header check** | ROC-AUC 0.50 (coin toss) |
| 4 | Kanyama, **HIV-positive** | same machine, different patients: population shift | quiet (feature drift 0.59) | ROC-AUC 0.80 → 0.74; Google's model 0.90 → 0.82, sensitivity 0.94 → 0.81 |

**The narrative point:** acquisition drift is loud if you check the right things (headers, feature drift, flag
rate) and can make a model fail completely; population shift is silent to every input check and only lab
results reveal it. Plus: passing the input checks doesn't prove the model works (step 2).

**What to do about each:** the label-free checks say which kind of change you have; then ask whether the *ranking*
(ROC-AUC) is still good or only the cut-off is wrong. Acquisition drift: fix the pipeline (follow the header,
standardise the images), then retrain or fine-tune with images from the new machine if ROC-AUC is still low.
Population shift: evaluate per group, set the threshold again on local lab results, and retrain if ROC-AUC fell.

## Setup

From the repo root, environment active:
```bash
python scripts/download.py zambia        # the study's participant table from Kaggle (355 KB, no account needed)
cd 07-tb-xray
```
Open `tb_screening.ipynb` in VSCode (kernel: `.venv`) and run it. The image features and DICOM header facts
are in `data/` (5 MB, in the repo). The notebook tries to download 6 sample images to show them; without
internet it skips that and everything else still runs. MLflow runs go to `mlflow.db` in this folder.

**Optional, the images themselves** (1,828 DICOM files, about 1.7 GB; Kaggle limits anonymous downloads, so
expect 30+ minutes): `python tb_helpers.py download-images`. With them and the ONNX model file, participants
can recompute the features (`facilitator/build_zambia.py`), look at more images, or try other preprocessing.

## What's in the notebook

1. **Look at the data, including the headers:** the three clinics' X-ray machines differ, and the DICOM
   header says so (manufacturer, how pixels are stored, pixel size). A short explanation of
   `PhotometricInterpretation` and image inversion, with two real images (raw numbers vs our pipeline).
2. **Step 1:** train at Kanyama (HIV-negative), threshold for 90% sensitivity from cross-validated predictions,
   log to MLflow, register `tb-screening@champion`. Google's model on the same people for comparison.
3. **The checks for every new site:** header check, feature drift (can a classifier tell the sites apart?),
   flag rate; then performance once lab results exist.
4. **Step 2 (Chawama):** checks quiet, performance lower: case mix.
5. **Step 3 (Chainda South):** checks fire, model flags nobody; Evidently on feature summaries (and why its
   "drifted columns" count also fires for small differences); the inverted-image bug; a local threshold
   can't fix the ranking; Google's model, trained on many devices, holds up. Decision: don't deploy here.
6. **Step 4 (HIV-positive at Kanyama):** checks quiet, lab results show the drop, with bootstrap intervals;
   smear-negative TB is more common. Respond: per-group evaluation, enough cases per group, audits.
7. **Summary:** which check caught what.

Seven **PAUSE** prompts ask participants to commit to an answer before each result is shown.

## Key messages for the room

- **Nothing crashes when a model moves.** At Chainda South every prediction was a valid probability and every
  TB case was missed.
- **Read the DICOM header.** Machine, software, pixel storage and size are free, label-free signals, and the
  only check that catches a pipeline that ignores them.
- **Drift means different, not wrong;** size matters. Evidently's per-column tests flag small differences
  with large samples; a site classifier's ROC-AUC shows how different.
- **Population shift is invisible to input checks.** HIV-positive patients' X-rays look like anyone's; the
  model is worse for them. Only per-group evaluation on lab results shows it.
- **Small groups give wide intervals.** 52 TB cases among HIV-positive participants; 7 at Chainda South. Plan
  sample sizes for the groups that matter before evaluating.
- **Robustness comes from diverse training data:** a model trained on one machine broke at the next; a model
  trained on many held up, and still needed local validation.

## Facilitator notes

Licence notes: [`data/SOURCES.md`](data/SOURCES.md).

## Exercises

1. **Previous TB.** Repeat step 4's comparison for people previously treated for TB (`prev_tb`), with Google's
   model. (Old TB scars look like TB on an X-ray: expect a big change in specificity.)
2. **A header rule that blocks.** Write a rule that would stop Chainda South's batch before scoring. Should it
   block or warn, and who gets the message?
3. **Train on both machines.** Retrain with Kanyama plus half of Chainda South's images. What happens at each
   site? Why is 11 TB cases not enough?
4. **Group thresholds.** Choose a separate threshold for HIV-positive patients (on half of them) that restores
   90% sensitivity. What does it cost in false alarms? Is a group-specific threshold acceptable here?
5. **Shortcut learning.** Train a model on TB cases from Kanyama and non-TB people from Chainda South only. How
   well does it do on its own mix, and on Kanyama alone? What did it learn?
6. **A monitoring function.** Write a function that takes a batch (rows of `people`) and returns the header
   mismatch, feature drift and flag rate as a dict, ready for a Prefect task (compare lesson 06).
