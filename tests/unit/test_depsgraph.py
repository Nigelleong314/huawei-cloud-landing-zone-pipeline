"""deps graph: an env's own backend key is never a consumed dependency.

The backend block lives inline in providers.tf. A dir renumbered with its
state left in place (08-network-dns keeps key envs/07-dns) used to read as
consuming '07-dns' - an unknown env - and failed build and regen-diff.
Consumers of that key must map to the env that owns it.
"""

from pathlib import Path

from lz_pipeline import depsgraph

_PROVIDERS = '''terraform {
  backend "s3" {
    bucket = "state-bucket"
    key    = "envs/%s/terraform.tfstate"
    endpoints = {
      s3 = "https://obs.example"
    }
  }
}
'''
_REMOTE = '''data "terraform_remote_state" "dep" {
  backend = "s3"
  config = {
    key = "envs/%s/terraform.tfstate"
  }
}
'''


def _env(envs: Path, name: str, key: str, consumes: str = ""):
    d = envs / name
    d.mkdir(parents=True)
    (d / "providers.tf").write_text(_PROVIDERS % key, encoding="utf-8")
    if consumes:
        (d / "main.tf").write_text(_REMOTE % consumes, encoding="utf-8")


def test_renamed_state_key_maps_to_its_env(tmp_path):
    _env(tmp_path, "05-network", "05-network")
    _env(tmp_path, "08-network-dns", "07-dns", consumes="05-network")
    _env(tmp_path, "09-network-cfw", "09-network-cfw", consumes="07-dns")

    graph = depsgraph.scan(tmp_path)

    assert graph["08-network-dns"]["consumes"] == ["05-network"]
    assert graph["09-network-cfw"]["consumes"] == ["08-network-dns"]
    assert depsgraph.check(graph) == []
