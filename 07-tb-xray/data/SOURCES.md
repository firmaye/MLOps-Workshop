# Sources and licences

## The Zambia study

**Google + CIDRZ Health AI Evaluation Zambia**, published by Google Health AI on Kaggle:
https://www.kaggle.com/datasets/googlehealthai/google-health-ai
Licence as stated there: *Database: Open Database License (ODbL); Contents: © Original Authors.*

Study: Kazemzadeh S. et al., "Prospective Multi-Site Validation of AI to Detect Tuberculosis and Chest X-Ray
Abnormalities", *NEJM AI* 2024 (ClinicalTrials.gov NCT05139940). Data collected by the Centre for Infectious
Disease Research in Zambia (CIDRZ) at Kanyama, Chawama and Chainda South clinics, Lusaka.

What is in this folder, and what is not:

| File | Contents | Derived from |
|---|---|---|
| `zambia_headers.csv` | per image: the study's anonymised participant id, file name, and acquisition fields from the DICOM header (manufacturer, software version, photometric interpretation, rows, columns, pixel spacing, bits stored) | the study's DICOM files |
| `zambia_features.npz` | per image: 1024 numbers computed by the image model below (not reversible to an image) | the study's DICOM files |
| `zambia_features_bug.npz` | the same for Chainda South's Konica images, computed by a deliberately wrong pipeline (always inverts) | the study's DICOM files |

**Not included:** the images themselves and the participant table (symptoms, HIV status, lab results). Both
are downloaded from Kaggle by each participant (`python scripts/download.py zambia`; images optional via
`python 07-tb-xray/tb_helpers.py download-images`). The database is used under the ODbL with attribution;
the derived features are shared for teaching. If the data owners object, remove the `.npz` files and have
participants compute features from the downloaded images (`facilitator/build_zambia.py`).

## Image features

Computed with the torchxrayvision DenseNet-121 model `densenet121-res224-all` (converted to ONNX):
Cohen J.P. et al., "TorchXRayVision: A library of chest X-ray datasets and models", MIDL 2022.
https://github.com/mlmed/torchxrayvision (code: Apache-2.0). It was trained on other public chest X-ray
collections, not on this study's images.
