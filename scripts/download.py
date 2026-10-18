"""Download (or copy from a USB stick) the large files the workshop demos need.

Usage, from the repo root with the environment active:

    python scripts/download.py tb                 # download the TB X-ray bundle
    python scripts/download.py all                # everything listed in downloads.json
    python scripts/download.py tb --from E:\\     # copy from a USB stick instead of downloading
    python scripts/download.py --list             # show what is available

What it does, for each file in scripts/downloads.json:
  1. skips it if it is already in downloads/ with the right checksum (safe to re-run);
  2. otherwise downloads it, resuming a partial download after a dropped connection,
     or copies it from the folder given with --from;
  3. checks the SHA-256 checksum, so a corrupted or incomplete file is never used;
  4. unzips it if the manifest says so.

Only the Python standard library is used, except for files hosted on Kaggle, which need the
workshop environment (kagglehub) to be installed first.
"""

import argparse
import hashlib
import json
import shutil
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MANIFEST = REPO / "scripts" / "downloads.json"
DEST = REPO / "downloads"          # ignored by git
CHUNK = 1024 * 1024                # 1 MB
# some servers refuse requests without a browser-like User-Agent
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def human(n):
    for unit in ["B", "KB", "MB", "GB"]:
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def fetch(url, target, size, retries=8):
    """Download url to target, resuming from where a previous attempt stopped."""
    for attempt in range(1, retries + 1):
        have = target.stat().st_size if target.exists() else 0
        if size and have >= size:
            return
        headers = {"User-Agent": USER_AGENT} | ({"Range": f"bytes={have}-"} if have else {})
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                # 206 = the server is resuming; 200 = it sent the whole file again
                mode = "ab" if resp.status == 206 else "wb"
                if mode == "wb":
                    have = 0
                with open(target, mode) as out:
                    last = time.time()
                    while block := resp.read(CHUNK):
                        out.write(block)
                        have += len(block)
                        if time.time() - last > 2:
                            pct = f" ({100 * have / size:.0f}%)" if size else ""
                            print(f"\r    {human(have)}{pct}   ", end="", flush=True)
                            last = time.time()
            print(f"\r    {human(have)} downloaded        ")
            return
        except urllib.error.HTTPError as e:
            if e.code == 416:       # "range not satisfiable": the file is already complete
                return
            if 400 <= e.code < 500:  # refused or not found: retrying won't help
                raise RuntimeError(f"the server refused the download (HTTP {e.code}); "
                                   "use the USB copy: python scripts/download.py <group> --from <USB folder>")
            print(f"\n    server error ({e}); retrying in {2 * attempt} s (attempt {attempt}/{retries})")
            time.sleep(2 * attempt)
        except Exception as e:  # dropped connection, timeout, ...: wait and resume
            print(f"\n    interrupted ({e}); retrying in {2 * attempt} s (attempt {attempt}/{retries})")
            time.sleep(2 * attempt)
    raise RuntimeError(f"could not download {url} after {retries} attempts")


def get(item, source_dir):
    target = DEST / item["file"]
    target.parent.mkdir(parents=True, exist_ok=True)
    print(f"- {item['file']} ({human(item['size'])}): {item['description']}")

    if target.exists() and target.stat().st_size == item["size"] and sha256(target) == item["sha256"]:
        print("    already present, checksum OK")
    else:
        if source_dir:
            src = Path(source_dir) / item["file"]
            if not src.exists():
                src = Path(source_dir) / Path(item["file"]).name
            print(f"    copying from {src}")
            shutil.copyfile(src, target)
        elif item.get("kaggle"):          # public Kaggle dataset file, fetched with kagglehub
            import kagglehub

            print(f"    downloading from Kaggle ({item['kaggle']['dataset']})")
            shutil.copyfile(kagglehub.dataset_download(item["kaggle"]["dataset"], path=item["kaggle"]["path"]), target)
        else:
            if item["url"].startswith("TODO"):
                raise RuntimeError("this file is not published yet; check back after the organisers' announcement")
            fetch(item["url"], target, item["size"])
        if sha256(target) != item["sha256"]:
            target.unlink()
            raise RuntimeError("checksum mismatch: the file was corrupted and has been deleted; run the command again")
        print("    checksum OK")

    if item.get("unzip"):
        out = DEST / item["unzip"]
        marker = out / ".complete"
        if not marker.exists():
            print(f"    unzipping to downloads/{item['unzip']}/")
            with zipfile.ZipFile(target) as z:
                z.extractall(out)
            marker.write_text(item["sha256"])


def main():
    manifest = json.loads(MANIFEST.read_text())
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("what", nargs="?", help="a group from downloads.json, or 'all'")
    p.add_argument("--from", dest="source", help="folder (e.g. a USB stick) to copy from instead of downloading")
    p.add_argument("--list", action="store_true", help="list the available groups")
    args = p.parse_args()

    if args.list or not args.what:
        for group, items in manifest.items():
            total = sum(i["size"] for i in items)
            print(f"{group:6s} {human(total):>8s}  " + "; ".join(i["description"] for i in items))
        return

    groups = list(manifest) if args.what == "all" else [args.what]
    for g in groups:
        if g not in manifest:
            sys.exit(f"unknown group '{g}'; choose from: {', '.join(manifest)} or all")
        print(f"\n[{g}]")
        for item in manifest[g]:
            try:
                get(item, args.source)
            except Exception as e:
                sys.exit(f"    FAILED: {e}")
    print("\nDone. Run `python check_setup.py` to confirm everything is in place.")


if __name__ == "__main__":
    main()
