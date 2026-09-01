"""Classify a Terraform plan (JSON) against known-benign and destructive rules.

Input is `terraform show -json <planfile>` output. Every resource change is
classified as:

  benign      - update whose changed attribute paths ALL match a benign rule
                for that resource type (LZR-019 known drift)
  create      - additions (normal forward changes)
  update      - in-place updates needing review
  destructive - any delete or replace; PROTECTED types are called out loudly
                (LZR-012 class: replacements that change public endpoints or
                destroy stateful/identity resources)

Exit codes: 0 = no changes; 2 = changes, none destructive; 3 = destructive.

Usage:
    terraform plan -out tf.plan && terraform show -json tf.plan > plan.json
    py tools/plan_triage.py plan.json [plan2.json ...] [--json]

Benign rules file format (defaults built in):
    [{"type": "huaweicloud_dns_endpoint", "paths": ["ip_addresses(\\[.*)?"]},
     {"type": "huaweicloud_lts_transfer",  "paths": [".*obs_dir_prefix_name"]}]
A change is benign only if EVERY changed path matches one of the rule's path
regexes (anchored). Rules are matched by anchored regex on the resource type.
"""

import argparse
import os
import json
import re
import sys
from pathlib import Path

# LZR-019: the two drifts this platform is known to re-report harmlessly.
DEFAULT_BENIGN = [
    {"type": r"huaweicloud_dns_endpoint", "paths": [r"ip_addresses(\[.*)?"]},
    {"type": r"huaweicloud_lts_transfer", "paths": [r".*obs_dir_prefix_name"]},
]

# LZR-012 class: destroying/replacing these is never routine.
DEFAULT_PROTECTED = [
    r"huaweicloud_vpn_gateway",            # replacement = new public IPs
    r"huaweicloud_organizations_.*",
    r"huaweicloud_obs_bucket.*",
    r"huaweicloud_kms_key",
    r"huaweicloud_vpc$",
    r"huaweicloud_vpc_subnet",
    r"huaweicloud_er_instance",
    r"huaweicloud_cts_tracker",
    r"huaweicloud_identity_.*",
    r"huaweicloud_lts_group",          # deleting breaks audit continuity
    r"huaweicloud_lts_transfer",
    r"huaweicloud_rms_.*",
    r"huaweicloud_er_route_table",
    r"huaweicloud_elb_loadbalancer",   # replacement = new public endpoint
]


def changed_paths(before, after, prefix=""):
    """Dotted paths of every leaf that differs between before and after."""
    if isinstance(before, dict) and isinstance(after, dict):
        out = []
        for k in sorted(set(before) | set(after)):
            out.extend(changed_paths(before.get(k), after.get(k),
                                     f"{prefix}.{k}" if prefix else k))
        return out
    if isinstance(before, list) and isinstance(after, list):
        out = []
        for i in range(max(len(before), len(after))):
            b = before[i] if i < len(before) else None
            a = after[i] if i < len(after) else None
            out.extend(changed_paths(b, a, f"{prefix}[{i}]"))
        return out
    if before != after:
        return [prefix or "(root)"]
    return []


def unknown_paths(after_unknown, prefix=""):
    """Paths marked computed/unknown in the plan (counted as changes)."""
    if isinstance(after_unknown, dict):
        out = []
        for k, v in after_unknown.items():
            out.extend(unknown_paths(v, f"{prefix}.{k}" if prefix else k))
        return out
    if isinstance(after_unknown, list):
        out = []
        for i, v in enumerate(after_unknown):
            out.extend(unknown_paths(v, f"{prefix}[{i}]"))
        return out
    return [prefix] if after_unknown is True and prefix else []


def _match_any(patterns, s):
    return any(re.fullmatch(p, s) for p in patterns)


def classify_change(rc, benign_rules, protected):
    actions = rc.get("change", {}).get("actions", [])
    rtype = rc.get("type", "")
    if actions in (["no-op"], ["read"], []):
        return None
    if "delete" in actions:
        kind = "replace" if "create" in actions else "delete"
        prot = _match_any(protected, rtype)
        return {"class": "destructive", "kind": kind, "protected": prot}
    if actions == ["create"]:
        return {"class": "create"}
    if "update" in actions:
        ch = rc.get("change", {})
        paths = changed_paths(ch.get("before"), ch.get("after"))
        paths += unknown_paths(ch.get("after_unknown", {}))
        paths = sorted(set(paths))
        for rule in benign_rules:
            if re.fullmatch(rule["type"], rtype) and paths and \
                    all(_match_any(rule["paths"], p) for p in paths):
                return {"class": "benign", "paths": paths}
        return {"class": "update", "paths": paths}
    return {"class": "update", "paths": []}


def triage(plan: dict, benign_rules=None, protected=None) -> dict:
    benign_rules = benign_rules if benign_rules is not None else DEFAULT_BENIGN
    protected = protected if protected is not None else DEFAULT_PROTECTED
    buckets = {"benign": [], "create": [], "update": [], "destructive": []}
    for rc in plan.get("resource_changes", []):
        c = classify_change(rc, benign_rules, protected)
        if c is None:
            continue
        c["address"] = rc.get("address", "?")
        c["type"] = rc.get("type", "?")
        buckets[c["class"]].append(c)
    return buckets


def report(name: str, buckets: dict) -> str:
    lines = [f"== {name} =="]
    total = sum(len(v) for v in buckets.values())
    if total == 0:
        lines.append("  no changes")
        return "\n".join(lines)
    for c in buckets["destructive"]:
        flag = "  ** PROTECTED **" if c.get("protected") else ""
        lines.append(f"  DESTRUCTIVE {c['kind']:8} {c['address']}{flag}")
    for c in buckets["update"]:
        detail = ", ".join(c.get("paths", [])[:6]) or "(attribute diff)"
        lines.append(f"  update              {c['address']}  [{detail}]")
    for c in buckets["create"]:
        lines.append(f"  create              {c['address']}")
    for c in buckets["benign"]:
        detail = ", ".join(c.get("paths", [])[:4])
        lines.append(f"  benign (known)      {c['address']}  [{detail}]")
    lines.append(f"  totals: {len(buckets['destructive'])} destructive, "
                 f"{len(buckets['update'])} update, {len(buckets['create'])} create, "
                 f"{len(buckets['benign'])} known-benign")
    return "\n".join(lines)




# ────────────────────────────────────────────────────────────────────────────
# Monthly cost estimate (pay-per-use x hours_per_month)
# ────────────────────────────────────────────────────────────────────────────

HOURS_PER_MONTH = 720  # 30 days x 24 h (customer convention)
CALCULATOR = "https://www.huaweicloud.com/intl/en-us/pricing/calculator.html"


def _billable_items(rc):
    """(rate_key, qty, unit, label) entries for one CREATED resource."""
    after = rc.get("change", {}).get("after") or {}
    t = rc.get("type", "")
    out = []
    if t == "huaweicloud_compute_instance":
        flavor = after.get("flavor_name") or after.get("flavor_id") or "?"
        out.append((f"ecs.{flavor}", 1, "hour", f"ECS {flavor}"))
        if after.get("system_disk_size"):
            dt = after.get("system_disk_type") or "GPSSD"
            out.append((f"evs.{dt}", after["system_disk_size"], "GB-month",
                        f"EVS {dt} (system disk)"))
    elif t == "huaweicloud_evs_volume":
        dt = after.get("volume_type") or "?"
        out.append((f"evs.{dt}", after.get("size") or 0, "GB-month", f"EVS {dt}"))
    elif t == "huaweicloud_vpc_eip":
        bw = 0
        for b in after.get("bandwidth") or []:
            bw += b.get("size") or 0
        out.append(("eip.bandwidth", bw or 1, "Mbps-month", "EIP bandwidth"))
    elif t == "huaweicloud_natv3_gateway":
        spec = after.get("spec") or "?"
        out.append((f"nat.{spec}", 1, "hour", f"NAT gateway spec {spec}"))
    elif t == "huaweicloud_elb_loadbalancer":
        out.append(("elb.instance", 1, "hour", "ELB load balancer"))
    elif t == "huaweicloud_cbr_vault":
        out.append(("cbr.backup", after.get("size") or 0, "GB-month", "CBR vault"))
    elif t == "huaweicloud_vpn_gateway":
        fl = after.get("flavor") or "?"
        out.append((f"vpn.{fl}", 1, "hour", f"VPN gateway {fl}"))
    elif t == "huaweicloud_waf_dedicated_instance":
        code = after.get("specification_code") or "?"
        out.append((f"waf.{code}", 1, "hour", f"Dedicated WAF {code}"))
    elif t == "huaweicloud_cfw_firewall":
        out.append(("cfw.instance", 1, "hour", "Cloud Firewall"))
    elif t == "huaweicloud_rds_instance":
        fl = after.get("flavor") or "?"
        out.append((f"rds.{fl}", 1, "hour", f"RDS {fl}"))
    return out


def load_pricing(path=None):
    """Rate card: {"region", "currency", "hours_per_month", "rates": {key: rate|null}}.
    Resolution: explicit path, then pricing/<LZ_PRICING_REGION>.json, then any
    single card in pricing/; missing -> empty card (quantities still reported).
    The report always names the card's region so a mismatched card is visible."""
    pdir = Path(__file__).parent / "pricing"
    candidates = []
    if path:
        candidates.append(Path(path))
    region = os.environ.get("LZ_PRICING_REGION")
    if region:
        candidates.append(pdir / f"{region}.json")
    cards = sorted(pdir.glob("*.json")) if pdir.exists() else []
    if len(cards) == 1:
        candidates.append(cards[0])
    for c in candidates:
        if c and c.exists():
            return json.loads(c.read_text(encoding="utf-8"))
    return {"currency": "USD", "hours_per_month": HOURS_PER_MONTH, "rates": {}}


def cost_summary(plan: dict, pricing: dict) -> dict:
    """Aggregate CREATED billables; monthly = hourly x hours_per_month or
    per-GB/Mbps-month x qty. Rates absent from the card -> unpriced."""
    hours = pricing.get("hours_per_month", HOURS_PER_MONTH)
    rates = pricing.get("rates", {})
    agg = {}   # rate_key -> {qty, unit, label, count}
    destroyed = 0
    for rc in plan.get("resource_changes", []):
        actions = rc.get("change", {}).get("actions", [])
        if "create" in actions:
            for key, qty, unit, label in _billable_items(rc):
                a = agg.setdefault(key, {"qty": 0, "count": 0, "unit": unit, "label": label})
                a["qty"] += qty
                a["count"] += 1
        elif "delete" in actions and _billable_items(rc):
            destroyed += 1
    items, total, unpriced = [], 0.0, 0
    for key in sorted(agg):
        a = agg[key]
        rate = rates.get(key)
        monthly = None
        if isinstance(rate, (int, float)):
            monthly = rate * hours * a["count"] if a["unit"] == "hour" else rate * a["qty"]
            total += monthly
        else:
            unpriced += 1
        items.append({"key": key, "label": a["label"], "count": a["count"],
                      "qty": a["qty"], "unit": a["unit"], "monthly": monthly})
    return {"items": items, "total_known": round(total, 2), "unpriced": unpriced,
            "destroyed_billables": destroyed,
            "currency": pricing.get("currency", "USD"), "hours": hours}


def cost_report(name: str, plan: dict, pricing: dict) -> str:
    c = cost_summary(plan, pricing)
    if not c["items"] and not c["destroyed_billables"]:
        return ""
    cur = c["currency"]
    card_region = pricing.get("region") or "unknown"
    lines = [f"== {name}: monthly cost estimate (pay-per-use x {c['hours']} h; "
             f"rate card: {card_region} - verify it matches your deployment region) =="]
    for it in c["items"]:
        qty = f"x{it['count']}" if it["unit"] == "hour" else f"{it['qty']:,} {it['unit'].split('-')[0]}"
        price = f"{cur} {it['monthly']:,.2f}/month" if it["monthly"] is not None             else "RATE NOT SET (see pricing card)"
        lines.append(f"  + {it['label']:<38} {qty:>12}   {price}")
    if c["total_known"]:
        lines.append(f"  known subtotal: {cur} {c['total_known']:,.2f}/month"
                     + (f"  ({c['unpriced']} item(s) unpriced)" if c["unpriced"] else ""))
    elif c["items"]:
        lines.append(f"  no rates set - fill the pricing card to price {len(c['items'])} item(s)")
    if c["destroyed_billables"]:
        lines.append(f"  note: {c['destroyed_billables']} billable resource(s) destroyed (cost reduction)")
    lines.append(f"  verify: {CALCULATOR}")
    return "\n".join(lines)


def main_files(paths, rules=None, as_json=False):
    """Library entry: triage a list of plan-JSON files; returns worst exit code."""
    worst = 0
    results = {}
    for pth in paths:
        plan = json.loads(Path(pth).read_text(encoding="utf-8"))
        buckets = triage(plan, rules)
        results[str(pth)] = buckets
        if not as_json:
            print(report(str(pth), buckets))
        if buckets["destructive"]:
            worst = max(worst, 3)
        elif sum(len(v) for v in buckets.values()):
            worst = max(worst, 2)
    if as_json:
        print(json.dumps(results, indent=2))
    return worst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("plans", nargs="+", help="terraform show -json output file(s)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()
    return main_files(args.plans, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
