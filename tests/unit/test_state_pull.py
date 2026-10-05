"""Doc generators read state only from state-<env>.json; say so when missing.

Pulls saved under any other name read as empty state, and the checklist and
config book silently showed nothing deployed. The reader now warns with the
envs that have no file, and `lzctl state-pull` writes the expected names -
copying 00-bootstrap's local terraform.tfstate, pulling the rest.
"""

import subprocess

from lz_pipeline import lzctl
from lz_pipeline.tools import envtree


def _tree(envs):
    (envs / "00-bootstrap").mkdir(parents=True)
    (envs / "00-bootstrap" / "main.tf").write_text("# --- Bootstrap ---\n", encoding="utf-8")
    (envs / "00-bootstrap" / "terraform.tfstate").write_text('{"serial": 1}', encoding="utf-8")
    (envs / "01-foundation").mkdir()
    (envs / "01-foundation" / "providers.tf").write_text(
        'terraform {\n  backend "s3" {}\n}\n', encoding="utf-8")


def test_missing_states_warn_then_state_pull_fills_them(tmp_path, monkeypatch, capsys):
    envs, states = tmp_path / "envs", tmp_path / "states"
    _tree(envs)
    states.mkdir()
    (states / "01-foundation.tfstate").write_text("{}", encoding="utf-8")  # wrong name

    assert envtree.missing_states(envs, states) == ["00-bootstrap", "01-foundation"]
    assert "00-bootstrap, 01-foundation" in capsys.readouterr().err

    pulls = []

    def fake_run(cmd, cwd=None, **kw):
        pulls.append((cmd, cwd))
        return subprocess.CompletedProcess(cmd, 0, '{"serial": 7}', "")

    monkeypatch.setattr(lzctl.subprocess, "run", fake_run)
    assert lzctl.main(["state-pull", "--envs-dir", str(envs), "--out", str(states)]) == 0

    # only the remote-backend env is pulled; bootstrap's local state is copied
    assert [c for c, _ in pulls] == [["terraform", "state", "pull"]]
    assert pulls[0][1].endswith("01-foundation")
    assert (states / "state-00-bootstrap.json").read_text(encoding="utf-8") == '{"serial": 1}'
    assert (states / "state-01-foundation.json").read_text(encoding="utf-8") == '{"serial": 7}'
    assert envtree.missing_states(envs, states) == []
