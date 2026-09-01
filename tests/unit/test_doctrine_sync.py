"""Prose copies of machine-readable contracts must not drift.

schemas/phases.json is the canonical phase graph; the eval shared_context,
the skill's Phase contract table, and docs/workflow.md all restate it in
prose. This guard fails when a restatement stops matching the graph.
"""

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def phase_names():
    doc = json.loads((REPO / "schemas" / "phases.json").read_text(encoding="utf-8"))
    return list(doc["phases"].keys())


def test_eval_doctrine_matches_phase_graph():
    fx = json.loads((REPO / "tests/evaluation/fixtures/fixtures.json")
                    .read_text(encoding="utf-8"))
    sc = fx["shared_context"]
    expected = " -> ".join(phase_names())
    assert expected in sc, (
        f"eval shared_context phase doctrine drifted from schemas/phases.json; "
        f"expected the literal sequence: {expected}")


def test_skill_phase_contract_matches_phase_graph():
    skill = (REPO / "skills/huawei-cloud-landing-zone/SKILL.md").read_text(encoding="utf-8")
    for name in phase_names():
        assert re.search(rf"^\| {re.escape(name)} \|", skill, re.M), (
            f"skill Phase contract is missing canonical phase {name!r}")


def test_workflow_doc_matches_phase_graph():
    doc = (REPO / "docs" / "workflow.md").read_text(encoding="utf-8")
    for name in phase_names():
        assert f"**{name}**" in doc, (
            f"docs/workflow.md phase table is missing canonical phase {name!r}")


def test_lzctl_phase_table_matches_phase_graph():
    """`lzctl status` restates the graph as a progress bar; the runner ships
    standalone (no schemas/ beside it), so the table is embedded and this
    guard is the only thing keeping it honest."""
    from lz_pipeline.lzctl import PHASES, PHASE_DOC
    assert list(PHASES) == phase_names(), (
        "lzctl.PHASES drifted from schemas/phases.json")
    assert set(PHASE_DOC) == set(phase_names()), (
        "lzctl.PHASE_DOC is missing or inventing a phase")
    for name, doc in PHASE_DOC.items():
        for field in ("summary", "who", "cloud", "reversible"):
            assert doc.get(field), f"{name}: PHASE_DOC.{field} is empty"


def test_skill_render_doctrine():
    """The render spec is doctrine: the system (rules + strip + default
    report) lives in SKILL.md, the verb goldens in rendering.md — and both
    files obey their own words-only law. `—` and `·` are vocabulary, not
    decoration; everything in `banned` is."""
    skill_dir = REPO / "skills/huawei-cloud-landing-zone"
    skill = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    assert "## Rendering" in skill
    for rule in ("Verdict first", "Exceptions only", "One Next", "Words only"):
        assert rule in skill, f"SKILL.md lost the {rule!r} rule"
    assert "**frasers** · 03-build · 4/7" in skill, "the strip example is the strip spec"
    assert "Needs attention" in skill, "the default report leads with exceptions"
    assert "Everything else gets no strip" in skill, (
        "the strip's scope must stay bounded: repo/tooling work is not an "
        "engagement update, and an unchanged strip repeated is noise")
    assert "Phases are numbered" in skill, "the numbering rule is doctrine"

    rendering = (skill_dir / "rendering.md").read_text(encoding="utf-8")
    for verb in ("PLAN", "APPLY", "VERIFY", "VALIDATE", "DECISIONS", "DOCS"):
        assert f"### {verb} —" in rendering, f"rendering.md lost the {verb} golden"
    assert "| 01-intake |" in rendering, "full-form table rows carry phase numbers"

    banned = set("✓✗≈○▸←→━═█░")
    for name, text in (("SKILL.md", skill), ("rendering.md", rendering)):
        hits = set(text) & banned
        assert not hits, f"{name} breaks its own words-only law: {hits}"


def test_no_skip_rule_is_true_of_the_graph():
    doc = json.loads((REPO / "schemas" / "phases.json").read_text(encoding="utf-8"))
    order = list(doc["phases"].keys())
    for i, (name, ph) in enumerate(doc["phases"].items()):
        for nxt in ph.get("next", []):
            assert order.index(nxt) == i + 1, (
                f"phase graph allows a skip: {name} -> {nxt} (docs promise "
                "no phase may be skipped forward)")


def test_state_keys_match_env_directory_names():
    """Every backend.tf state key must name ITS OWN env directory - a mismatch
    sends state (and state backups, and audit forensics) to the wrong slot."""
    import re
    for tree in ("terraform/scaffold", "terraform/envs-example"):
        for backend in sorted((REPO / tree).glob("*/backend.tf")):
            m = re.search(r'key\s*=\s*"envs/([^/]+)/terraform\.tfstate"',
                          backend.read_text(encoding="utf-8"))
            assert m, f"{backend}: no state key found"
            assert m.group(1) == backend.parent.name, (
                f"{backend}: state key names 'envs/{m.group(1)}/' but the env "
                f"directory is '{backend.parent.name}'")


def test_pipeline_written_filenames_are_ignored_or_retained():
    """Category guard for the drift.tfplan/state-key class of bug: every
    artifact filename the runner/pipeline writes is either gitignored or
    deliberately retained. A new write-site must be added here, forcing the
    author to decide its fate in .gitignore AND the handover exporter."""
    import subprocess
    base = "terraform/envs-example/05-network/"
    IGNORED = ["tf.plan", "drift.tfplan", ".lzctl.lock",
               "secrets.auto.tfvars.json", "errored.tfstate",
               "backend.hcl.bak", "terraform.tfvars.json.bak",
               "terraform.tfstate", "terraform.tfstate.backup",
               "lzctl-logs/x.log", "state-backups/x.tfstate",
               "evidence/x/MANIFEST.txt", "drift-report.md"]
    RETAINED = ["terraform.tfvars.json", "backend.hcl", "backend.tf",
                "providers.generated.tf", "deps.json"]
    for name in IGNORED:
        r = subprocess.run(["git", "check-ignore", "-q", base + name],
                           cwd=REPO, capture_output=True, stdin=subprocess.DEVNULL)
        assert r.returncode == 0, (
            f"{name!r} is written by the pipeline but NOT gitignored")
    for name in RETAINED:
        r = subprocess.run(["git", "check-ignore", "-q", base + name],
                           cwd=REPO, capture_output=True, stdin=subprocess.DEVNULL)
        assert r.returncode == 1, (
            f"{name!r} must be retained (committed) but .gitignore excludes it")
    # the handover exporter must exclude every ignored artifact class
    exporter = (REPO / "pipeline/lz_pipeline/export_v2.py").read_text(encoding="utf-8")
    for token in ('".tfplan"', '"tf.plan"', '".lzctl.lock"',
                  '"secrets.auto.tfvars.json"'):
        assert token in exporter, (
            f"export_v2.py must exclude {token} - a plan/lock/secrets artifact "
            "would ship in the handover")
