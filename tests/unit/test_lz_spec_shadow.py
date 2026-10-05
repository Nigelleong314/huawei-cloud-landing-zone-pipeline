"""A folder named lz_spec in the working directory must not shadow the pipeline.

Under `py -m lz_pipeline` the working directory is first on sys.path, so a
customer workspace holding an `lz_spec/` folder became the `lz_spec`
package and the run died later with ModuleNotFoundError. The CLI now stops
up front and names the shadowing folder.
"""

import importlib.machinery
import importlib.util
import subprocess
import sys
from pathlib import Path

from lz_pipeline import __main__ as cli

FIXTURE = Path(__file__).resolve().parents[2] / "pipeline/lz_pipeline/fixtures/example.spec.json"


def test_namespace_lz_spec_is_named(tmp_path, monkeypatch):
    shadow = tmp_path / "lz_spec"
    ns = importlib.machinery.ModuleSpec("lz_spec", None, is_package=True)
    ns.submodule_search_locations = [str(shadow)]
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: ns)
    msg = cli.lz_spec_problem()
    assert msg and "without __init__.py" in msg and str(shadow) in msg


def test_foreign_lz_spec_in_cwd_stops_the_cli(tmp_path):
    assert cli.lz_spec_problem() is None          # the real package is fine
    (tmp_path / "lz_spec").mkdir()
    (tmp_path / "lz_spec" / "__init__.py").write_text("", encoding="utf-8")
    r = subprocess.run([sys.executable, "-X", "utf8", "-m", "lz_pipeline",
                        "spec-validate", str(FIXTURE)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=str(tmp_path), stdin=subprocess.DEVNULL)
    assert r.returncode == 1
    assert "shadows the pipeline's own package" in r.stderr
    assert str(tmp_path / "lz_spec") in r.stderr
