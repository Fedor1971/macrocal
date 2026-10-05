"""Build a distributable zip: python tools/make_release.py [--python 3.13 ...] [--no-wheels]

Bundles the app, run.bat and (unless --no-wheels) a "wheels" folder with every dependency for
Windows x64, so the recipient needs no PyPI access, only Python 3.11+. Wheels are tied to the
recipient's Python version: pass --python once per version you need to support.

NOTE: the app still needs internet at run time (fxstreet calendar, economy-intel, Yahoo Finance,
Gemini). Offline, each view shows its own "could not reach ..." message instead of data.

Secrets: a real .streamlit/secrets.toml or .env is NEVER bundled, even if present. Colleagues
create their own from secrets.toml.example.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOP_FILES = ["app.py", "style.py", "run.bat", "requirements.txt", "README.md"]
STREAMLIT_FILES = [".streamlit/config.toml", ".streamlit/secrets.toml.example"]
PACKAGE_DIRS = ["macrocal", "vendor"]  # vendor/ecocal is the vendored calendar library (MIT)
SECRET_FILES = [".env", ".streamlit/secrets.toml"]


def release_files(root: Path) -> list[Path]:
    """Relative paths that go into the zip. An allow-list, so new junk can never sneak in."""
    chosen = [Path(f) for f in TOP_FILES + STREAMLIT_FILES if (root / f).is_file()]
    for directory in PACKAGE_DIRS:
        for path in sorted((root / directory).rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                chosen.append(path.relative_to(root))
    return chosen


def secret_files_present(root: Path) -> list[str]:
    return sorted(f for f in SECRET_FILES if (root / f).exists())


def release_name(rev: str, versions: list[str], online: bool) -> str:
    kind = "online" if online else "offline-py" + "+".join(v.replace(".", "") for v in versions)
    return f"macrocal-{rev or 'dev'}-{kind}"


def pip_download(requirements: Path, wheels: Path, version: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "pip", "download", "-r", str(requirements), "-d", str(wheels),
         "--only-binary=:all:", "--platform", "win_amd64", "--python-version", version, "--implementation", "cp"],
        check=True,
    )  # fmt: skip


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--python", action="append", help="target Python version(s), e.g. 3.13 (default: 3.13)")
    ap.add_argument("--no-wheels", action="store_true", help="online release: recipient installs from PyPI/mirror")
    args = ap.parse_args()
    versions = args.python or ["3.13"]

    present = secret_files_present(ROOT)
    if present:
        print(f"Note: {', '.join(present)} exist locally and are deliberately NOT included.")

    rev = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False
    ).stdout.strip()
    name = release_name(rev, versions, args.no_wheels)
    stage = ROOT / "dist" / name
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True)

    for rel in release_files(ROOT):
        (stage / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, stage / rel)

    if not args.no_wheels:
        wheels = stage / "wheels"
        for v in versions:
            print(f"Downloading wheels for Python {v} (Windows x64)...")
            pip_download(ROOT / "requirements.txt", wheels, v)

    out = ROOT / "dist" / f"{name}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(stage.rglob("*")):
            if p.is_file():
                z.write(p, Path(name) / p.relative_to(stage))
    shutil.rmtree(stage)
    print(f"Built {out} ({out.stat().st_size / 1e6:.0f} MB)")


if __name__ == "__main__":
    main()
