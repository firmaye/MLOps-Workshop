"""Helpers for the TB chest X-ray demo (Zambia study), shared by the notebook and the facilitator script.

Kept small and plain on purpose: the notebook is where the story is told.

    python tb_helpers.py download-images      # optional: all 1,828 study X-rays from Kaggle (about 1.7 GB)
    python tb_helpers.py download-images 24   # or just a few, to look at
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
DOWNLOADS = HERE.parent / "downloads" / "zambia"
IMAGES = DOWNLOADS / "images"                                  # optional DICOM downloads land here
MODEL_FILE = HERE.parent / "downloads" / "tb" / "cxr_densenet121.onnx"   # optional; see README
SIZE = 224                                                     # the pretrained model works on 224 x 224 grayscale

KAGGLE_DATASET = "googlehealthai/google-health-ai"             # Google + CIDRZ Health AI Evaluation Zambia
KAGGLE_TABLE = "Metadata and Codebook/Metadata and Codebook/GHAI_Final_Data_2023.csv"
KAGGLE_IMAGES = "Google_AI_Anonymized_images/Google_AI_Anonymized_images/"
TABLE = DOWNLOADS / "GHAI_Final_Data_2023.csv"
CLINICS = {"Kan": "Kanyama", "Cha": "Chawama", "Chai": "Chainda South"}


# ---------------------------------------------------------------- data


def load_participants():
    """The study table, one row per participant: symptoms, HIV status, lab results, Google's AI score.

    Downloaded once from Kaggle (355 KB, no account needed), then read locally.
    Note: the column the codebook calls "1 - TB Predictions" (`tb_predictions1`) is in fact the TB
    score: it reproduces the study's own decisions at its published thresholds. We call it `google_score`.
    """
    if not TABLE.exists():
        import shutil

        import kagglehub

        TABLE.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(kagglehub.dataset_download(KAGGLE_DATASET, path=KAGGLE_TABLE), TABLE)
    d = pd.read_csv(TABLE, encoding="utf-8-sig", dtype={"anon_id": str})
    d["tb"] = (d.ground_truth_tb == "pos").astype(int)          # bacteriologically confirmed (culture / Xpert)
    d["google_score"] = d.tb_predictions1
    d["clinic"] = d.facility_code.map(CLINICS)
    d["hiv"] = d.hiv_status.map({"neg": "HIV-negative", "pos": "HIV-positive"})
    return d


def load_data():
    """Participants joined to their image's DICOM header facts, plus the image features (same order)."""
    people = load_participants()
    heads = pd.read_csv(DATA / "zambia_headers.csv", dtype=str)
    z = np.load(DATA / "zambia_features.npz")
    feats = pd.DataFrame(z["features"], index=z["anon_id"])
    table = heads.merge(people, on="anon_id", how="inner").reset_index(drop=True)
    return table, feats.loc[table.anon_id].to_numpy()


def load_bug_features(anon_ids):
    """Features for the same images, processed by a pipeline that ignores the DICOM image-format flag."""
    z = np.load(DATA / "zambia_features_bug.npz")
    return pd.DataFrame(z["features"], index=z["anon_id"]).loc[list(anon_ids)].to_numpy()


# ---------------------------------------------------------------- images (optional)


def download_images(n=None):
    """Download the study's DICOM images from Kaggle (all, or the first n listed in the header table)."""
    import shutil

    import kagglehub

    IMAGES.mkdir(parents=True, exist_ok=True)
    files = pd.read_csv(DATA / "zambia_headers.csv", dtype=str).file.tolist()[:n]
    for i, f in enumerate(files, 1):
        if not (IMAGES / f).exists():
            shutil.copy(kagglehub.dataset_download(KAGGLE_DATASET, path=KAGGLE_IMAGES + f), IMAGES / f)
        if i % 100 == 0 or i == len(files):
            print(f"{i}/{len(files)} images", flush=True)


def dicom_to_224(ds, assume_monochrome1=False):
    """DICOM -> 224 x 224 grayscale array (0-255), bones bright.

    DICOM images can be stored either way round: MONOCHROME2 means bright = dense (bone);
    MONOCHROME1 means the opposite and must be inverted. `assume_monochrome1=True` reproduces a
    pipeline written for one site's machine that always inverts, whatever the file says.
    """
    from PIL import Image

    a = ds.pixel_array.astype(np.float32)
    lo, hi = np.percentile(a, [0.5, 99.5])
    a = np.clip((a - lo) / max(hi - lo, 1), 0, 1)
    if assume_monochrome1 or ds.get("PhotometricInterpretation") == "MONOCHROME1":
        a = 1 - a
    im = Image.fromarray((a * 255).astype(np.uint8))
    w, h = im.size
    s = min(w, h)
    im = im.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s)).resize((SIZE, SIZE), Image.LANCZOS)
    return np.asarray(im, dtype=np.float32)


def embed_pixels(pixels, model_file=MODEL_FILE, batch=32):
    """Run the pretrained chest X-ray network: (n, 224, 224) arrays (0-255) -> (n, 1024) features."""
    import onnxruntime as ort

    session = ort.InferenceSession(str(model_file))
    out = []
    for i in range(0, len(pixels), batch):
        x = pixels[i:i + batch] / 255 * 2048 - 1024            # the scaling the network was trained with
        out.append(session.run(None, {"image": x[:, None].astype(np.float32)})[0])
    return np.concatenate(out)


# ---------------------------------------------------------------- evaluation


def threshold_for_sensitivity(y, p, target=0.90):
    """The highest threshold that still catches `target` of the TB cases in (y, p)."""
    return float(np.quantile(np.asarray(p)[np.asarray(y) == 1], 1 - target))


def screening_metrics(y, p, threshold):
    """What a TB programme cares about at a given threshold."""
    from sklearn.metrics import roc_auc_score

    y, p = np.asarray(y), np.asarray(p)
    flag = p >= threshold
    return {
        "people": len(y), "TB cases": int(y.sum()),
        "roc_auc": roc_auc_score(y, p) if len(set(y)) == 2 else np.nan,
        "sensitivity": flag[y == 1].mean() if (y == 1).any() else np.nan,     # TB cases flagged
        "specificity": 1 - flag[y == 0].mean() if (y == 0).any() else np.nan,  # people without TB not flagged
        "flag_rate": flag.mean(),                                              # share sent for a lab test
    }


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "download-images":
        download_images(int(sys.argv[2]) if len(sys.argv) > 2 else None)
    else:
        print(__doc__)
