"""Shared helpers for docgen tools: read an envs tree (tfvars, states, aliases).

Everything here is customer-agnostic: values come from the generated
terraform.tfvars.json files, the generated/static provider files, and
(optionally) pulled state JSON files named state-<env>.json.
"""

import json
import re
from pathlib import Path

from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

# shared header styling for the xlsx doc generators (ipam / checklist / config book)
HDR_FONT = Font(bold=True, size=10, color="FFFFFF")
HDR_FILL = PatternFill("solid", fgColor="1F4E79")
BOX = Border(*[Side(style="thin", color="BFBFBF")] * 4)
WRAP = Alignment(vertical="top", wrap_text=True)


def env_dirs(envs_dir: Path) -> list:
    return sorted(p for p in envs_dir.iterdir()
                  if p.is_dir() and re.match(r"^[0-9]{2}-", p.name))


def tfvars(envs_dir: Path, env: str) -> dict:
    p = envs_dir / env / "terraform.tfvars.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def state(states_dir: Path, env: str) -> dict:
    if states_dir is None:
        return {}
    p = states_dir / f"state-{env}.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8-sig"))


def instances(st: dict, rtype: str) -> list:
    """[(resource_name, index_key, attributes)] for managed resources of rtype."""
    out = []
    for r in st.get("resources", []):
        if r.get("mode") == "managed" and r.get("type") == rtype:
            for i in r.get("instances", []):
                out.append((r.get("name"), i.get("index_key"), i.get("attributes", {})))
    return out


_PROVIDER_SPLIT = re.compile(r'provider\s+"huaweicloud"\s*\{')
_ALIAS_RE = re.compile(r'\balias\s*=\s*"([^"]+)"')
_DOMAIN_RE = re.compile(r'\b(?:agency_)?domain_name\s*=\s*("([^"]*)"|var\.([A-Za-z0-9_]+))')


def alias_accounts(envs_dir: Path, env: str) -> dict:
    """{provider_alias: account_name} parsed from the env's provider files.

    Handles literal domain names and var.<name> references (resolved against
    the env's tfvars). The default (un-aliased) provider maps to "" -> master.
    """
    tv = tfvars(envs_dir, env)
    out = {}
    for tf in sorted((envs_dir / env).glob("*.tf")):
        text = tf.read_text(encoding="utf-8")
        chunks = _PROVIDER_SPLIT.split(text)[1:]
        for chunk in chunks:
            # trim to plausibly one block (up to next provider header is already done)
            alias_m = _ALIAS_RE.search(chunk)
            dom_m = _DOMAIN_RE.search(chunk)
            if not alias_m:
                continue
            account = None
            if dom_m:
                if dom_m.group(2) is not None and dom_m.group(2) != "":
                    account = dom_m.group(2)
                elif dom_m.group(3):
                    v = tv.get(dom_m.group(3))
                    if isinstance(v, str):
                        account = v
            if account:
                out[alias_m.group(1)] = account
    return out


def provider_alias_of(resource_provider: str) -> str:
    """'provider[\"...huaweicloud\"].acct_X' -> 'acct_X'; bare provider -> ''. """
    m = re.search(r'provider\[[^\]]+\]\.?(\w*)', resource_provider or "")
    return m.group(1) if m else ""
