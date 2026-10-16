"""Facilitator only: build 07-tb-xray/data/ from the two public TB datasets.

Participants never run this; its output (about 20 MB) is committed to the repo.

Inputs (download once, by hand):
  - TBX11K (Nankai University, CC BY 4.0): https://mmcheng.net/tb/  -> unzip; we use imgs/tb,
    imgs/health and annotations/json. (Its imgs/extra folder holds NLM images whose terms forbid
    sharing, so it is never used.)
  - "Dataset of Tuberculosis Chest X-rays Images" (Kiran & Jabeen, Mendeley Data, CC BY 4.0):
    https://data.mendeley.com/datasets/8j2g3csprk  -> folders "TB Chest X-rays" and "Normal Chest X-rays".
  - cxr_densenet121.onnx from export_onnx.py.

    python prepare_data.py --tbx11k path/to/TBX11K --pakistan path/to/pakistan --onnx path/to/cxr_densenet121.onnx

Output: data/images/site_a|site_b/*.png (224 x 224 grayscale), data/metadata.csv, data/embeddings.npz.
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tb_helpers import DATA, embed, square_resize  # noqa: E402

N_PER_CLASS = 200            # images per site per class (TB / normal)
SEED = 20261016

# fixed splits (counts per class): how each site's images are used in the notebook
SPLITS = {
    "A": [("train", 150), ("test", 50)],             # site A: where the model is built
    "B": [("local_sample", 25), ("test", 175)],       # site B: the new site; a small labelled sample + the rest
}


def tbx11k_lesions(root):
    """Share of the image covered by annotated TB lesions, and lesion type, per TBX11K TB image."""
    ann = json.loads((root / "annotations/json/TBX11K_trainval_only_tb.json").read_text())
    files = {i["id"]: i["file_name"] for i in ann["images"]}
    names = {c["id"]: c["name"] for c in ann["categories"]}
    area, kind = {}, {}
    for a in ann["annotations"]:
        f = files[a["image_id"]]
        area[f] = area.get(f, 0) + a["area"] / (a["width"] * a["height"])
        kind.setdefault(f, set()).add(names[a["category_id"]])
    return area, {f: "+".join(sorted(k)) for f, k in kind.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tbx11k", type=Path, required=True)
    ap.add_argument("--pakistan", type=Path, required=True)
    ap.add_argument("--onnx", type=Path, required=True)
    args = ap.parse_args()
    rng = np.random.default_rng(SEED)
    area, kind = tbx11k_lesions(args.tbx11k)

    sources = {
        ("A", 1): sorted((args.tbx11k / "imgs/tb").glob("*.png")),
        ("A", 0): sorted((args.tbx11k / "imgs/health").glob("*.png")),
        ("B", 1): sorted((args.pakistan / "tb").glob("*.jpg")),
        ("B", 0): sorted((args.pakistan / "normal").glob("*.jpg")),
    }
    rows = []
    for (site, tb), files in sources.items():
        picked = rng.choice(files, N_PER_CLASS, replace=False)
        splits = [s for s, n in SPLITS[site] for _ in range(n)]
        for i, (src, split) in enumerate(zip(picked, splits), 1):
            image_id = f"{site.lower()}_{'tb' if tb else 'normal'}_{i:03d}"
            out = DATA / "images" / f"site_{site.lower()}" / f"{image_id}.png"
            out.parent.mkdir(parents=True, exist_ok=True)
            square_resize(src).save(out, optimize=True)
            key = f"tb/{src.name}"
            rows.append({
                "image_id": image_id, "file": str(out.relative_to(DATA)), "site": site, "tb": tb, "split": split,
                "source_dataset": "TBX11K" if site == "A" else "Kiran & Jabeen (Mendeley)",
                "source_file": src.name,
                "lesion_area_pct": round(100 * area[key], 2) if site == "A" and tb and key in area else None,
                "lesion_type": kind.get(key) if site == "A" and tb else None,
            })
    meta = pd.DataFrame(rows)
    meta.to_csv(DATA / "metadata.csv", index=False)
    print(meta.groupby(["site", "split", "tb"]).size())

    print("computing features (a few minutes) ...")
    feats = embed([str(DATA / f) for f in meta.file], model_file=args.onnx)
    np.savez_compressed(DATA / "embeddings.npz", image_id=meta.image_id.to_numpy().astype(str), features=feats.astype(np.float32))
    print("done:", DATA)


if __name__ == "__main__":
    main()
