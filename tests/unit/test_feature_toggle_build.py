"""A disabled feature is absent from the BUILT tree, not only from the export.

SecMaster used to be stripped only by export_v2 (profile features.secmaster),
so the live tree kept planning a SecMaster workspace the shipped artifact did
not have. 07_Security.Settings.enable_secmaster = FALSE now applies the same
strip at build time; export's strip is a no-op on such a tree.
"""

import json
from pathlib import Path

from lz_pipeline import model
from lz_pipeline.core.cli import build_from_spec
from lz_pipeline.core.features import secmaster_enabled, strip_secmaster

REPO = Path(__file__).resolve().parents[2]
SCAFFOLD = REPO / "terraform" / "scaffold"
SPEC = REPO / "pipeline" / "lz_pipeline" / "fixtures" / "example.spec.json"


def _build(tmp_path, enabled):
    spec = model.load(SPEC)["sheets"]
    if enabled is not None:
        spec["07_Security"]["Settings"]["enable_secmaster"] = enabled
    envs = tmp_path / "envs"
    build_from_spec(spec, envs, SCAFFOLD, ["07-security"])
    return envs / "07-security"


def _snapshot(env):
    return {p.name: p.read_bytes() for p in env.iterdir() if p.is_file()}


def test_flag_defaults_on():
    assert secmaster_enabled({})
    assert secmaster_enabled({"07_Security": {"Settings": {"enable_secmaster": None}}})
    assert not secmaster_enabled({"07_Security": {"Settings": {"enable_secmaster": "FALSE"}}})


def test_enabled_build_keeps_secmaster(tmp_path):
    env = _build(tmp_path, None)
    assert 'module "security"' in (env / "main.tf").read_text(encoding="utf-8")


def test_disabled_build_strips_secmaster_and_export_strip_is_idempotent(tmp_path):
    env = _build(tmp_path, False)
    main = (env / "main.tf").read_text(encoding="utf-8")
    assert 'module "security"' not in main
    assert '"observability"' not in main
    assert 'module "edge_protection"' in main
    assert '"lz_security"' not in (env / "providers.tf").read_text(encoding="utf-8")
    assert 'variable "enable_secmaster"' not in (env / "variables.tf").read_text(encoding="utf-8")
    tfvars = json.loads((env / "terraform.tfvars.json").read_text(encoding="utf-8"))
    assert not {"security_account", "secmaster_workspace_name",
                "observability_state_bucket"} & set(tfvars)
    assert "hub_account" in tfvars

    before = _snapshot(env)
    strip_secmaster(env)          # what export does with features.secmaster=false
    assert _snapshot(env) == before
