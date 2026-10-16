# Sources and licences

The images in `images/` are derived from two datasets, both licensed under
[Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/).

**Changes made to both:** a random sample of 200 TB and 200 normal images per dataset, converted to
grayscale, centre-cropped to a square and resized to 224 × 224 pixels, saved as PNG and renamed
(`metadata.csv` maps each file to its original name). Neither dataset's authors endorse this workshop.

## Site A: TBX11K

Liu, Y., Wu, Y.-H., Ban, Y., Wang, H., Cheng, M.-M. "Rethinking Computer-Aided Tuberculosis
Diagnosis." IEEE/CVF Conference on Computer Vision and Pattern Recognition (CVPR), 2020.
Dataset page: https://mmcheng.net/tb/ — belongs to the Media Computing Lab, Nankai University.
Lesion areas and types in `metadata.csv` are computed from its bounding-box annotations.
(The dataset's `imgs/extra` folder, which contains images under other terms, is not used.)

## Site B: Dataset of Tuberculosis Chest X-rays Images

Kiran, S., Jabeen, I. "Dataset of Tuberculosis Chest X-rays Images." Mendeley Data, version 3.
https://data.mendeley.com/datasets/8j2g3csprk — images collected from a hospital in Pakistan.

## Image features (`embeddings.npz`)

Computed with the torchxrayvision DenseNet-121 model `densenet121-res224-all`:
Cohen, J.P. et al. "TorchXRayVision: A library of chest X-ray datasets and models." MIDL 2022.
https://github.com/mlmed/torchxrayvision (code: Apache-2.0).
