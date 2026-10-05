"""Pre-commit gate for env trees: refuse staged state, plans and credentials.

Scans what is about to be committed - the INDEX, not the working tree - and
exits 1 listing each offending path with the reason. It never prints the
matched value. Detection is by content, not filename, so a renamed or
BOM-prefixed state file is still caught:

- Terraform state: JSON carrying "lineage" plus "serial" or
  "terraform_version" (UTF-8 BOM and UTF-16 tolerated)
- plans: a binary plan (zip holding a tfplan member) or plan JSON carrying
  "planned_values" / "resource_changes"
- Huawei credentials: a 20-character uppercase access key next to a
  40-character secret key, or an access_key / secret_key / security_token
  assignment with a literal value
- any file named secrets.auto.tfvars.json

Usage, from inside the repository (normally as .git/hooks/pre-commit):

    python -m lz_pipeline.tools.precommit_secrets
    python path/to/precommit_secrets.py        # stdlib only; runs standalone
"""

import io
import re
import subprocess
import sys
import zipfile

SECRET_FILES = {"secrets.auto.tfvars.json"}

_STATE = (re.compile(r'"lineage"\s*:'),
          re.compile(r'"(?:serial|terraform_version)"\s*:'))
_PLAN = re.compile(r'"(?:planned_values|resource_changes)"\s*:')
_EDGE = "A-Za-z0-9+/="   # a key embedded in a longer base64 run is not a key
_AK = re.compile(rf"(?<![{_EDGE}])(?=[A-Z0-9]*[A-Z])[A-Z0-9]{{20}}(?![{_EDGE}])")
_SK = re.compile(rf"(?<![{_EDGE}])(?=[A-Za-z0-9]*[a-z])(?=[A-Za-z0-9]*[A-Z])"
                 rf"[A-Za-z0-9]{{40}}(?![{_EDGE}])")
_PAIR_WINDOW = 300
_ASSIGN = re.compile(
    r"(?i)[\w-]*(?:secret_?(?:access_?)?key|access_?key(?:_?id)?|"
    r"security_?token|session_?token)[\w-]*[\"']?\s*[:=]\s*"
    r"(?:\"([^\"\n]*)\"|'([^'\n]*)'|([A-Za-z0-9/+=_-]{16,})(?![\w.(\[]))")
_PLACEHOLDER = re.compile(r"(?i)replace|example|placeholder|changeme|xxxx|^<.*>$")


def _git(*args) -> bytes:
    return subprocess.run(["git", *args], capture_output=True, check=True,
                          stdin=subprocess.DEVNULL).stdout


def staged_paths() -> list:
    out = _git("diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR")
    return [p for p in out.decode("utf-8").split("\0") if p]


def _text(data: bytes):
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16", errors="replace")
    if b"\0" in data:
        return None   # binary
    return data.decode("utf-8-sig", errors="replace")


def _literal_secret(value: str) -> bool:
    return (len(value) >= 8 and not value.startswith("${")
            and not _PLACEHOLDER.search(value)
            and re.search(r"\d", value) is not None)


def classify(path: str, data: bytes):
    """The reason a staged blob must not be committed, or None."""
    if path.rsplit("/", 1)[-1] in SECRET_FILES:
        return "secrets tfvars file"
    if data[:4] == b"PK\x03\x04":
        try:
            names = zipfile.ZipFile(io.BytesIO(data)).namelist()
        except zipfile.BadZipFile:
            names = []
        return "binary Terraform plan" if "tfplan" in names else None
    text = _text(data)
    if text is None:
        return None
    if text.lstrip().startswith("{"):
        if all(rx.search(text) for rx in _STATE):
            return "Terraform state"
        if _PLAN.search(text):
            return "Terraform plan JSON"
    for ak in _AK.finditer(text):
        lo, hi = max(0, ak.start() - _PAIR_WINDOW), ak.end() + _PAIR_WINDOW
        if _SK.search(text, lo, hi):
            return "access key / secret key pair"
    for m in _ASSIGN.finditer(text):
        if _literal_secret(next(g for g in m.groups() if g is not None)):
            return "credential assignment with a literal value"
    return None


def scan() -> list:
    hits = []
    for path in staged_paths():
        reason = classify(path, _git("show", f":{path}"))
        if reason:
            hits.append((path, reason))
    return hits


def main() -> int:
    try:
        hits = scan()
    except (OSError, subprocess.CalledProcessError) as e:
        print(f"precommit_secrets: cannot read the index ({e})", file=sys.stderr)
        return 1
    if not hits:
        return 0
    print(f"precommit_secrets: refusing to commit {len(hits)} path(s):",
          file=sys.stderr)
    for path, reason in hits:
        print(f"  {path}: {reason}", file=sys.stderr)
    print("Unstage with `git restore --staged <path>` and add the pattern to "
          ".gitignore. Rotate any credential that was ever staged.",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
