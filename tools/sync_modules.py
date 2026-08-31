"""Refresh the vendored Terraform module snapshot from an upstream checkout.

Usage: python tools/sync_modules.py <upstream-modules-dir>

Copies the tree (excluding caches/state/backups), rewrites nothing, updates
PROVENANCE.md with the new content hash and date, and prints a diff summary.
Review `git diff terraform/modules` before committing.
"""

import datetime
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DST = REPO / "terraform" / "modules"
EXCLUDE_DIRS = {".terraform", "__pycache__", ".git"}
EXCLUDE_SUFFIXES = (".backup", ".bak")


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    src = Path(sys.argv[1]).resolve()
    if not (src / "organization").is_dir():
        print(f"{src} does not look like a module library (no organization/)")
        return 2
    if src == DST or DST in src.parents or src in DST.parents:
        print(f"source {src} overlaps the destination {DST} - the sync would "
              "delete its own source; pass an UPSTREAM checkout")
        return 2

    def ignore(d, names):
        return [n for n in names
                if n in EXCLUDE_DIRS or n.endswith(EXCLUDE_SUFFIXES)
                or "tfstate" in n or n == ".terraform.lock.hcl"]

    if DST.exists():
        shutil.rmtree(DST)
    shutil.copytree(src, DST, ignore=ignore)

    h = hashlib.sha256()
    n = 0
    for p in sorted(DST.rglob("*")):
        if p.is_file() and p.name != "PROVENANCE.md":
            h.update(p.relative_to(DST).as_posix().encode())
            h.update(p.read_bytes())
            n += 1
    today = datetime.date.today().isoformat()
    (DST / "PROVENANCE.md").write_text(
        "# Module snapshot provenance\n\n"
        f"Synced from an upstream module library checkout on {today}.\n"
        f"Files: {n}. Content hash (excluding this file): sha256:{h.hexdigest()}\n"
        "Refresh with tools/sync_modules.py; review the diff before committing.\n",
        encoding="utf-8")
    print(f"synced {n} files -> {DST}\nsha256 {h.hexdigest()[:16]}...")
    r = subprocess.run(["git", "-C", str(REPO), "diff", "--stat", "--", "terraform/modules"],
                       capture_output=True, text=True)
    tail = (r.stdout or "").strip().splitlines()
    print(tail[-1] if tail else "(no git diff available)")
    print("review: git diff terraform/modules")
    return 0


if __name__ == "__main__":
    sys.exit(main())
