"""An envs tree remembers its LZ_MODULE_SOURCE_ROOT.

Every generated module `source` embeds the root. A tree built under an
override and rebuilt without it had every source silently rewritten to the
default. The build now records the root in <envs>/.lz-module-source-root,
reuses it when the variable is unset, and refuses a different one.
"""

import os
import subprocess
import sys
from pathlib import Path

from lz_pipeline import export_v2

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "pipeline/lz_pipeline/fixtures/example.spec.json"


def _build(envs: Path, root=None):
    env = {k: v for k, v in os.environ.items() if k != "LZ_MODULE_SOURCE_ROOT"}
    if root:
        env["LZ_MODULE_SOURCE_ROOT"] = root
    return subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "lz_pipeline", "build", "--ir", str(FIXTURE),
         "--envs-dir", str(envs), "--scaffold-dir", str(REPO / "terraform/scaffold"),
         "--only", "00,01,05"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env, cwd=str(REPO), stdin=subprocess.DEVNULL)


def _sources(envs: Path) -> str:
    return (envs / "05-network" / "spokes.generated.tf").read_text(encoding="utf-8")


def test_recorded_root_is_reused_and_a_different_one_refused(tmp_path):
    envs = tmp_path / "envs"
    r = _build(envs, "../../custom-modules")
    assert r.returncode == 0, r.stdout[-500:] + r.stderr[-500:]
    assert (envs / ".lz-module-source-root").read_text(encoding="utf-8") == "../../custom-modules\n"
    assert '"../../custom-modules/network"' in _sources(envs)

    r = _build(envs)                       # variable unset: the tree's root is used
    assert r.returncode == 0, r.stdout[-500:] + r.stderr[-500:]
    assert '"../../custom-modules/network"' in _sources(envs)

    r = _build(envs, "../../modules")      # a different root is refused
    assert r.returncode != 0
    assert "module source root mismatch" in r.stderr
    assert '"../../custom-modules/network"' in _sources(envs)


def test_root_marker_never_ships():
    assert ".lz-module-source-root" in export_v2.EXCLUDE_NAMES


def test_export_rewrites_the_recorded_root(tmp_path, monkeypatch):
    from lz_pipeline import export_v2
    monkeypatch.delenv("LZ_MODULE_SOURCE_ROOT", raising=False)
    (tmp_path / ".lz-module-source-root").write_text("../../../lib/modules-v2\n", encoding="utf-8")
    assert export_v2.path_rewrite(tmp_path) == ('"../../../lib/modules-v2/', '"../../modules/')
