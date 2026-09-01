"""The gap register and the gates that close the "fully answered questionnaire
proves nothing" hole: LZR-032 (no placeholder survives), LZR-033 (reserved
security toggles), `lzctl gap add`, and the app's decisions endpoints.

Traced to a demo run where a 54/54-answered questionnaire produced 0 OPEN
decisions, yet the spec that got built still carried four values nobody had
supplied.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "pipeline" / "lz_pipeline" / "fixtures" / "example.spec.json"


def run(mod, *args):
    return subprocess.run([sys.executable, "-X", "utf8", "-m", mod, *args],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", cwd=str(REPO),
                          stdin=subprocess.DEVNULL)


def sheets():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["sheets"]


# ── LZR-032: placeholders never reach build ────────────────────────────────

def test_clean_fixture_has_no_placeholder_findings():
    from lz_pipeline.rules import placeholder_findings
    assert placeholder_findings(sheets()) == []


def test_placeholder_in_any_field_is_an_error():
    from lz_pipeline.rules import placeholder_findings
    spec = sheets()
    spec.setdefault("10_VPN", {}).setdefault("CustomerGateways", []).append(
        {"Enabled": "TRUE", "Name": "dc1", "IP": "REPLACE_WITH_DC1_PUBLIC_IP", "ASN": 65010})
    found = placeholder_findings(spec)
    assert [f["path"] for f in found] == ["10_VPN.CustomerGateways[dc1].IP"]
    assert found[0]["sheet"] == "10_VPN" and found[0]["column"] == "IP"


def test_vpn_psk_placeholder_is_exempt():
    """LZR-027 REQUIRES a placeholder there (a literal secret would be worse);
    lzctl preflight blocks it before it can become a live tunnel key."""
    from lz_pipeline.rules import placeholder_findings
    spec = sheets()
    spec.setdefault("10_VPN", {}).setdefault("Connections", []).append(
        {"Enabled": "TRUE", "Name": "t1", "PSK": "REPLACE_WITH_STRONG_PSK"})
    assert placeholder_findings(spec) == []


# ── LZR-033: a flag that deploys nothing must not read as delivered ────────

@pytest.mark.parametrize("field", ["enable_hss", "enable_dbss"])
def test_reserved_security_toggle_blocks(field):
    from lz_pipeline import rules
    spec = sheets()
    spec.setdefault("07_Security", {}).setdefault("Settings", {})[field] = True
    msgs = [f.message for f in rules.run_spec_rules(spec) if f.rule_id == "LZR-033"]
    assert any(field in m and "deploys nothing" in m for m in msgs)


def test_reserved_security_toggles_silent_when_false():
    from lz_pipeline import rules
    spec = sheets()
    spec.setdefault("07_Security", {}).setdefault("Settings", {}).update(
        {"enable_hss": False, "enable_dbss": False})
    assert not [f for f in rules.run_spec_rules(spec) if f.rule_id == "LZR-033"]


# ── lzctl gap add: the only sanctioned way to grow a decision set ──────────

@pytest.fixture
def assessed(tmp_path):
    """A real assess() output: neutral draft + decisions files."""
    dump = tmp_path / "dump.json"
    dump.write_text(json.dumps({
        "source_file": "q.xlsx", "meta": {"questionnaire_version": "1.1"},
        "answers": [{"ref": "C1", "question": "Q one?", "answer": "an answer",
                     "targets": ["01_Foundation.Settings"], "default_if_silent": ""}],
        "appendices": {},
    }), encoding="utf-8")
    r = run("lz_pipeline.lzctl", "assess", str(dump), "--customer", "t",
            "--workspace", str(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    return tmp_path / "specs" / "lz.spec.t.json"


def test_gap_add_registers_and_blocks_build(assessed, tmp_path):
    before = json.loads(assessed.read_text(encoding="utf-8"))["provenance"]

    r = run("lz_pipeline.lzctl", "gap", "add", "--spec", str(assessed),
            "--field", "08_DNS.ResolverRules[fwd].TargetIPs",
            "--question", "On-prem DNS IPs")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "G1" in r.stdout

    after = json.loads(assessed.read_text(encoding="utf-8"))["provenance"]
    assert after["decision_count"] == before["decision_count"] + 1
    assert after["decision_set_sha256"] != before["decision_set_sha256"]

    # the gap now blocks the build gate (exit 3), by ref
    b = run("lz_pipeline", "build", "--spec", str(assessed),
            "--envs-dir", str(tmp_path / "envs"))
    assert b.returncode == 3, b.stdout + b.stderr
    assert "OPEN G1" in b.stderr

    # ...and the human-readable agenda records it too
    md = assessed.with_name("lz.spec.t.decisions.md").read_text(encoding="utf-8")
    assert "Gaps found during interpretation" in md and "G1" in md


def test_gap_add_refuses_to_launder_an_edited_set(assessed):
    dec = assessed.with_name("lz.spec.t.decisions.json")
    doc = json.loads(dec.read_text(encoding="utf-8"))
    doc["items"][0]["question"] = "tampered"
    dec.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

    r = run("lz_pipeline.lzctl", "gap", "add", "--spec", str(assessed),
            "--field", "X.Y.Z", "--question", "q")
    assert r.returncode == 3
    assert "altered outside this command" in r.stderr


def test_gap_add_needs_questionnaire_lineage(tmp_path):
    plain = tmp_path / "lz.spec.plain.json"
    plain.write_text(json.dumps({"format": "lz-spec-ir/1", "schema_version": "2.2",
                                 "customer": "p", "sheets": {}}), encoding="utf-8")
    r = run("lz_pipeline.lzctl", "gap", "add", "--spec", str(plain),
            "--field", "X.Y.Z", "--question", "q")
    assert r.returncode == 2 and "no questionnaire lineage" in r.stderr


# ── the app's decisions endpoints write ONLY resolutions ───────────────────

def test_app_resolve_writes_resolution_and_keeps_the_hash(assessed):
    from lz_app import server
    from lz_pipeline import model
    from lz_pipeline.lzctl import _decision_set_sha256

    run("lz_pipeline.lzctl", "gap", "add", "--spec", str(assessed),
        "--field", "08_DNS.ResolverRules[fwd].TargetIPs", "--question", "On-prem DNS IPs")

    server.STATE.update({"workspace": assessed.parents[1], "ir": model.load(assessed),
                         "source": str(assessed), "file": assessed.name})
    payload = server.decisions_payload()
    assert payload["available"] and payload["counts"]["blocking"] == 1

    server.resolve_decision("G1", "ANSWERED", "Network Eng", "10.100.1.53, 10.100.2.53")
    assert server.decisions_payload()["counts"]["blocking"] == 0

    # the immutable half is untouched: the spec's provenance hash still matches
    doc = json.loads(assessed.with_name("lz.spec.t.decisions.json").read_text(encoding="utf-8"))
    prov = json.loads(assessed.read_text(encoding="utf-8"))["provenance"]
    assert _decision_set_sha256(doc["items"]) == prov["decision_set_sha256"]


@pytest.mark.parametrize("args,msg", [
    (("G1", "MAYBE", "who", "why"), "status must be one of"),
    (("G1", "ANSWERED", "", "why"), "approved_by and reason"),
    (("G1", "ANSWERED", "who", "  "), "approved_by and reason"),
    (("NOPE", "ANSWERED", "who", "why"), "no decision"),
])
def test_app_resolve_rejects_unauditable_input(assessed, args, msg):
    from lz_app import server
    from lz_pipeline import model
    run("lz_pipeline.lzctl", "gap", "add", "--spec", str(assessed),
        "--field", "X.Y.Z", "--question", "q")
    server.STATE.update({"workspace": assessed.parents[1], "ir": model.load(assessed),
                         "source": str(assessed), "file": assessed.name})
    with pytest.raises(ValueError, match=msg):
        server.resolve_decision(*args)
