"""Facilitator only: build tb-chest-xray/data/ from the Zambia study's chest X-rays.

Participants never need this: its outputs are committed (about 8 MB). It reads the study's DICOM
images (download them with `python ../tb_helpers.py download-images`, about 1.7 GB), and writes:

  data/zambia_headers.csv      one row per image: acquisition facts from the DICOM header
                               (vendor, software, image format, size, pixel spacing). No personal data.
  data/zambia_features.npz     1024 image features per image (torchxrayvision DenseNet, via ONNX),
                               keyed by the study's anonymised participant id
  data/zambia_features_bug.npz the same, for Chainda South only, computed with the "site 1 pipeline"
                               that ignores the DICOM PhotometricInterpretation flag (part 5's silent bug)

    python build_zambia.py --onnx path/to/cxr_densenet121.onnx
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tb_helpers as tb  # noqa: E402

HEADER_FIELDS = ["Manufacturer", "SoftwareVersions", "PhotometricInterpretation", "Rows", "Columns",
                 "PixelSpacing", "BitsStored"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--onnx", type=Path, default=tb.MODEL_FILE)
    a = ap.parse_args()
    import pydicom

    files = sorted(tb.IMAGES.glob("*.dcm"))
    print(f"{len(files)} DICOM files in {tb.IMAGES}")
    heads, good, ids = [], [], []
    for i, f in enumerate(files):
        ds = pydicom.dcmread(f)
        heads.append({"anon_id": str(ds.PatientID), "file": f.name} |
                     {k: str(ds.get(k)) for k in HEADER_FIELDS})
        ids.append(str(ds.PatientID))
        good.append(tb.dicom_to_224(ds))
        if i % 200 == 0:
            print(f"  read {i}", flush=True)
    heads = pd.DataFrame(heads)
    heads.to_csv(tb.DATA / "zambia_headers.csv", index=False)

    print("computing features ...")
    feats = tb.embed_pixels(np.stack(good), a.onnx)
    np.savez_compressed(tb.DATA / "zambia_features.npz", anon_id=np.array(ids), features=feats.astype(np.float32))

    # the bug: a pipeline written at site 1 (Fujifilm, MONOCHROME1) that always inverts
    konica = heads.PhotometricInterpretation == "MONOCHROME2"
    bad = [tb.dicom_to_224(pydicom.dcmread(f), assume_monochrome1=True) for f in np.array(files)[konica.to_numpy()]]
    np.savez_compressed(tb.DATA / "zambia_features_bug.npz", anon_id=np.array(ids)[konica.to_numpy()],
                        features=tb.embed_pixels(np.stack(bad), a.onnx).astype(np.float32))
    print("done:", heads.groupby("Manufacturer").size().to_dict())


if __name__ == "__main__":
    main()
