"""`lzctl status` derives every phase from artifacts, and `lzctl back` is a
re-entry that never undoes anything.

The point of deriving (rather than storing a pointer) is that the report
cannot drift from reality: touch the spec and the tree is stale, whether or
not anybody declared it. These tests pin that property.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "pipeline" / "lz_pipeline" / "fixtures" / "example.spec.json"
SCAFFOLD = REPO / "terraform" / "scaffold"
PHASE_NAMES = ("intake", "design", "build", "verify_pre", "deploy",
               "verify_post", "deliver")


def lzctl(*args):
    return subprocess.run([sys.executable, "-X", "utf8", "-m", "lz_pipeline.lzctl", *args],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", cwd=str(REPO), stdin=subprocess.DEVNULL)


def flat(text):
    """Collapse whitespace: the report WRAPS, so a prose assertion must not
    depend on where a line happened to break."""
    return " ".join(text.split())


def status(*args):
    return lzctl("status", *args)


def status_json(*args):
    """The contract callers format from - the agent renders this, not the text."""
    r = lzctl("status", "--json", *args)
    return json.loads(r.stdout), r


def phase(doc, name):
    return next(p for p in doc["phases"] if p["name"] == name)


@pytest.fixture
def ws(tmp_path):
    (tmp_path / "specs").mkdir()
    (tmp_path / "specs" / "lz.spec.demo.json").write_text(
        FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    return tmp_path


def built(ws):
    r = subprocess.run([sys.executable, "-X", "utf8", "-m", "lz_pipeline.lzctl", "build",
                        "--spec", str(ws / "specs" / "lz.spec.demo.json"),
                        "--envs-dir", str(ws / "envs-demo"),
                        "--scaffold-dir", str(SCAFFOLD)],
                       capture_output=True, text=True, cwd=str(REPO))
    assert r.returncode == 0, r.stdout + r.stderr
    return ws


# ── the bar reflects artifacts, not memory ─────────────────────────────────

def test_status_before_build_is_at_build(ws):
    r = status("--workspace", str(ws))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "> build" in r.stdout, "the current phase is marked in the text form too"
    assert "2/7 complete" in r.stdout
    assert "lzctl build --spec" in r.stdout       # NEXT is a runnable command
    assert "runner agent" in r.stdout and "cloud none" in r.stdout


def test_status_after_build_advances(ws):
    built(ws)
    r = status("--workspace", str(ws))
    assert "build        complete" in " ".join(r.stdout.split(chr(10)))
    assert "> verify_pre" in r.stdout
    assert "3/7 complete" in r.stdout


def test_touching_the_spec_makes_the_tree_stale(ws):
    built(ws)
    time.sleep(0.01)
    (ws / "specs" / "lz.spec.demo.json").touch()
    r = status("--workspace", str(ws))
    assert r.returncode == 2, "stale must be a gate signal, not a footnote"
    assert "recheck" in r.stdout, "plain words beat jargon: stale reads as recheck"
    assert "the spec is newer than 12 of 12 envs" in flat(r.stdout)
    # staleness is a hint, never a verdict: it must name the check that settles it
    assert "check regen-diff" in r.stdout
    assert "Timestamp hint only. Content may still match." in flat(r.stdout)


def test_missing_deps_json_is_a_blocker(ws):
    built(ws)
    (ws / "envs-demo" / "deps.json").unlink()
    r = status("--workspace", str(ws))
    assert "deps.json missing" in flat(r.stdout)


def test_interrupted_apply_lock_blocks_deploy(ws):
    built(ws)
    (ws / "envs-demo" / "lzctl-logs").mkdir(exist_ok=True)
    (ws / "envs-demo" / "lzctl-logs" / "20260101-000000-apply.log").write_text("x", encoding="utf-8")
    (ws / "envs-demo" / ".lzctl.lock").write_text('{"pid": 1}', encoding="utf-8")
    r = status("--workspace", str(ws))
    assert r.returncode == 3, "a blocked phase must exit 3"
    assert "blocked" in r.stdout
    assert "Do NOT re-apply blindly" in flat(r.stdout)


def test_blocking_decision_shows_as_a_design_blocker(tmp_path):
    dump = tmp_path / "dump.json"
    dump.write_text(json.dumps({
        "source_file": "q.xlsx", "meta": {"questionnaire_version": "1.1"},
        "answers": [{"ref": "C1", "question": "Q?", "answer": "a",
                     "targets": ["01_Foundation.Settings"], "default_if_silent": ""}],
        "appendices": {}}), encoding="utf-8")
    assert lzctl("assess", str(dump), "--customer", "t",
                 "--workspace", str(tmp_path)).returncode == 0
    spec = tmp_path / "specs" / "lz.spec.t.json"
    assert lzctl("gap", "add", "--spec", str(spec),
                 "--field", "08_DNS.ResolverRules[fwd].TargetIPs",
                 "--question", "missing fact").returncode == 0

    r = status("--workspace", str(tmp_path))
    assert "> design" in r.stdout
    assert "1 OPEN decision without a resolution" in flat(r.stdout)
    assert "the app's Decisions & gaps view" in r.stdout   # INPUT names where to fix it


# ── back: re-entry, never undo ─────────────────────────────────────────────

def test_back_journals_and_names_what_it_invalidates(ws):
    built(ws)
    r = lzctl("back", "design", "--reason", "supernet moved", "--by", "tester",
              "--workspace", str(ws))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "invalidates (must be redone in order): build, verify_pre" in r.stdout
    assert "nothing was deleted" in r.stdout

    entry = json.loads((ws / "specs" / "lz.spec.demo.journal.jsonl")
                       .read_text(encoding="utf-8").splitlines()[0])
    assert entry["phase"] == "design" and entry["by"] == "tester"
    assert entry["reason"] == "supernet moved"
    assert entry["invalidates"][0] == "build"

    # ...and the journal surfaces in the next status report
    out = status("--workspace", str(ws)).stdout
    assert "journal" in out and "tester" in out
    assert "supernet moved" in flat(out)


def test_back_deletes_nothing(ws):
    built(ws)
    before = sorted(p.name for p in (ws / "envs-demo").iterdir())
    lzctl("back", "design", "--reason", "r", "--workspace", str(ws))
    assert sorted(p.name for p in (ws / "envs-demo").iterdir()) == before


def test_back_warns_when_the_estate_is_applied(ws):
    built(ws)
    (ws / "envs-demo" / "lzctl-logs").mkdir(exist_ok=True)
    (ws / "envs-demo" / "lzctl-logs" / "20260101-000000-apply.log").write_text("x", encoding="utf-8")
    r = lzctl("back", "design", "--reason", "r", "--workspace", str(ws))
    assert "already APPLIED" in r.stdout
    assert "plans a DESTROY" in r.stdout


def test_back_refuses_a_forward_move(ws):
    r = lzctl("back", "deploy", "--reason", "r", "--workspace", str(ws))
    assert r.returncode == 1
    assert "nothing to re-enter" in r.stderr


def test_back_rejects_an_unknown_phase(ws):
    r = lzctl("back", "provisioning", "--reason", "r", "--workspace", str(ws))
    assert r.returncode == 2 and "unknown phase" in r.stderr


# ── the JSON contract the agent renders from ──────────────────────────────

def test_json_carries_everything_a_render_needs(ws):
    built(ws)
    doc, r = status_json("--workspace", str(ws))
    assert r.returncode == 0
    assert doc["customer"] == "demo" and doc["total"] == 7
    assert doc["complete"] == 3 and doc["current"] == "verify_pre"
    assert doc["env_count"] == 12
    assert [p["name"] for p in doc["phases"]] == list(PHASE_NAMES)
    # every phase carries the fields the skill's rendering references
    for p in doc["phases"]:
        for field in ("state", "status", "current", "gist", "artifacts",
                      "blockers", "notes", "needs", "next", "runner",
                      "cloud_access", "undo"):
            assert field in p, f"{p['name']} is missing {field}"
    assert sum(1 for p in doc["phases"] if p["current"]) == 1


def test_json_states_use_plain_words(ws):
    built(ws)
    doc, _ = status_json("--workspace", str(ws))
    words = {p["status"] for p in doc["phases"]}
    assert words <= {"complete", "recheck", "blocked", "pending"}, words


def test_json_reports_recheck_and_blocked(ws):
    built(ws)
    time.sleep(0.01)
    (ws / "specs" / "lz.spec.demo.json").touch()
    (ws / "envs-demo" / "lzctl-logs").mkdir(exist_ok=True)
    (ws / "envs-demo" / "lzctl-logs" / "20260101-000000-apply.log").write_text("x", encoding="utf-8")
    (ws / "envs-demo" / ".lzctl.lock").write_text('{"pid": 1}', encoding="utf-8")

    doc, r = status_json("--workspace", str(ws))
    assert r.returncode == 3, "blocked outranks recheck in the exit code"
    assert phase(doc, "build")["status"] == "recheck"
    assert phase(doc, "deploy")["status"] == "blocked"
    assert any("Do NOT re-apply blindly" in b for b in phase(doc, "deploy")["blockers"])
    assert any("Timestamp hint only" in h for h in doc["hints"])


def test_json_next_is_a_list_of_runnable_commands(ws):
    doc, _ = status_json("--workspace", str(ws))
    nxt = phase(doc, "build")["next"]
    assert nxt and all(c.startswith("lzctl ") for c in nxt), nxt
    assert phase(doc, "deploy")["undo"], "undo must never be empty - it gates how an apply is read"


def test_journal_rides_along_in_the_json(ws):
    built(ws)
    lzctl("back", "design", "--reason", "supernet moved", "--by", "tester",
          "--workspace", str(ws))
    doc, _ = status_json("--workspace", str(ws))
    assert len(doc["journal"]) == 1
    assert doc["journal"][0]["reason"] == "supernet moved"


def test_text_form_stays_plain(ws):
    """No colour, no box glyphs: the readable report is the agent's, not this."""
    built(ws)
    out = status("--workspace", str(ws), "--verbose").stdout
    assert "[" not in out
    assert not set(out) & set("━─═█░✓✗≈○▸←"), "the CLI must not paint a terminal UI"
    assert "(s)" not in out
