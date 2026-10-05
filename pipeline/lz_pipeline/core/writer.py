"""Env output: tfvars writer + backend fill-in."""

import json
import shutil
from pathlib import Path


def write_env(env_dir: Path, tfvars: dict, state_bucket: str, region: str, env_name: str):
    env_dir.mkdir(parents=True, exist_ok=True)

    tfvars_path = env_dir / "terraform.tfvars.json"
    _backup_if_exists(tfvars_path)
    tfvars_path.write_text(json.dumps(tfvars, indent=2, sort_keys=False), encoding="utf-8", newline="\n")

    # Credentials are never written to disk: the provider and the S3 backend
    # both read them from the environment (HW_ACCESS_KEY / HW_SECRET_KEY /
    # HW_SECURITY_TOKEN, AWS_*), which is the only shape a temporary AK/SK
    # can take - a session token has no tfvars home. Any file an older
    # build left behind would now only raise "undeclared variable".
    (env_dir / "secrets.auto.tfvars.json").unlink(missing_ok=True)

    if env_name != "00-bootstrap" and state_bucket:
        _inject_backend(env_dir / "providers.tf", state_bucket, region)
        # a self-contained backend replaces the partial-config pair
        for stale in ("backend.hcl", "backend.hcl.example", "backend.tf"):
            (env_dir / stale).unlink(missing_ok=True)


def write_root_gitignore(envs_dir: Path):
    """One .gitignore for the whole envs tree, written only when absent so a
    user's own rules are never overwritten. Lock files stay tracked."""
    path = envs_dir / ".gitignore"
    if path.exists():
        return
    tpl = Path(__file__).parent / "templates" / "envs.gitignore.tmpl"
    path.write_text(tpl.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")


def _inject_backend(providers: Path, bucket: str, region: str):
    """Fill bucket/region/endpoints into the scaffold's `backend "s3"` block.

    `terraform init` then needs no -backend-config flag, which is one less way
    for a handover recipient to end up on a silent empty state.

    THE KEY IS NEVER WRITTEN HERE. It addresses live state, which an env may
    keep under a key that differs from its current directory name; the
    scaffold owns it as a static value so no rebuild can rewrite it.
    Idempotent: an already-filled block is left alone.
    """
    if not providers.exists():
        return
    text = providers.read_text(encoding="utf-8")
    if 'backend "s3"' not in text or "bucket =" in text:
        return
    # f-string interpolation is safe here: bucket/region are schema-constrained
    # identifiers (the one non-json.dumps surface in the generated tree)
    fill = [f'    bucket = "{bucket}"',
            f'    region = "{region}"',
            '    endpoints = {',
            f'      s3 = "https://obs.{region}.myhuaweicloud.com"',
            '    }']
    out, done = [], False
    for line in text.splitlines():
        out.append(line)
        if not done and line.strip().startswith('backend "s3"'):
            out.extend(fill)
            done = True
    providers.write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")


def _backup_if_exists(path: Path):
    if path.exists():
        shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))


def write_generated(env_dir: Path, files):
    for fname, lines in files:
        path = env_dir / fname
        _backup_if_exists(path)
        path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
