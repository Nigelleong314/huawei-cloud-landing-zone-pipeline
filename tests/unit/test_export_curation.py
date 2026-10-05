"""Export curation: what a profile ships, and what never ships.

- skip_envs leaves env dirs out (and out of deps.json); ship_markdown=false
  drops .md under modules/ and envs/; library modules no shipped env uses
  are pruned, and a module source outside the artifact refuses the export.
- No *.tfstate* ships, the 00-bootstrap local state included (it is handed
  over out of band).
- Relative profile paths resolve against the profile file's directory.
"""

import json
from pathlib import Path

import pytest

from lz_pipeline import export_v2


def _write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".tf":
        text = "# --- Test ---\n" + text      # the comment convention's header
    path.write_text(text, encoding="utf-8")


def _workspace(tmp_path):
    envs = tmp_path / "ws" / "envs"
    _write(envs / "00-bootstrap" / "main.tf", "locals {}\n")
    _write(envs / "00-bootstrap" / "terraform.tfstate", "{}")
    _write(envs / "00-bootstrap" / "terraform.tfstate.backup", "{}")
    _write(envs / "01-core" / "main.tf", 'module "a" {\n  source = "../../modules/a"\n}\n')
    _write(envs / "01-core" / "README.md", "notes\n")
    _write(envs / "02-extra" / "main.tf", 'module "c" {\n  source = "../../modules/c"\n}\n')
    _write(envs / ".gitignore", "*.tfstate\n")
    _write(envs / "deps.json", json.dumps({
        "apply_order": ["00-bootstrap", "01-core", "02-extra"],
        "envs": {"00-bootstrap": {"consumes": []}, "01-core": {"consumes": []},
                 "02-extra": {"consumes": ["01-core"]}}}))
    lib = tmp_path / "library"
    _write(lib / "a" / "main.tf", 'module "b" {\n  source = "../b"\n}\n')
    _write(lib / "a" / "README.md", "a\n")
    _write(lib / "b" / "main.tf", "locals {}\n")
    _write(lib / "c" / "main.tf", "locals {}\n")
    _write(lib / "unused" / "main.tf", "locals {}\n")
    return envs, lib


def test_state_never_ships_not_even_bootstrap():
    for name in ("terraform.tfstate", "terraform.tfstate.backup", "x-01.tfstate.json"):
        assert export_v2.excluded(Path("envs/00-bootstrap") / name, export_v2.EXCLUDE_NAMES)


def test_profile_curation_end_to_end(tmp_path, monkeypatch):
    envs, lib = _workspace(tmp_path)
    monkeypatch.setattr(export_v2, "MODULES", lib)
    prof = tmp_path / "ws" / "profiles" / "acme.json"
    _write(prof, json.dumps({"customer": "acme", "envs_dir": "../envs",
                             "skip_envs": ["02-extra"], "ship_markdown": False}))
    profile = export_v2.resolve_profile_paths(json.loads(prof.read_text(encoding="utf-8")),
                                              prof.parent)
    target = tmp_path / "artifact"
    assert export_v2.export(profile, target, "1.0.0", False, tmp_path / "rel",
                            no_workbook=True) == 0

    assert sorted(p.name for p in (target / "envs").iterdir() if p.is_dir()) \
        == ["00-bootstrap", "01-core"]
    assert sorted(p.name for p in (target / "modules").iterdir() if p.is_dir()) == ["a", "b"]
    assert not list(target.rglob("*.tfstate*"))
    assert not list((target / "envs").rglob("*.md"))
    assert not list((target / "modules").rglob("*.md"))
    deps = json.loads((target / "envs" / "deps.json").read_text(encoding="utf-8"))
    assert deps["apply_order"] == ["00-bootstrap", "01-core"]
    assert "02-extra" not in deps["envs"]
    assert (target / ".gitignore").read_text(encoding="utf-8") == "*.tfstate\n"


def test_unresolved_module_source_refuses(tmp_path):
    _write(tmp_path / "envs" / "01-core" / "main.tf",
           'module "a" {\n  source = "../../../elsewhere/modules/a"\n}\n')
    (tmp_path / "modules" / "a").mkdir(parents=True)
    with pytest.raises(SystemExit, match="elsewhere"):
        export_v2.prune_modules(tmp_path)


def test_relative_profile_paths_follow_the_profile(tmp_path, monkeypatch):
    (tmp_path / "ws" / "envs").mkdir(parents=True)
    (tmp_path / "cwd" / "legacy-envs").mkdir(parents=True)
    monkeypatch.setattr(export_v2, "ROOT", tmp_path / "cwd")
    prof_dir = tmp_path / "ws" / "profiles"
    out = export_v2.resolve_profile_paths(
        {"envs_dir": "../envs", "docs_dir": None, "ir": str(tmp_path / "abs.json")}, prof_dir)
    assert Path(out["envs_dir"]) == (tmp_path / "ws" / "envs").resolve()
    assert out["ir"] == str(tmp_path / "abs.json")
    assert out["docs_dir"] is None
    # a path that exists only relative to the invoking directory still works
    legacy = export_v2.resolve_profile_paths({"envs_dir": "legacy-envs"}, prof_dir)
    assert Path(legacy["envs_dir"]) == (tmp_path / "cwd" / "legacy-envs").resolve()
