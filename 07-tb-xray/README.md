# 07 – TB chest X-ray screening: image data, site shift, shortcut learning

**Use case demo.** The EMR lessons introduced the tools; this one shows what changes when the
data are **images** and the model moves **between hospitals**. One notebook:
[`tb_screening.ipynb`](tb_screening.ipynb), about 30 seconds to run, CPU only.

| Beat | In the notebook |
|---|---|
| Setting | A TB programme screens adults with chest X-rays; flagged people get a lab test. Target: catch ≥ 90% of TB. |
| First model | Pretrained chest X-ray network turns each image into 1024 features; logistic regression on site A. ROC-AUC 0.98. Logged and registered in MLflow (`tb-screening@champion`). |
| Twist 1: new site | Deployed at site B: ROC-AUC **0.59**, half the TB cases missed, no error anywhere. |
| Detect | Without labels: image checks (contrast, borders), feature drift (a classifier tells the sites apart with ROC-AUC 1.00; Evidently flags 8 of 10 feature summaries), flag rate. With labels: per-site evaluation. |
| Respond | A local threshold can't fix it (flags 90% of people). Retraining with **50 labelled local images** does: site B ROC-AUC 0.99, site A unchanged. Promoted under a written rule. |
| Twist 2: shortcut | TB cases from one hospital, normal controls from another: perfect test score (1.00), but 0.72 once both classes come from the same hospital. The model learned the hospital. |
| Twist 3: real programme | 50% TB in the test set vs 1–5% in screening: what the same model means for lab workload and positive predictive value; HIV and who gets screened (discussion). |
| Lesson | Evaluate per site; check whether the site is predictable from the inputs; label-free signals warn, lab results confirm; prevalence and lab capacity set the threshold. |

## Setup

From the repo root, environment active:
```bash
cd 07-tb-xray
```
Open `tb_screening.ipynb` in VSCode (kernel: `.venv`) and run it top to bottom. Everything it needs
is in `data/` (about 23 MB, in the repo): 800 resized X-rays, their metadata and precomputed
image features. MLflow runs go to `mlflow.db` / `mlruns/` in this folder (`mlflow ui` to browse).

**Optional:** to recompute image features on your laptop, the notebook looks for the pretrained
network as `downloads/tb/cxr_densenet121.onnx` (28 MB; `python scripts/download.py tb-model` once
it is published). Without it, the notebook uses the precomputed features and says so.

## The data

| | Site A | Site B |
|---|---|---|
| Source | [TBX11K](https://mmcheng.net/tb/) (Liu et al., CVPR 2020; hospitals in China) | [Dataset of Tuberculosis Chest X-rays Images](https://data.mendeley.com/datasets/8j2g3csprk) (Kiran & Jabeen, Mendeley Data; a hospital in Pakistan) |
| Licence | CC BY 4.0 | CC BY 4.0 |
| Used here | 200 TB + 200 normal, randomly sampled | 200 TB + 200 normal, randomly sampled |
| Splits | train 150 + 150, test 50 + 50 | local labelled sample 25 + 25, test 175 + 175 |

Changes made: random sampling, conversion to grayscale, centre crop, resize to 224 × 224 PNG.
`data/metadata.csv` keeps each image's original file name; for site A it also has the annotated
lesion area and type. Full attribution in [`data/SOURCES.md`](data/SOURCES.md).

**Why not the well-known Shenzhen and Montgomery sets?** Their terms ask users not to share the
data outside their own organisation, so they can't be handed to workshop participants.

**Image features:** [torchxrayvision](https://github.com/mlmed/torchxrayvision) DenseNet-121
(`densenet121-res224-all`, Apache-2.0 code), trained on other public chest X-ray collections
(NIH, CheXpert, MIMIC, PadChest and others), not on either TB set used here. Converted to ONNX so
laptops need only `onnxruntime`, not PyTorch.

## Key messages for the room

- **Nothing crashes when a model moves.** At site B every prediction was a valid probability;
  half the TB cases were missed. Per-site evaluation before go-live is the only real defence.
- **Image data get their own checks.** Size, colour mode, brightness, contrast, borders: the
  image version of a Great Expectations suite, run on every batch.
- **Label-free signals come first:** image checks, feature drift and the flag rate are available
  the day images arrive; lab results come later and mostly only for flagged people.
- **A threshold can't fix a model that ranks badly.** A small local labelled sample can.
- **Too good to be true usually is.** Near-perfect scores on public data, and a site that can be
  predicted from the image, call for a shortcut check.
- **Prevalence and lab capacity, not ROC-AUC, decide the threshold** in a real programme.

## Facilitator notes

- The numbers in the table above are from the committed data and are reproducible
  (fixed splits, deterministic logistic regression).
- Site A's sensitivity on its own test set is 0.82, not the 0.90 aimed for: 50 TB test images and
  a threshold chosen on 300 training images. Good discussion point on small validation sets.
- The HIV twist from the design doc is a discussion point, not a computation: no openly
  shareable chest X-ray dataset records HIV status. Lesion size (in `metadata.csv`) barely changes
  sensitivity here, so it isn't a convincing stand-in.
- `facilitator/` rebuilds `data/` from the original downloads (`export_onnx.py` needs PyTorch;
  `prepare_data.py` needs the two datasets). Participants never need it.

## Exercises

1. **How few local images are enough?** Retrain v2 with 10, 20 and 50 images from site B's local
   sample (keep classes balanced). Plot site B's ROC-AUC against the number of images.
2. **A stricter image gate.** Write a rule that would have **blocked** site B's batch, and one that
   only **warns**. Which should it be, and who gets the warning?
3. **Find the shortcut yourself.** Train a classifier to predict the site from the features, using
   only normal images. What does it mean that it succeeds?
4. **Capacity.** The lab can process 40 tests per 1,000 people screened, prevalence is 2%. Which
   threshold would you choose for v2, and what sensitivity does that give at site B?
5. **Monitoring.** Write a function that takes a new batch of image paths and returns a dict with
   the image-check failures, the share flagged and the site-classifier score, ready for a Prefect
   task (compare with the EMR pipeline in lesson 06).
6. **Version the images.** Track `data/images` with DVC (lesson 01). What happens to `dvc status`
   when you add one new image?
