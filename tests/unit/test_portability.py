"""Portability gates introduced by the product assembly: fail-loud region,
configurable module source root, JSON Schema emission, transient matcher."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def test_home_region_fails_loud():
    # _home_region takes the Global.Settings table itself
    from lz_pipeline.core.helpers import _home_region
    with pytest.raises(SystemExit, match="home_region is required"):
        _home_region({})
    assert _home_region({"home_region": "eu-west-101"}) == "eu-west-101"


def test_module_source_root_env_override(tmp_path):
    env = dict(os.environ)
    env["LZ_MODULE_SOURCE_ROOT"] = "../../custom-modules"
    r = subprocess.run(
        [sys.executable, "-X", "utf8", "-c",
         "from lz_pipeline.core.helpers import MODULE_SOURCE_ROOT; print(MODULE_SOURCE_ROOT)"],
        capture_output=True, text=True, env=env, cwd=str(REPO),
        stdin=subprocess.DEVNULL)
    assert r.stdout.strip() == "../../custom-modules"


def test_jsonschema_generation(tmp_path):
    out = tmp_path / "s.json"
    r = subprocess.run([sys.executable, "-X", "utf8", "-m",
                        "lz_pipeline.tools.gen_jsonschema", "-o", str(out)],
                       capture_output=True, text=True, cwd=str(REPO),
                       stdin=subprocess.DEVNULL)
    assert r.returncode == 0, r.stdout + r.stderr
    d = json.loads(out.read_text(encoding="utf-8"))
    sheets = d["properties"]["sheets"]["properties"]
    assert "05_Network" in sheets and "09_CFW" in sheets
    assert "home_region" in sheets["Global"]["properties"]["Settings"]["properties"]


def test_committed_schema_is_fresh():
    """The committed schemas/lz.spec.schema.json must match a regeneration."""
    committed = REPO / "schemas" / "lz.spec.schema.json"
    assert committed.exists(), "regenerate: python -m lz_pipeline.tools.gen_jsonschema"
    from lz_pipeline.tools.gen_jsonschema import build_schema
    fresh = json.dumps(build_schema(), indent=2, ensure_ascii=False) + "\n"
    assert committed.read_text(encoding="utf-8") == fresh, \
        "schema drifted: python -m lz_pipeline.tools.gen_jsonschema"


def test_transient_matcher_is_specific():
    from lz_pipeline import lzctl
    assert lzctl._is_transient("Error: LTS.2101 something")
    assert lzctl._is_transient("EPS.0004 Permission error")
    assert not lzctl._is_transient("Error: 403 Forbidden")   # too broad on purpose
    assert not lzctl._is_transient("")
    assert not lzctl._is_transient(None)
