"""Env output: tfvars/secrets/backend writers."""

import json
import shutil
from pathlib import Path


def write_env(env_dir: Path, tfvars: dict, state_bucket: str, ak: str, sk: str, region: str, env_name: str):
    env_dir.mkdir(parents=True, exist_ok=True)

    tfvars_path = env_dir / "terraform.tfvars.json"
    _backup_if_exists(tfvars_path)
    tfvars_path.write_text(json.dumps(tfvars, indent=2, sort_keys=False), encoding="utf-8", newline="\n")

    if ak and sk:
        sec = {"master_access_key": ak, "master_secret_key": sk}
        sec_path = env_dir / "secrets.auto.tfvars.json"
        # never .bak a secrets file: a rotation must not leave the OLD key
        # lying next to the new one (and clean up any .bak from older builds)
        sec_path.with_suffix(sec_path.suffix + ".bak").unlink(missing_ok=True)
        sec_path.write_text(json.dumps(sec, indent=2), encoding="utf-8", newline="\n")
    # creds unset: any existing secrets file is left as-is ON PURPOSE - a
    # rebuild without exported env vars must not break a working deployment

    if env_name != "00-bootstrap" and state_bucket:
        backend_path = env_dir / "backend.hcl"
        _backup_if_exists(backend_path)
        backend_path.write_text(_render_backend_hcl(state_bucket, region), encoding="utf-8", newline="\n")


def _render_backend_hcl(bucket: str, region: str) -> str:
    # f-string interpolation is safe here: bucket/region are schema-constrained
    # identifiers (the one non-json.dumps surface in the generated tree)
    return (
        f'bucket = "{bucket}"\n'
        f'region = "{region}"\n'
        '\n'
        'endpoints = {\n'
        f'  s3 = "https://obs.{region}.myhuaweicloud.com"\n'
        '}\n'
    )


def _backup_if_exists(path: Path):
    if path.exists():
        shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
