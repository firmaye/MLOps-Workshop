"""Check that this laptop is ready for the MLOps workshop.

Run from the repo root, with the environment active:

    python check_setup.py

Prints one line per item (PASS, WARN or FAIL, with a hint for anything that isn't PASS)
and saves the same report to setup_report.txt. Please send setup_report.txt to the
organisers, even if everything passes.

Uses only the Python standard library, so it runs even when packages are missing.
"""

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import urllib.request
from importlib import metadata
from pathlib import Path

REPO = Path(__file__).resolve().parent
os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")   # keep the report free of MLflow import messages
LLM_API = "https://openrouter.ai/api/v1"   # the LLM demo calls hosted open-weight models here
MIN_FREE_GB = 10
MIN_RAM_GB = 8

# package name in the lock file -> module to import
PACKAGES = {
    "numpy": "numpy", "pandas": "pandas", "scikit-learn": "sklearn", "matplotlib": "matplotlib",
    "dvc": "dvc", "great-expectations": "great_expectations", "mlflow": "mlflow",
    "fairlearn": "fairlearn", "evidently": "evidently", "prefect": "prefect",
    "onnxruntime": "onnxruntime", "pillow": "PIL", "openai": "openai", "ipykernel": "ipykernel",
}

results = []   # (status, item, detail)


def report(status, item, detail=""):
    results.append((status, item, detail))
    print(f"{status:4s}  {item}" + (f"  ->  {detail}" if detail else ""))


def run(cmd):
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        return (out.stdout + out.stderr).strip()
    except Exception:
        return None


def ram_gb():
    try:
        if sys.platform.startswith("linux"):
            kb = int(re.search(r"MemTotal:\s+(\d+)", Path("/proc/meminfo").read_text()).group(1))
            return kb / 1024 ** 2
        if sys.platform == "darwin":
            return int(run(["sysctl", "-n", "hw.memsize"])) / 1024 ** 3
        if sys.platform == "win32":
            import ctypes

            class MEM(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = MEM()
            m.dwLength = ctypes.sizeof(MEM)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return m.ullTotalPhys / 1024 ** 3
    except Exception:
        return None


def locked_versions():
    """Versions pinned in requirements.lock (ignoring platform markers)."""
    pins = {}
    for line in (REPO / "requirements.lock").read_text().splitlines():
        m = re.match(r"^([A-Za-z0-9_.-]+)==([^\s;]+)", line)
        if m:
            pins[m.group(1).lower().replace("_", "-")] = m.group(2)
    return pins


def check_machine():
    ram = ram_gb()
    if ram is None:
        report("WARN", "Memory", "could not detect; the workshop needs at least 8 GB")
    elif ram < MIN_RAM_GB - 0.5:
        report("FAIL", f"Memory: {ram:.0f} GB", "at least 8 GB is needed; tell the organisers so we can pair you up")
    else:
        report("PASS", f"Memory: {ram:.0f} GB")

    free = shutil.disk_usage(REPO).free / 1024 ** 3
    if free < MIN_FREE_GB:
        report("FAIL", f"Free disk space: {free:.0f} GB", f"free up space: at least {MIN_FREE_GB} GB after installing")
    else:
        report("PASS", f"Free disk space: {free:.0f} GB")

    git = run(["git", "--version"])
    report("PASS", git) if git and git.startswith("git version") else report("FAIL", "git", "install git (see the setup guide)")


def check_python():
    v = sys.version_info
    if (v.major, v.minor) == (3, 12):
        report("PASS", f"Python {platform.python_version()}")
    else:
        report("FAIL", f"Python {platform.python_version()}", "the workshop uses Python 3.12: activate .venv (see the setup guide)")
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    if in_venv and Path(sys.prefix).resolve() == (REPO / ".venv").resolve():
        report("PASS", "Running inside the workshop environment (.venv)")
    else:
        report("FAIL", "Not running inside .venv", "activate it: `source .venv/bin/activate` (macOS/Linux) or `.venv\\Scripts\\activate` (Windows)")


def check_packages():
    pins = locked_versions()
    missing, wrong = [], []
    for dist, module in PACKAGES.items():
        try:
            installed = metadata.version(dist)
        except metadata.PackageNotFoundError:
            missing.append(dist)
            continue
        want = pins.get(dist)
        if want and installed != want:
            wrong.append(f"{dist} {installed} (lock: {want})")
    if missing:
        report("FAIL", "Packages missing: " + ", ".join(missing), "run `uv pip sync requirements.lock --python .venv`")
    elif wrong:
        report("WARN", "Package versions differ from the lock: " + "; ".join(wrong), "run `uv pip sync requirements.lock --python .venv`")
    else:
        report("PASS", f"Workshop packages ({len(PACKAGES)} checked) match requirements.lock")
    if not missing:
        broken = []
        for dist, module in PACKAGES.items():
            try:
                __import__(module)
            except Exception as e:
                broken.append(f"{module} ({type(e).__name__})")
        if broken:
            report("FAIL", "Packages that fail to import: " + ", ".join(broken), "send this report to the organisers")


def check_llm_api():
    """The LLM demo uses hosted open-weight models through OpenRouter; nothing to install.
    The shared key is handed out at the workshop, so here we only check that the service is reachable."""
    try:
        with urllib.request.urlopen(f"{LLM_API}/models", timeout=15) as r:
            n = len(json.load(r)["data"])
        report("PASS", f"LLM service reachable (openrouter.ai, {n} models listed)")
    except Exception as e:
        report("FAIL", "Cannot reach openrouter.ai", f"check your internet connection or firewall ({type(e).__name__})")
        return
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        report("INFO", "LLM key not set yet", "the shared key is given out at the workshop")
        return
    try:
        req = urllib.request.Request(f"{LLM_API}/key", headers={"Authorization": f"Bearer {key}"})
        with urllib.request.urlopen(req, timeout=15):
            report("PASS", "LLM key accepted")
    except Exception as e:
        report("FAIL", "LLM key rejected", f"check OPENROUTER_API_KEY ({type(e).__name__})")


def check_downloads():
    manifest = json.loads((REPO / "scripts" / "downloads.json").read_text())
    for group, items in manifest.items():
        for item in items:
            if item["url"].startswith("TODO"):
                report("INFO", f"Data '{group}': not published yet", "nothing to do for now")
                continue
            target = REPO / "downloads" / item["file"]
            done = (REPO / "downloads" / item["unzip"] / ".complete") if item.get("unzip") else target
            if target.exists() and target.stat().st_size == item["size"] and done.exists():
                report("PASS", f"Data '{group}': {item['file']}")
            elif item.get("optional"):
                report("INFO", f"Optional data '{group}' not downloaded (fine)", f"`python scripts/download.py {group}` if you want it")
            else:
                report("FAIL", f"Data '{group}' missing or incomplete", f"run `python scripts/download.py {group}`")


def main():
    print(f"MLOps workshop setup check  ({platform.platform()}, {platform.machine()})\n")
    for section in (check_machine, check_python, check_packages, check_llm_api, check_downloads):
        try:
            section()
        except Exception as e:
            report("FAIL", f"{section.__name__} crashed: {type(e).__name__}: {e}", "send this report to the organisers")

    fails = sum(s == "FAIL" for s, _, _ in results)
    warns = sum(s == "WARN" for s, _, _ in results)
    summary = "READY" if not fails else f"NOT READY: {fails} item(s) to fix"
    print(f"\n{summary}" + (f" ({warns} warning(s))" if warns else ""))

    lines = [f"MLOps workshop setup report", f"platform: {platform.platform()} {platform.machine()}",
             f"python: {sys.version.split()[0]} at {sys.executable}", f"result: {summary}", ""]
    lines += [f"{s:4s}  {i}" + (f"  ->  {d}" if d else "") for s, i, d in results]
    (REPO / "setup_report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Saved to setup_report.txt: please send it to the organisers.")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
