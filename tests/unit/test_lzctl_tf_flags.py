"""lzctl passes --parallelism and drift --no-refresh through to terraform.

A large CFW plan failed with WSAEACCES unless -parallelism was lowered, and a
config-vs-state drift check took 7 s with -refresh=false against ~32 min with
a full refresh. Both must reach the terraform command line.
"""

import subprocess

from lz_pipeline import lzctl


def _envs(tmp_path):
    env = tmp_path / "01-foundation"
    (env / ".terraform").mkdir(parents=True)
    return tmp_path


def test_plan_passes_parallelism(tmp_path, capsys):
    envs = _envs(tmp_path)
    rc = lzctl.main(["plan", "--envs-dir", str(envs), "--all", "--dry-run",
                     "--parallelism", "2"])
    assert rc == 0
    plan_line = next(l for l in capsys.readouterr().out.splitlines()
                     if "terraform plan" in l)
    assert plan_line.endswith("-parallelism=2"), plan_line


def test_drift_no_refresh_and_parallelism(tmp_path, monkeypatch):
    envs = _envs(tmp_path)
    calls = []

    def fake_run_tf(env_dir, args, dry, log=None, **kw):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(lzctl, "run_tf", fake_run_tf)
    rc = lzctl.main(["drift", "--envs-dir", str(envs), "--no-refresh",
                     "--parallelism", "2"])
    assert rc == 0
    assert calls and calls[0][0] == "plan"
    assert "-refresh=false" in calls[0] and "-parallelism=2" in calls[0]

    calls.clear()
    lzctl.main(["drift", "--envs-dir", str(envs)])
    assert not any(a.startswith(("-refresh", "-parallelism")) for a in calls[0])
