"""Shared helpers: scalars, coercion, csv/tag parsing, account lookups."""

import json
import re
from collections import defaultdict
from pathlib import Path
import os

# Where emitted env HCL finds the module library, relative to each env dir.
# Default matches the product layout: <workspace>/modules beside <workspace>/envs/NN-*.
# Override with LZ_MODULE_SOURCE_ROOT for a non-standard checkout.
MODULE_SOURCE_ROOT = os.environ.get("LZ_MODULE_SOURCE_ROOT", "../../modules")


# Apply order == numeric order since the 2026-07 renumber (env numbers now
# match the workbook sheet numbers).
ENV_NAMES = [
    "00-bootstrap",
    "01-foundation",
    "02-finance",
    "03-identity",
    "04-perimeter",
    "05-network",
    "06-observability",
    "07-security",
    "08-network-dns",
    "09-network-cfw",
    "10-network-vpn",
    "11-network-sgacl",
]


def _truthy(v) -> bool:
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("true", "1", "yes", "y")


def _coerce(v, typ: str):
    if typ is None:
        return v
    t = str(typ).lower()
    if t == "bool":
        return _truthy(v)
    if t == "int":
        return int(float(v))
    if t == "csv-list":
        if isinstance(v, list):
            return v
        return [x.strip() for x in str(v).split(",") if x.strip()]
    if t == "json":
        try:
            return json.loads(v) if isinstance(v, str) else v
        except json.JSONDecodeError:
            return v  # pass through raw, will be flagged at plan
    return str(v).strip() if isinstance(v, str) else v


def _home_region(g: dict) -> str:
    """The deployment region, REQUIRED. No silent fallback: a missed region
    must fail the build, not produce a plausible deployment somewhere else."""
    v = _scalar(g, "home_region")
    if not v:
        raise SystemExit("Global.Settings.home_region is required (no default region)")
    return v


def _scalar(table: dict, key: str, default=None):
    if not table:
        return default
    v = table.get(key)
    return default if v is None else v


def _tags_from(spec, table: str) -> dict:
    """Global.<table> Key/Value rows -> {key: value} map (keys lowercased)."""
    out = {}
    for r in (spec.get("Global", {}).get(table) or []):
        k = r.get("Key")
        if k is None or str(k).strip() == "":
            continue
        v = r.get("Value")
        out[str(k).strip().lower()] = "" if v is None else str(v)
    return out


def _default_tags(spec) -> dict:
    """The single default-tag set for ALL accounts (master + members). The separate
    member DefaultTags table was removed — everything now uses MasterDefaultTags."""
    return _tags_from(spec, "MasterDefaultTags")


def _master_default_tags(spec) -> dict:
    """Alias of _default_tags now that there is one shared set (MasterDefaultTags)."""
    return _default_tags(spec)


def _drop_none(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}


def _group_by(rows, key):
    g = defaultdict(list)
    for r in rows:
        k = r.get(key)
        if k is None:
            continue
        g[str(k).strip()].append(r)
    return g


def _csv_or_all(v):
    """Split a csv-list cell into a list. The literal 'all' is preserved as the
    single-element list ['all'] (a sentinel consumed by the ER routing TF)."""
    if v is None:
        return []
    if isinstance(v, list):
        return v
    s = str(v).strip()
    if not s:
        return []
    if s.lower() == "all":
        return ["all"]
    return [x.strip() for x in s.split(",") if x.strip()]


def _split_csv(v):
    if v is None:
        return []
    if isinstance(v, list):
        return v
    return [x.strip() for x in str(v).split(",") if x.strip()]


def _lts_admin(spec) -> str:
    """LTS delegated-admin account, derived from 01_Foundation TrustedServices
    (the enabled service.LTS row's DelegatedAdmin). Not spec input anywhere else:
    log aggregation always converges into this account. '' when absent."""
    for t in (spec.get("01_Foundation", {}).get("TrustedServices") or []):
        if str(t.get("Name") or "").strip() == "service.LTS" and _truthy(t.get("Enabled")):
            return str(t.get("DelegatedAdmin") or "").strip()
    return ""


def _parse_kv_csv(v) -> dict:
    """Parse 'k1=v1,k2=v2' into {k1: v1, k2: v2}. Blank/None -> {}."""
    out = {}
    for part in _split_csv(v):
        if "=" in part:
            k, val = part.split("=", 1)
            k = k.strip()
            if k:
                out[k] = val.strip()
    return out


def _normalize_ou_parent(v) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    if s.lower() in ("", "root", "(root)"):
        return ""
    return s


def _render_tag_policy(row: dict) -> dict:
    """Build a tag_policies entry from {Name, TagKey, TagValue, Scope}.

    - TagValue blank  -> enforce key presence + casing only
    - TagValue filled -> also restrict allowed values
    - Scope blank     -> apply to ALL taggable resource types (no enforced_for)
    - Scope filled    -> restrict enforcement to listed '<service>:<resourceType>' types
    """
    key = str(row["TagKey"]).strip().lower()
    values = row.get("TagValue") if isinstance(row.get("TagValue"), list) else _split_csv(row.get("TagValue"))
    scope  = row.get("Scope")    if isinstance(row.get("Scope"),    list) else _split_csv(row.get("Scope"))
    key_rule = {"tag_key": {"@@assign": key}}
    if values:
        key_rule["tag_value"] = {"@@assign": values}
    if scope:
        key_rule["enforced_for"] = {"@@assign": scope}
    content = {"tags": {key: key_rule}}
    desc_parts = [f"Enforce {key}"]
    desc_parts.append(f"in [{', '.join(values)}]" if values else "key (any value)")
    desc_parts.append(f"on [{', '.join(scope)}]" if scope else "on all services")
    return {
        "name":        row["Name"],
        "description": " ".join(desc_parts),
        "content":     json.dumps(content, separators=(",", ":")),
    }


def _account_names(spec) -> list:
    m1 = spec.get("01_Foundation", {})
    names = []
    for a in (m1.get("CoreAccounts") or []) + (m1.get("WorkloadAccounts") or []):
        n = a.get("Name")
        if n and str(n).strip():
            names.append(str(n).strip())
    return names


def _acct_alias(name) -> str:
    return "acct_" + re.sub(r"[^0-9A-Za-z_]", "_", str(name).strip())
