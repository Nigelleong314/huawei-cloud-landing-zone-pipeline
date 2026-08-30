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
                          errors="replace", cwd=str(REPO),
                          stdin=subprocess.DEVNULL, **kw)


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
    draft_path = ws / "specs" / "lz.spec.unittest.json"
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    assert draft["customer"] == "unittest"
    assert "NEUTRAL DRAFT" in draft["source"]
    # neutral baseline: no deployable value survives from any example
    body = json.dumps(draft["sheets"])
    for example_value in ("10.42.", "EXAMPLE-", "example-lz-obs"):
        assert example_value not in body, f"example value leaked: {example_value}"
    # and, by design, the uninterpreted draft does NOT validate clean
    rv = run("lz_pipeline", "spec-validate", str(draft_path))
    assert rv.returncode == 1, "neutral draft must fail validation until interpreted"
    decisions = (ws / "specs" / "lz.spec.unittest.decisions.md").read_text(encoding="utf-8")
    # blank questionnaire: nothing answered, so every question is defaulted or open
    assert "## ANSWERED (0)" in decisions
    assert "## OPEN" in decisions
    # a second run must refuse to clobber without --force
    r2 = run("lz_pipeline.lzctl", "assess", str(dump), "--customer", "unittest",
             "--workspace", str(ws))
    assert r2.returncode == 1
    assert "refusing" in r2.stdout


def test_build_gate_blocks_on_open_decisions(blank_questionnaire, tmp_path):
    """The Review-3 scenario: OPEN items must BLOCK build until resolved."""
    dump = tmp_path / "dump.json"
    run("lz_pipeline.tools.dump_questionnaire", str(blank_questionnaire), "-o", str(dump))
    ws = tmp_path / "ws"
    run("lz_pipeline.lzctl", "assess", str(dump), "--customer", "gate",
        "--workspace", str(ws))
    specs = ws / "specs"
    dec_path = specs / "lz.spec.gate.decisions.json"
    dec = json.loads(dec_path.read_text(encoding="utf-8"))
    open_items = [i for i in dec["items"] if i["state"] == "OPEN"]
    assert open_items, "blank questionnaire must yield OPEN items"

    # a KNOWN-GOOD spec next to unresolved decisions still refuses to build:
    # the gate is on the decisions file, not on spec quality
    import shutil
    shutil.copy2(REPO / "pipeline/lz_pipeline/fixtures/example.spec.json",
                 specs / "lz.spec.gate.json")
    r = run("lz_pipeline", "build", "--ir", str(specs / "lz.spec.gate.json"),
            "--envs-dir", str(tmp_path / "envs"),
            "--scaffold-dir", str(REPO / "terraform" / "scaffold"))
    assert r.returncode == 3, f"expected gate block, got {r.returncode}: {r.stderr}"
    assert "unresolved OPEN decisions" in r.stderr

    # resolving every OPEN item unblocks the build
    for i in dec["items"]:
        if i["state"] == "OPEN":
            i["resolution"] = {"status": "ANSWERED", "approved_by": "unittest",
                               "reason": "test resolution"}
    dec_path.write_text(json.dumps(dec), encoding="utf-8")
    r = run("lz_pipeline", "build", "--ir", str(specs / "lz.spec.gate.json"),
            "--envs-dir", str(tmp_path / "envs"),
            "--scaffold-dir", str(REPO / "terraform" / "scaffold"))
    assert r.returncode == 0, r.stdout[-500:] + r.stderr[-500:]
