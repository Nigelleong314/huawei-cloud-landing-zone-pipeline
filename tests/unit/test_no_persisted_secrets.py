"""No fixture-declared secret may survive in any persisted artifact.

The eval runner redacts declared secrets before writing transcripts; this
test is the deterministic backstop the review asked for - it fails if a
declared secret ever appears under tests/evaluation/results/ (or anywhere
else in the evaluation tree).
"""

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EVAL = REPO / "tests" / "evaluation"


def declared_secrets():
    doc = json.loads((EVAL / "fixtures" / "fixtures.json").read_text(encoding="utf-8"))
    out = []
    for fx in doc["fixtures"]:
        out.extend(fx.get("secrets", []))
    return out


def test_fixture_secrets_are_declared():
    # the canary fixture must keep declaring its secret, or redaction and
    # this scan both silently stop covering it
    assert declared_secrets(), "secrets-01 must declare its secret values"


def test_no_declared_secret_persisted():
    secrets = declared_secrets()
    hits = []
    for p in EVAL.rglob("*"):
        if not p.is_file() or p.suffix not in (".json", ".md", ".txt", ".log"):
            continue
        if p.name == "fixtures.json":
            continue  # the declaration itself
        body = p.read_text(encoding="utf-8", errors="ignore")
        for s in secrets:
            if s in body:
                hits.append(f"{p.relative_to(REPO)}: {s[:6]}...")
    assert not hits, f"declared secrets persisted: {hits}"
