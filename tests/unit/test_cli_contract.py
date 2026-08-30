"""Every documented command shape must work exactly as written.

This is the drift guard between docs and CLI: the shapes below mirror the
README quickstart and docs/workflow.md. A change that breaks one of these
breaks the documentation, not just the code.
"""

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "pipeline/lz_pipeline/fixtures/example.spec.json"


def lzctl(*args, cwd=None):
    return subprocess.run([sys.executable, "-X", "utf8", "-m", "lz_pipeline.lzctl", *args],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", cwd=str(cwd or REPO),
                          stdin=subprocess.DEVNULL)


ALL_VERBS = ["preflight", "order", "plan", "apply", "drift", "state-backup",
             "adopt", "who-changed", "triage", "docs", "intake", "assess",
             "verify", "report", "build", "validate", "spec-validate",
             "check", "export"]


def test_every_verb_is_registered():
    r = lzctl("--help")
    assert r.returncode == 0
    for verb in ALL_VERBS:
        assert verb in r.stdout, f"{verb} missing from lzctl --help"


def test_documented_validate_shape():
    r = lzctl("validate", str(FIXTURE))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "0 error(s)" in r.stdout


def test_documented_build_shape(tmp_path):
    """The README quickstart's exact flag order: --ir, --envs-dir, --scaffold-dir."""
    r = lzctl("build", "--ir", str(FIXTURE),
              "--envs-dir", str(tmp_path / "envs"),
              "--scaffold-dir", str(REPO / "terraform" / "scaffold"))
    assert r.returncode == 0, r.stdout[-500:] + r.stderr[-300:]
    assert (tmp_path / "envs" / "05-network" / "terraform.tfvars.json").exists()


def test_build_relative_paths_resolve_from_cwd(tmp_path):
    """Delegated commands must honor the caller's cwd for relative paths."""
    (tmp_path / "work").mkdir()
    r = lzctl("build", "--ir", str(FIXTURE), "--envs-dir", "myenvs",
              "--scaffold-dir", str(REPO / "terraform" / "scaffold"),
              cwd=tmp_path / "work")
    assert r.returncode == 0, r.stdout[-500:]
    assert (tmp_path / "work" / "myenvs" / "00-bootstrap").exists()


def test_export_delegate_reaches_exporter():
    r = lzctl("export", "--help")
    # argparse --help exits 0 from the delegated module
    assert r.returncode == 0 and "--profile" in r.stdout, r.stdout + r.stderr


@pytest.mark.parametrize("verb", ["plan", "apply", "verify", "report"])
def test_operational_verbs_reject_missing_envs_dir(verb):
    r = lzctl(verb)
    assert r.returncode == 2, f"{verb} should exit 2 without --envs-dir"
