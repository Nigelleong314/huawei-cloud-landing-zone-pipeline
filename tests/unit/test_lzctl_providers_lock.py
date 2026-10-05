"""lzctl providers-lock: lock both platforms, flag envs on different versions.

An estate drifted to three huaweicloud versions across envs, and
single-platform lock hashes (what `init -upgrade` leaves) broke a Linux CI
runner. The command locks windows_amd64 + linux_amd64 per env and exits
non-zero when the envs' locked versions disagree.
"""

from lz_pipeline import lzctl

_LOCK = '''provider "registry.terraform.io/huaweicloud/huaweicloud" {
  version     = "%s"
  constraints = "~> 1.87"
  hashes = [
    "h1:abc=",
  ]
}
'''


def _env(envs, name, version):
    d = envs / name
    (d / ".terraform").mkdir(parents=True)
    (d / ".terraform.lock.hcl").write_text(_LOCK % version, encoding="utf-8")


def test_reports_versions_and_fails_on_disagreement(tmp_path, capsys):
    _env(tmp_path, "01-foundation", "1.93.0")
    _env(tmp_path, "05-network", "1.95.0")

    rc = lzctl.main(["providers-lock", "--envs-dir", str(tmp_path), "--all", "--dry-run"])
    out = capsys.readouterr().out

    assert rc == 2
    assert "-platform=windows_amd64 -platform=linux_amd64" in out
    assert "1.93.0" in out and "1.95.0" in out and "DISAGREE" in out


def test_agreeing_envs_pass(tmp_path, capsys):
    _env(tmp_path, "01-foundation", "1.95.0")
    _env(tmp_path, "05-network", "1.95.0")

    assert lzctl.main(["providers-lock", "--envs-dir", str(tmp_path), "--all",
                       "--dry-run"]) == 0
    assert "LOCKED (1.95.0" in capsys.readouterr().out
