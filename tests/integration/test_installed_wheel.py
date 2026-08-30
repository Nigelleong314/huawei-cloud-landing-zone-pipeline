"""Installed-runtime contract: the wheel alone must run the core workflow.

Builds a wheel, installs it into a clean venv, and runs `lzctl validate` and
`lzctl build` against a fixture COPIED OUT of the checkout - proving the
installed package carries every runtime resource (templates, fixtures,
pricing, schema) with no dependence on the repository tree.

Marked `integration`: needs pip + venv and ~a minute; CI runs it in its own
job, plain `pytest` (unit) skips it.
"""

import shutil
import subprocess
import sys
import venv
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[2]


def run(argv, **kw):
    return subprocess.run(argv, capture_output=True, text=True,
                          encoding="utf-8", errors="replace",
                          stdin=subprocess.DEVNULL, **kw)


def test_wheel_is_self_contained(tmp_path):
    # 1. build the wheel from the checkout
    r = run([sys.executable, "-m", "pip", "wheel", str(REPO), "--no-deps",
             "-w", str(tmp_path / "dist")])
    assert r.returncode == 0, r.stdout[-800:] + r.stderr[-800:]
    wheels = list((tmp_path / "dist").glob("*.whl"))
    assert len(wheels) == 1, wheels

    # 2. clean venv + install (openpyxl comes from the running interpreter's
    #    site via the wheel's dependency; install it explicitly to stay offline-safe)
    env_dir = tmp_path / "venv"
    venv.create(env_dir, with_pip=True)
    py = env_dir / ("Scripts" if sys.platform == "win32" else "bin") / "python"
    r = run([str(py), "-m", "pip", "install", "--no-index",
             "--find-links", str(tmp_path / "dist"), "openpyxl", str(wheels[0])])
    if r.returncode != 0:  # offline: fall back to normal index for openpyxl
        r = run([str(py), "-m", "pip", "install", str(wheels[0])])
    assert r.returncode == 0, r.stdout[-800:] + r.stderr[-800:]

    # 3. copy the fixture OUT of the repo; run from a neutral cwd
    work = tmp_path / "work"
    work.mkdir()
    shutil.copy2(REPO / "pipeline/lz_pipeline/fixtures/example.spec.json",
                 work / "spec.json")
    scaffold = tmp_path / "scaffold"
    shutil.copytree(REPO / "terraform" / "scaffold", scaffold)

    r = run([str(py), "-X", "utf8", "-m", "lz_pipeline.lzctl", "--help"], cwd=str(work))
    assert r.returncode == 0, r.stderr[-400:]

    r = run([str(py), "-X", "utf8", "-m", "lz_pipeline.lzctl", "validate", "spec.json"],
            cwd=str(work))
    assert r.returncode == 0, r.stdout[-500:] + r.stderr[-400:]

    r = run([str(py), "-X", "utf8", "-m", "lz_pipeline.lzctl", "build",
             "--ir", "spec.json", "--envs-dir", "envs",
             "--scaffold-dir", str(scaffold)], cwd=str(work))
    assert r.returncode == 0, r.stdout[-800:] + r.stderr[-400:]
    # the template-driven emitters must have produced generated files
    assert (work / "envs" / "04-perimeter" / "providers.generated.tf").exists(), \
        "template-driven codegen produced nothing - wheel is missing resources"
