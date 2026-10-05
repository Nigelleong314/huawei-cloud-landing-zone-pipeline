"""Feature toggles that remove a whole feature from an env, shared by build and
export so the built tree is already what the artifact ships.

SecMaster is the one such feature: `07_Security.Settings.enable_secmaster =
FALSE` (build) or profile `features.secmaster = false` (export) strips its
wiring from 07-security. The env keeps its directory and number; edge
protection in the same env is untouched.
"""

import json
import re
from pathlib import Path

from .helpers import _truthy


def secmaster_enabled(spec: dict) -> bool:
    v = ((spec.get("07_Security") or {}).get("Settings") or {}).get("enable_secmaster")
    return True if v is None or str(v).strip() == "" else _truthy(v)


def _find_block(text: str, header_re: str):
    """(start, end) of the block whose opening line matches header_re; the
    span runs to the matching closing brace, inclusive of the trailing \\n."""
    m = re.search(header_re, text)
    if not m:
        return None
    i = text.index("{", m.start())
    depth = 0
    for j in range(i, len(text)):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                end = j + 1
                if end < len(text) and text[end] == "\n":
                    end += 1
                return m.start(), end
    return None


# tfvars keys only the SecMaster wiring declares
_SECMASTER_TFVARS = ("observability_state_bucket", "secmaster_modules", "security_account",
                     "enable_secmaster", "secmaster_workspace_name", "alert_rules",
                     "enable_hss", "enable_dbss", "enable_member_workspaces",
                     "member_workspace_bindings")


def strip_secmaster(env_dir: Path):
    """Remove the SecMaster wiring from 07-security. Fails CLOSED: a pattern
    that finds nothing means the env drifted from this strip - shipping would
    leave a "disabled" billable feature behind. Idempotent: an env whose
    main.tf no longer calls the security module only has its tfvars cleaned."""

    def _file(name):
        p = env_dir / name
        if not p.exists():
            print(f"  strip[secmaster]: skip {name}: not present")
            return None
        return p

    def _write(p, text):
        p.write_text(text, encoding="utf-8", newline="\n")

    def _fail(name, what):
        raise SystemExit(f"feature secmaster=off strip incomplete ({name}: {what} "
                         f"not found) - update strip_secmaster in core/features.py "
                         f"to match {env_dir.name}")

    def _drop_block(text, header_re, name):
        span = _find_block(text, header_re)
        if span is None:
            _fail(name, f"block {header_re!r}")
        s, e = span
        if s >= 1 and text[s - 1] == "\n" and (s < 2 or text[s - 2] == "\n"):
            s -= 1
        return text[:s] + text[e:]

    def _drop_span(text, start_re, end_re, name):
        ms = re.search(start_re, text, re.M)
        me = re.search(end_re, text[ms.start():], re.M) if ms else None
        if ms is None or me is None:
            _fail(name, f"span {start_re!r}")
        end = ms.start() + me.end()
        if end < len(text) and text[end] == "\n":
            end += 1
        return text[:ms.start()] + text[end:]

    main = env_dir / "main.tf"
    done = main.exists() and 'module "security" {' not in main.read_text(encoding="utf-8")

    p = None if done else _file("main.tf")
    if p:
        text = p.read_text(encoding="utf-8")
        text = _drop_block(text, r'data "terraform_remote_state" "observability" \{', p.name)
        text = "\n".join(l for l in text.split("\n") if not re.match(
            r'^  observability = data\.terraform_remote_state\.observability\.outputs$', l))
        text = _drop_span(text, r'^\n  # Wire SecMaster cloud_log_resources', r'^  \]$', p.name)
        text = _drop_span(text, r'^\n# Warn \(not fail\) when SecMaster deploys', r'^\}$', p.name)
        text = _drop_block(text, r'module "security" \{', p.name)
        # the reviewed artifact keeps a separating blank line in locals
        text = text.replace("network       = data.terraform_remote_state.network.outputs\n}",
                            "network       = data.terraform_remote_state.network.outputs\n\n}")
        _write(p, text)

    p = None if done else _file("variables.tf")
    if p:
        text = p.read_text(encoding="utf-8")
        for name in ("observability_state_bucket", "observability_state_key",
                     "security_account", "enable_secmaster", "secmaster_workspace_name",
                     "secmaster_modules", "alert_rules", "enable_hss", "enable_dbss",
                     "enable_member_workspaces", "member_workspace_bindings"):
            span = _find_block(text, rf'variable "{name}" \{{')
            if span:
                text = text[:span[0]] + text[span[1]:]
        text = re.sub(r"\n{4,}", "\n\n\n", text)
        _write(p, text)

    p = None if done else _file("outputs.tf")
    if p:
        text = p.read_text(encoding="utf-8").replace(
            'output "secmaster_workspace_id" { value = module.security.secmaster_workspace_id }',
            "# No outputs: edge protection exposes nothing downstream.")
        _write(p, text)

    p = None if done else _file("providers.tf")
    if p:
        text = _drop_block(p.read_text(encoding="utf-8"),
                           r'provider "huaweicloud" \{\n  alias              = "lz_security"',
                           p.name)
        _write(p, text)

    p = _file("terraform.tfvars.json")
    if p:
        data = json.loads(p.read_text(encoding="utf-8"))
        for k in _SECMASTER_TFVARS:
            data.pop(k, None)
        _write(p, json.dumps(data, indent=2, sort_keys=False) + "\n")

    p = _file("terraform.tfvars.example")
    if p:
        match = (r'^(observability_state_bucket|# enable_secmaster|# enable_hss|# enable_dbss'
                 r'|# enable_member_workspaces|# member_workspace_bindings)')
        text = "\n".join(l for l in p.read_text(encoding="utf-8").split("\n")
                         if not re.match(match, l))
        _write(p, text)
