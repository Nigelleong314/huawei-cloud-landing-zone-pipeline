"""check export-smoke: every env in an artifact zip inits offline and validates.

Each env gets its own fresh TF_DATA_DIR (a stale .terraform with backend
state makes even -backend=false read backend credentials), credentials never
reach terraform, and one failing env fails the check with a verdict per env.
"""

import subprocess
import zipfile

from lz_spec import verify_pipeline as vp


def _zip(tmp_path):
    z = tmp_path / "artifact.zip"
    with zipfile.ZipFile(z, "w") as f:
        for env in ("01-foundation", "05-network"):
            f.writestr(f"acme/terraform/envs/{env}/main.tf", "# --- Main ---\n")
        f.writestr("acme/terraform/envs/deps.json", "{}")
        f.writestr("acme/terraform/modules/network/main.tf", "# --- Network ---\n")
    return z


def test_offline_init_and_validate_per_env(tmp_path, monkeypatch, capsys):
    calls = []

    def fake_run(cmd, cwd, env, **kw):
        calls.append((cmd, cwd, env))
        bad = cmd[1] == "validate" and cwd.endswith("05-network")
        return subprocess.CompletedProcess(cmd, 1 if bad else 0, "Error: boom\n", "")

    monkeypatch.setattr(vp.shutil, "which", lambda _: "terraform")
    monkeypatch.setattr(vp.subprocess, "run", fake_run)
    monkeypatch.setenv("HW_SECRET_KEY", "x")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "x")

    ok = vp.check_export_smoke(_zip(tmp_path), plugin_dir=str(tmp_path / "plugins"))
    out = capsys.readouterr().out

    assert ok is False
    assert "PASS 01-foundation" in out and "FAIL 05-network: validate" in out
    assert "Error: boom" in out
    inits = [c for c in calls if c[0][1] == "init"]
    assert len(inits) == 2
    for cmd, cwd, env in inits:
        assert "-backend=false" in cmd and "-input=false" in cmd
        assert any(a.startswith("-plugin-dir=") for a in cmd)
    data_dirs = {env["TF_DATA_DIR"] for _, _, env in calls}
    assert len(data_dirs) == 2
    assert all(not d.startswith(cwd) for _, cwd, env in calls for d in [env["TF_DATA_DIR"]])
    assert not any(k in env for _, _, env in calls for k in vp.CREDENTIAL_VARS)
    assert not any("plan" in cmd for cmd, _, _ in calls)
