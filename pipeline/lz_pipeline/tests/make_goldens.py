"""Capture golden files for the emitter split.

Renders every FROZEN fixture through the CURRENT pipeline and snapshots each
generated artifact under tests/goldens/<fixture>/<env>/. Fixtures are synthetic
and must stay that way - see test_goldens.py for why a live customer spec can
never be a golden input.

Recapture only when an output change is intended and reviewed.

Run:  py tests/make_goldens.py          (from lz_pipeline/)
Then: py tests/test_goldens.py          asserts the pipeline reproduces them.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent            # lz_pipeline/tests
PKG = HERE.parent                       # lz_pipeline
ROOT = PKG.parent.parent                # repo root
GOLD = HERE / "goldens"

FIXTURES = {
    "example": PKG / "fixtures" / "example.spec.json",
}
KEEP = ("terraform.tfvars.json", "backend.hcl")


def build_fixture(name: str, ir: Path, out: Path):
    env = dict(os.environ)
    env.pop("HW_ACCESS_KEY", None)
    env.pop("HW_SECRET_KEY", None)
    with tempfile.TemporaryDirectory(prefix=f"lz-gold-{name}-") as td:
        envs = Path(td) / "envs"
        r = subprocess.run([sys.executable, "-X", "utf8", "-m", "lz_pipeline", "build",
                            "--ir", str(ir), "--envs-dir", str(envs),
                            "--scaffold-dir", str(ROOT / "terraform" / "scaffold")],
                           capture_output=True, text=True, env=env, cwd=str(ROOT))
        if r.returncode != 0:
            print(r.stdout[-1200:], r.stderr[-1200:])
            raise SystemExit(f"build failed for {name}")
        n = 0
        for p in sorted(envs.rglob("*")):
            if p.is_file() and (p.name in KEEP or p.name.endswith(".generated.tf")):
                rel = p.relative_to(envs)
                dst = out / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dst)
                n += 1
        print(f"{name}: {n} golden files")


def main():
    if GOLD.exists():
        shutil.rmtree(GOLD)
    for name, ir in FIXTURES.items():
        build_fixture(name, ir, GOLD / name)
    print(f"goldens captured under {GOLD}")


if __name__ == "__main__":
    main()
