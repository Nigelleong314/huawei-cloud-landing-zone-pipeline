"""The pre-commit gate blocks staged state, plans and credentials by content.

Stages a mix of offending and clean files in a throwaway repository and runs
the hook the way git does (from the repo root, reading the index). The state
file carries a UTF-8 BOM and an innocent name - the shape that once slipped
past a filename/plain-JSON check. Fake key material is assembled at runtime
so this file never matches its own patterns.
"""

import io
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

PIPELINE = Path(__file__).resolve().parents[2] / "pipeline"


def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True,
                   stdin=subprocess.DEVNULL)


def _hook(repo):
    env = dict(os.environ, PYTHONPATH=str(PIPELINE))
    return subprocess.run([sys.executable, "-m", "lz_pipeline.tools.precommit_secrets"],
                          cwd=repo, env=env, capture_output=True, text=True,
                          stdin=subprocess.DEVNULL)


def test_hook_blocks_state_plans_and_keys_but_not_clean_files(tmp_path):
    repo = tmp_path / "envs"
    repo.mkdir()
    _git(repo, "init", "-q")
    ak = "AKTEST" + "0123456789ABCD"
    sk = "Ab3" * 13 + "Z"
    state = {"version": 4, "terraform_version": "1.9.8", "serial": 7,
             "lineage": "0c1d", "resources": []}
    plan_zip = io.BytesIO()
    with zipfile.ZipFile(plan_zip, "w") as z:
        z.writestr("tfplan", b"plan")
    files = {
        "05-network/notes.json": b"\xef\xbb\xbf" + json.dumps(state).encode(),
        "05-network/review.json": json.dumps({"format_version": "1.2",
                                              "resource_changes": []}).encode(),
        "05-network/saved": plan_zip.getvalue(),
        "05-network/creds.txt": f"key {ak}\nsecret {sk}\n".encode(),
        "05-network/override.tf": f'provider "huaweicloud" {{\n  secret_key = "{sk}"\n}}\n'.encode(),
        "05-network/secrets.auto.tfvars.json": b"{}",
        "05-network/main.tf": b'provider "huaweicloud" {\n  access_key = var.master_access_key\n}\n',
        "05-network/terraform.tfvars.json": b'{"master_access_key": "", "region": "ap-southeast-3"}',
    }
    for rel, data in files.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_bytes(data)
    _git(repo, "add", "-A")

    r = _hook(repo)
    assert r.returncode == 1, r.stderr
    blocked = {line.split(":")[0].strip() for line in r.stderr.splitlines()
               if line.startswith("  ")}
    assert blocked == {"05-network/notes.json", "05-network/review.json",
                       "05-network/saved", "05-network/creds.txt",
                       "05-network/override.tf",
                       "05-network/secrets.auto.tfvars.json"}, r.stderr
    assert ak not in r.stderr and sk not in r.stderr, "the hook echoed a secret"

    # the index is what counts: unstage the offenders and the commit is clean
    _git(repo, "rm", "-q", "--cached", *[p for p in blocked])
    r = _hook(repo)
    assert r.returncode == 0, r.stderr
