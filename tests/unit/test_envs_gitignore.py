"""A built envs tree carries one root .gitignore, and lock files stay tracked.

Per-env scaffold ignores used to list .terraform.lock.hcl, so provider
checksums never reached the customer's repository. The build now writes a
single root .gitignore (state, plans, logs and caches in every spelling) and
leaves an existing one alone.
"""

import fnmatch
from pathlib import Path

from lz_pipeline import model
from lz_pipeline.core.cli import build_from_spec

REPO = Path(__file__).resolve().parents[2]
SCAFFOLD = REPO / "terraform" / "scaffold"
SPEC = REPO / "pipeline" / "lz_pipeline" / "fixtures" / "example.spec.json"


def _patterns(text):
    return [l.strip() for l in text.splitlines() if l.strip() and not l.startswith("#")]


def _ignored(name, patterns):
    return any(fnmatch.fnmatch(name, p.rstrip("/")) for p in patterns)


def test_scaffold_has_no_per_env_gitignore():
    assert not list(SCAFFOLD.glob("*/.gitignore"))


def test_build_writes_root_gitignore(tmp_path):
    envs = tmp_path / "envs"
    build_from_spec(model.load(SPEC)["sheets"], envs, SCAFFOLD, ["00-bootstrap"])
    assert not (envs / "00-bootstrap" / ".gitignore").exists()
    pats = _patterns((envs / ".gitignore").read_text(encoding="utf-8"))
    for name in ("terraform.tfstate", "terraform.tfstate.backup", "tf.plan", "tfplan.bin",
                 "plan.json", "x.plan.txt", "a.tfplan", "state-11-pre.json",
                 ".terraform", "state-backups", "lzctl-logs", "main.tf.bak",
                 "secrets.auto.tfvars.json"):
        assert _ignored(name, pats), name
    for name in (".terraform.lock.hcl", "terraform.tfvars.json", "main.tf"):
        assert not _ignored(name, pats), name


def test_existing_root_gitignore_is_kept(tmp_path):
    envs = tmp_path / "envs"
    envs.mkdir()
    (envs / ".gitignore").write_text("mine\n", encoding="utf-8")
    build_from_spec(model.load(SPEC)["sheets"], envs, SCAFFOLD, ["00-bootstrap"])
    assert (envs / ".gitignore").read_text(encoding="utf-8") == "mine\n"
