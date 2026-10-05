"""lzctl plan fails when terraform's exit code contradicts its plan summary.

-detailed-exitcode says 0 = no changes, 2 = changes. If the summary printed
in the same run says the opposite, one of the two is wrong, so the env fails
instead of either being trusted.
"""

import subprocess

import pytest

from lz_pipeline import lzctl

ANSI_PLAN = "\x1b[1mPlan:\x1b[0m 1 to add, 0 to change, 0 to destroy.\n"
NO_CHANGES = "\x1b[32m\x1b[1mNo changes.\x1b[0m Your infrastructure matches the configuration.\n"


def _plan(tmp_path, monkeypatch, rc, output):
    (tmp_path / "01-foundation" / ".terraform").mkdir(parents=True)
    monkeypatch.setattr(lzctl, "run_tf", lambda env_dir, args, dry, log=None, **kw:
                        subprocess.CompletedProcess(args, rc, output, ""))
    monkeypatch.setattr(lzctl, "triage_plan", lambda *a, **kw: (rc, None))
    return lzctl.main(["plan", "--envs-dir", str(tmp_path), "--all"])


@pytest.mark.parametrize("rc,output", [
    (0, ANSI_PLAN),
    (0, "Changes to Outputs:\n  + x = 1\n"),
    (2, NO_CHANGES),
])
def test_mismatch_fails(tmp_path, monkeypatch, capsys, rc, output):
    assert _plan(tmp_path, monkeypatch, rc, output) == 1
    assert "trusting neither" in capsys.readouterr().out


@pytest.mark.parametrize("rc,output", [
    (0, NO_CHANGES),
    (2, ANSI_PLAN),
    (2, "Plan: 1 to import, 0 to add, 0 to change, 0 to destroy.\n"),
    (2, "Changes to Outputs:\n  + x = 1\n"),
])
def test_agreement_passes(tmp_path, monkeypatch, capsys, rc, output):
    assert _plan(tmp_path, monkeypatch, rc, output) == rc
    assert "trusting neither" not in capsys.readouterr().out


def test_warns_while_apply_lock_present(tmp_path, monkeypatch, capsys):
    (tmp_path / ".lzctl.lock").write_text("{}", encoding="utf-8")
    _plan(tmp_path, monkeypatch, 0, NO_CHANGES)
    assert "WARNING" in capsys.readouterr().out
