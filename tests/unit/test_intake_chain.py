"""Intake-chain coverage the legacy suites never had: questionnaire coverage
check, mechanical dump round-trip, and the deterministic assess pre-pass."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def run(mod, *args, **kw):
    return subprocess.run([sys.executable, "-X", "utf8", "-m", mod, *args],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", cwd=str(REPO), **kw)


def test_questionnaire_coverage_check_passes():
    r = run("lz_pipeline.tools.gen_questionnaire", "--check")
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.fixture(scope="module")
def blank_questionnaire(tmp_path_factory):
    out = tmp_path_factory.mktemp("q") / "q.xlsx"
    r = run("lz_pipeline.tools.gen_questionnaire", "-o", str(out))
    assert r.returncode == 0, r.stdout + r.stderr
    return out


def test_dump_extracts_wiring_and_meta(blank_questionnaire, tmp_path):
    out = tmp_path / "dump.json"
    r = run("lz_pipeline.tools.dump_questionnaire", str(blank_questionnaire),
            "-o", str(out))
    assert r.returncode == 0, r.stdout + r.stderr
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["meta"].get("schema_version"), "meta must carry the schema version"
    assert len(d["answers"]) >= 40
    assert all(a["ref"][0] in "CD" for a in d["answers"])
    assert set(d["appendices"]) == {"A", "B", "C"}
    # every answer carries its wiring targets or an explicit empty list
    assert all("targets" in a for a in d["answers"])


def test_assess_is_deterministic_and_never_guesses(blank_questionnaire, tmp_path):
    dump = tmp_path / "dump.json"
    run("lz_pipeline.tools.dump_questionnaire", str(blank_questionnaire), "-o", str(dump))
    ws = tmp_path / "ws"
    r = run("lz_pipeline.lzctl", "assess", str(dump), "--customer", "unittest",
            "--workspace", str(ws))
    assert r.returncode == 0, r.stdout + r.stderr
    draft = json.loads((ws / "specs" / "lz.spec.unittest.json").read_text(encoding="utf-8"))
    assert draft["customer"] == "unittest"
    assert "DRAFT" in draft["source"]
    decisions = (ws / "specs" / "lz.spec.unittest.decisions.md").read_text(encoding="utf-8")
    # blank questionnaire: nothing answered, so every question is defaulted or open
    assert "## Answered (0)" in decisions
    assert "## Open questions" in decisions
    # a second run must refuse to clobber without --force
    r2 = run("lz_pipeline.lzctl", "assess", str(dump), "--customer", "unittest",
             "--workspace", str(ws))
    assert r2.returncode == 1
    assert "refusing" in r2.stdout
