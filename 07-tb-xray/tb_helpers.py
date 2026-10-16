"""Helpers for the TB chest X-ray demo, shared by the notebook and the facilitator scripts.

Kept small and plain on purpose: the notebook is where the story is told.
"""

from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
SIZE = 224                       # the pretrained model works on 224 x 224 grayscale images
MODEL_FILE = HERE.parent / "downloads" / "tb" / "cxr_densenet121.onnx"   # optional; see README


# ---------------------------------------------------------------- images


def square_resize(path, size=SIZE):
    """Open any X-ray file, convert to grayscale, cut the largest centred square, resize."""
    im = Image.open(path).convert("L")
    w, h = im.size
    s = min(w, h)
    left, top = (w - s) // 2, (h - s) // 2
    return im.crop((left, top, left + s, top + s)).resize((size, size), Image.LANCZOS)


def load_pixels(paths):
    """Images as one array: (n_images, 224, 224), values 0-255."""
    return np.stack([np.asarray(Image.open(p).convert("L"), dtype=np.float32) for p in paths])


def image_checks(paths):
    """The image equivalent of a Great Expectations suite: one row of facts per file.

    Each column is something you can write a rule about: size, colour mode, brightness,
    contrast, and how much of the image is pure black or pure white (cropping, burned-in borders).
    """
    rows = []
    for p in paths:
        im = Image.open(p)
        a = np.asarray(im.convert("L"), dtype=np.float32)
        rows.append({
            "file": Path(p).name,
            "width": im.size[0], "height": im.size[1], "mode": im.mode,
            "mean": a.mean(),                     # overall brightness
            "std": a.std(),                       # contrast
            "pct_black": (a <= 5).mean() * 100,   # % of pixels that are (almost) pure black
            "pct_white": (a >= 250).mean() * 100,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- features


def embed(paths, model_file=MODEL_FILE, batch=32):
    """Run the pretrained chest X-ray network and return 1024 features per image.

    The network was trained on other X-ray collections; we only use it to turn each image
    into 1024 numbers, then train a small, fast classifier on those numbers.
    """
    import onnxruntime as ort

    session = ort.InferenceSession(str(model_file))
    out = []
    for i in range(0, len(paths), batch):
        x = load_pixels(paths[i:i + batch])
        x = x / 255 * 2048 - 1024                      # the scaling the network was trained with
        out.append(session.run(None, {"image": x[:, None].astype(np.float32)})[0])
    return np.concatenate(out)


def load_data():
    """metadata (one row per image) and the precomputed features, in the same order."""
    meta = pd.read_csv(DATA / "metadata.csv")
    z = np.load(DATA / "embeddings.npz")
    feats = pd.DataFrame(z["features"], index=z["image_id"]).loc[meta.image_id].to_numpy()
    meta["path"] = [str(DATA / f) for f in meta.file]
    return meta, feats


# ---------------------------------------------------------------- evaluation


def threshold_for_sensitivity(y, p, target=0.90):
    """The highest threshold that still catches `target` of the TB cases in (y, p)."""
    return float(np.quantile(p[np.asarray(y) == 1], 1 - target))


def screening_metrics(y, p, threshold):
    """What a TB programme cares about at a given threshold."""
    from sklearn.metrics import roc_auc_score

    y = np.asarray(y)
    flag = p >= threshold
    return {
        "roc_auc": roc_auc_score(y, p) if len(set(y)) == 2 else np.nan,
        "sensitivity": flag[y == 1].mean() if (y == 1).any() else np.nan,   # TB cases flagged
        "specificity": 1 - flag[y == 0].mean() if (y == 0).any() else np.nan,  # normals not flagged
        "flag_rate": flag.mean(),                                            # share sent for a lab test
    }
