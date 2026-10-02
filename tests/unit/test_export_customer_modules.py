"""A customer's own modules ship in the artifact's modules/ beside the library.

An envs tree may carry modules that belong to that customer only (Frasers'
workload VM, KMS, CBR and OBS-backup modules) in <envs>/modules; the product
library stays landing-zone only. The export must move them to modules/, point
the env sources at the new place, leave library sources as they were, and
refuse a customer module that would shadow a library one.
"""

import pytest

from lz_pipeline import export_v2


def _tree(tmp_path):
    envs = tmp_path / "envs"
    (envs / "12-workloads").mkdir(parents=True)
    (envs / "12-workloads" / "vms.tf").write_text(
        'module "vm" {\n  source = "../modules/workload-vm"\n}\n'
        'module "net" {\n  source = "../../../huaweicloud-agentic-tools/modules-v2/network"\n}\n',
        encoding="utf-8")
    (envs / "modules" / "workload-vm").mkdir(parents=True)
    (envs / "modules" / "workload-vm" / "main.tf").write_text("# --- VM ---\n", encoding="utf-8")
    library = tmp_path / "library"
    (library / "network").mkdir(parents=True)
    (library / "network" / "main.tf").write_text("# --- Network ---\n", encoding="utf-8")
    return envs, library


def test_env_copy_skips_own_modules_and_repoints_sources(tmp_path):
    envs, _ = _tree(tmp_path)
    dst = tmp_path / "out" / "envs"
    export_v2.copy_tree(envs, dst, rewrite=True, skip_top=("modules",),
                        extra_rewrites=(export_v2.OWN_MODULES_REWRITE,))

    assert not (dst / "modules").exists()
    vms = (dst / "12-workloads" / "vms.tf").read_text(encoding="utf-8")
    assert 'source = "../../modules/workload-vm"' in vms
    assert 'source = "../../modules/network"' in vms
    assert "../../../modules" not in vms


def test_customer_modules_land_beside_the_library(tmp_path):
    envs, library = _tree(tmp_path)
    dst = tmp_path / "out" / "modules"
    export_v2.copy_tree(library, dst, rewrite=True)
    n = export_v2.copy_customer_modules(envs, dst, library)

    assert n == 1
    assert sorted(p.name for p in dst.iterdir()) == ["network", "workload-vm"]


def test_customer_module_may_not_shadow_a_library_module(tmp_path):
    envs, library = _tree(tmp_path)
    (envs / "modules" / "network").mkdir()
    with pytest.raises(SystemExit, match="network"):
        export_v2.copy_customer_modules(envs, tmp_path / "out" / "modules", library)


def test_tree_without_own_modules_is_unchanged(tmp_path):
    envs, library = _tree(tmp_path)
    for f in (envs / "modules").rglob("*"):
        if f.is_file():
            f.unlink()
    (envs / "modules" / "workload-vm").rmdir()
    (envs / "modules").rmdir()
    assert export_v2.copy_customer_modules(envs, tmp_path / "out" / "modules", library) == 0
