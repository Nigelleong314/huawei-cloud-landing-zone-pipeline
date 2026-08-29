"""Pytest bridge over the proven assert-script suites.

The scripts are self-contained gates (each exits non-zero on failure); this
bridge gives them pytest discovery, per-suite reporting, and CI selection
without rewriting battle-tested checks.
"""

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SUITES = sorted((REPO / "pipeline" / "lz_pipeline" / "tests").glob("test_*.py"))
SUITES += sorted((REPO / "app" / "tests").glob("test_*.py"))


@pytest.mark.parametrize("script", SUITES, ids=lambda p: p.stem)
def test_suite(script):
    r = subprocess.run([sys.executable, "-X", "utf8", str(script)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=str(REPO))
    assert r.returncode == 0, f"{script.name} failed:\n{r.stdout[-3000:]}\n{r.stderr[-800:]}"
