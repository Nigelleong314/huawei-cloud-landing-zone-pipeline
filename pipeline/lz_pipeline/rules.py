"""Platform rule registry (LZR rules).

Codifies the Huawei Cloud landing-zone constraints that previously lived as
prose in CLAUDE.md / module READMEs / cookbooks. Every rule has a stable ID,
a severity, and one of:

  check="spec"    - executable here against the parsed workbook spec dict
  check="tree"    - executable here against a generated envs tree / modules dir
  check="runtime" - enforced elsewhere (runner preflight, plan triage, module
                    design, existing validate()); listed for the registry only

Usage (library):
    from rules import run_spec_rules, run_tree_rules, REGISTRY
    findings = run_spec_rules(spec)          # list[Finding]
    findings += run_tree_rules(envs_dir, modules_dir)

Usage (CLI):
    py rules.py --workbook "landing_zone_spec - acme.xlsx" \
                [--envs-dir envs] [--modules-dir auto] [--list]

Exit code: 1 if any ERROR finding, else 0 (warnings never fail).

A finding message always starts with the sheet name (e.g. "05_Network: ...")
so callers can scope failures the same way build_envs.validate() output is
scoped on subset builds.
"""

import argparse
import ipaddress
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# ────────────────────────────────────────────────────────────────────────────
# Model
# ────────────────────────────────────────────────────────────────────────────

@dataclass
class Finding:
    rule_id: str
    severity: str   # "error" | "warn"
    message: str    # starts with "<sheet>: " for spec rules

    def __str__(self):
        return f"[{self.rule_id}/{self.severity}] {self.message}"


@dataclass
class Rule:
    rule_id: str
    severity: str
    check: str       # spec | tree | runtime
    title: str
    enforced_by: str = ""   # for check="runtime": where it lives
    fn: object = None       # callable for spec/tree rules

    @property
    def origin(self) -> str:
        return ORIGINS.get(self.rule_id, "IMPLEMENTATION")


# What KIND of constraint each rule encodes, so an implementation choice is
# never mistaken for a Huawei Cloud requirement:
#   PLATFORM       - hard behavior of Huawei Cloud itself
#   PROVIDER       - behavior of the Terraform provider
#   SAFETY         - a deliberate safety gate of this framework
#   IMPLEMENTATION - a choice of this reference implementation
#   OPERATIONAL    - an operating procedure the runner/CI enforces
ORIGINS = {
    "LZR-001": "PLATFORM",  "LZR-002": "PLATFORM",  "LZR-003": "PLATFORM",
    "LZR-004": "PROVIDER",  "LZR-005": "PROVIDER",  "LZR-006": "PLATFORM",
    "LZR-007": "PLATFORM",  "LZR-008": "IMPLEMENTATION",
    "LZR-009": "PLATFORM",  "LZR-010": "PLATFORM",
    "LZR-011a": "PLATFORM", "LZR-011b": "PLATFORM", "LZR-011c": "PROVIDER",
    "LZR-011d": "IMPLEMENTATION", "LZR-011e": "IMPLEMENTATION",
    "LZR-012": "PLATFORM",  "LZR-013": "PLATFORM",
    "LZR-014": "PLATFORM",  "LZR-014b": "IMPLEMENTATION",
    "LZR-015": "PLATFORM",  "LZR-015b": "IMPLEMENTATION",
    "LZR-016": "PLATFORM",  "LZR-017": "PLATFORM",
    "LZR-018": "OPERATIONAL", "LZR-019": "PROVIDER",
    "LZR-020": "PLATFORM",  "LZR-021": "IMPLEMENTATION",
    "LZR-022": "SAFETY",    "LZR-023": "SAFETY",   "LZR-024": "SAFETY",
    "LZR-025": "SAFETY",    "LZR-026": "IMPLEMENTATION",
    "LZR-027": "SAFETY",    "LZR-030": "IMPLEMENTATION",
    "LZR-031": "IMPLEMENTATION", "LZR-032": "SAFETY",
    "LZR-033": "IMPLEMENTATION", "LZR-034": "SAFETY",
    "LZR-035": "SAFETY", "LZR-036": "IMPLEMENTATION",
}

REGISTRY: list = []


def _rule(rule_id, severity, check, title, enforced_by=""):
    def deco(fn):
        REGISTRY.append(Rule(rule_id, severity, check, title, enforced_by, fn))
        return fn
    return deco


def _doc(rule_id, severity, check, title, enforced_by):
    """Register a non-executable (documentation-only) rule."""
    REGISTRY.append(Rule(rule_id, severity, check, title, enforced_by, None))


# ────────────────────────────────────────────────────────────────────────────
# Shared helpers (no imports from build_envs: keep this module standalone)
# ────────────────────────────────────────────────────────────────────────────

def _scalar(table: dict, key: str, default=None):
    v = (table or {}).get(key)
    return default if v is None else v


def _truthy(v) -> bool:
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("true", "1", "yes", "y")


def _csv(v):
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    return [x.strip() for x in str(v).split(",") if x.strip()]


def _net(s):
    """Parse a CIDR/IP into an IPv4Network, or None if not parseable."""
    s = str(s).strip()
    try:
        if "/" not in s:
            return ipaddress.ip_network(s + "/32")
        return ipaddress.ip_network(s, strict=True)
    except ValueError:
        return None


def _all_vpcs(spec):
    """[(sheet_hint, vpc_name, cidr_str)] over hub + spoke tables."""
    m3 = spec.get("05_Network", {})
    out = []
    for v in (m3.get("HubVPCs") or []):
        if v.get("VPCName"):
            out.append(("HubVPCs", str(v["VPCName"]).strip(), v.get("CIDR")))
    for v in (m3.get("SpokeVPCs") or []):
        if v.get("VPCName"):
            out.append(("SpokeVPCs", str(v["VPCName"]).strip(), v.get("CIDR")))
    return out


def _all_subnets(spec):
    """[(table, vpc_name, subnet_name, cidr_str)]"""
    m3 = spec.get("05_Network", {})
    out = []
    for t in ("HubSubnets", "SpokeSubnets"):
        for s in (m3.get(t) or []):
            if s.get("Name"):
                out.append((t, str(s.get("VPCName") or "").strip(),
                            str(s["Name"]).strip(), s.get("CIDR")))
    return out


# ────────────────────────────────────────────────────────────────────────────
def is_placeholder(v) -> bool:
    """True for an unresolved sentinel in any position.

    Public so the type and format checks can stay quiet about a value this
    already owns: "REPLACE_WITH_ER_BGP_ASN is not a valid network" tells a
    reader nothing LZR-032 has not said better, and two errors for one
    unfilled field made every count meaningless.
    """
    if not isinstance(v, str):
        return False
    t = v.strip().lower()
    return any(tok in t for tok in _PLACEHOLDER_PREFIXES) or (
        t.startswith("<") and t.endswith(">"))


# Spec rules (executable against the parsed workbook dict)
# ────────────────────────────────────────────────────────────────────────────

@_rule("LZR-022", "error", "spec", "Every CIDR must be a valid IPv4 network (no host bits set)")
def r_cidr_format(spec):
    # A placeholder CIDR is LZR-032's finding, not a format complaint.
    out = []
    for src, name, cidr in _all_vpcs(spec):
        if cidr is not None and not is_placeholder(cidr) and _net(cidr) is None:
            out.append(f"05_Network: {src}[{name}] CIDR={cidr!r} is not a valid network (check host bits / format)")
    for t, vpc, name, cidr in _all_subnets(spec):
        if cidr is not None and not is_placeholder(cidr) and _net(cidr) is None:
            out.append(f"05_Network: {t}[{name}] CIDR={cidr!r} is not a valid network (check host bits / format)")
    sup = _scalar(spec.get("05_Network", {}).get("Settings", {}), "spoke_private_supernet")
    if sup and not is_placeholder(sup) and _net(sup) is None:
        out.append(f"05_Network: Settings.spoke_private_supernet={sup!r} is not a valid network")
    return out


@_rule("LZR-023", "error", "spec", "Subnet CIDRs must lie within their VPC CIDR")
def r_subnet_in_vpc(spec):
    vpc_nets = {}
    for _, name, cidr in _all_vpcs(spec):
        n = _net(cidr) if cidr else None
        if n:
            vpc_nets[name] = n
    out = []
    for t, vpc, name, cidr in _all_subnets(spec):
        sn = _net(cidr) if cidr else None
        vn = vpc_nets.get(vpc)
        if sn and vn and not sn.subnet_of(vn):
            out.append(f"05_Network: {t}[{name}] CIDR {cidr} is outside its VPC {vpc} ({vn})")
    return out


@_rule("LZR-024", "error", "spec", "VPC CIDRs must not overlap each other")
def r_vpc_overlap(spec):
    nets = [(name, _net(cidr)) for _, name, cidr in _all_vpcs(spec) if cidr and _net(cidr)]
    out = []
    for i in range(len(nets)):
        for j in range(i + 1, len(nets)):
            (n1, a), (n2, b) = nets[i], nets[j]
            if a.overlaps(b):
                out.append(f"05_Network: VPC CIDRs overlap: {n1} ({a}) and {n2} ({b})")
    return out


@_rule("LZR-025", "error", "spec", "Subnets within one VPC must not overlap each other")
def r_subnet_overlap(spec):
    by_vpc = {}
    for t, vpc, name, cidr in _all_subnets(spec):
        n = _net(cidr) if cidr else None
        if n:
            by_vpc.setdefault(vpc, []).append((name, n))
    out = []
    for vpc, subs in by_vpc.items():
        for i in range(len(subs)):
            for j in range(i + 1, len(subs)):
                (n1, a), (n2, b) = subs[i], subs[j]
                if a.overlaps(b):
                    out.append(f"05_Network: subnets overlap in VPC {vpc}: {n1} ({a}) and {n2} ({b})")
    return out


@_rule("LZR-026", "warn", "spec", "Spoke VPC CIDRs should lie within spoke_private_supernet")
def r_spoke_supernet(spec):
    m3 = spec.get("05_Network", {})
    sup = _scalar(m3.get("Settings", {}), "spoke_private_supernet")
    sn = _net(sup) if sup else None
    if not sn:
        return []
    out = []
    for v in (m3.get("SpokeVPCs") or []):
        n = _net(v.get("CIDR")) if v.get("CIDR") else None
        if n and not n.subnet_of(sn):
            out.append(f"05_Network: SpokeVPCs[{v.get('VPCName')}] CIDR {v.get('CIDR')} "
                       f"is outside spoke_private_supernet {sup}")
    return out


@_rule("LZR-014", "error", "spec", "Resolver rules must include the inbound-resolver VPC in their VPCs list")
def r_dns_resolver_vpc(spec):
    dns = spec.get("08_DNS", {})
    inbound_vpcs = {str(e.get("VPC") or "").strip()
                    for e in (dns.get("ResolverEndpoints") or [])
                    if str(e.get("Direction") or "").strip().lower() == "inbound" and e.get("VPC")}
    if not inbound_vpcs:
        return []
    out = []
    for r in (dns.get("ResolverRules") or []):
        vpcs = set(_csv(r.get("VPCs")))
        if vpcs and not (vpcs & inbound_vpcs):
            out.append(f"08_DNS: ResolverRules[{r.get('Name')}] VPCs={sorted(vpcs)} does not include the "
                       f"resolver VPC ({', '.join(sorted(inbound_vpcs))}) - the rule will never match "
                       "queries arriving through the central resolver")
    return out


@_rule("LZR-014b", "warn", "spec", "Private zones should include the inbound-resolver VPC (org-wide resolvability)")
def r_dns_zone_vpc(spec):
    dns = spec.get("08_DNS", {})
    inbound_vpcs = {str(e.get("VPC") or "").strip()
                    for e in (dns.get("ResolverEndpoints") or [])
                    if str(e.get("Direction") or "").strip().lower() == "inbound" and e.get("VPC")}
    if not inbound_vpcs:
        return []
    out = []
    for z in (dns.get("PrivateZones") or []):
        vpcs = set(_csv(z.get("VPCs")))
        if vpcs and not (vpcs & inbound_vpcs):
            out.append(f"08_DNS: PrivateZones[{z.get('Name')}] does not list the resolver VPC "
                       f"({', '.join(sorted(inbound_vpcs))}); the zone resolves only inside its own VPC list")
    return out


_CFW_KINDS = {"vpc", "nat", "eip"}
_CFW_ACTIONS = {"allow", "deny"}
_CFW_PROTOS = {"tcp", "udp", "icmp", "any"}


@_rule("LZR-011a", "error", "spec", "CFW address-group members must not overlap one another")
def r_cfw_group_overlap(spec):
    out = []
    for g in (spec.get("09_CFW", {}).get("AddressGroups") or []):
        members = _csv(g.get("Members"))
        nets = []
        for m in members:
            if "-" in m and "/" not in m:
                continue  # explicit IP range member: not checked
            n = _net(m)
            if n:
                nets.append((m, n))
        for i in range(len(nets)):
            for j in range(i + 1, len(nets)):
                (m1, a), (m2, b) = nets[i], nets[j]
                if a.overlaps(b):
                    out.append(f"09_CFW: AddressGroups[{g.get('Name')}] members overlap: {m1} and {m2} "
                               "(the CFW create API returns no ID for overlapping members)")
    return out


@_rule("LZR-011b", "error", "spec", "Inbound internet (eip) rules cannot reference domain groups")
def r_cfw_inbound_domaingroup(spec):
    out = []
    for r in (spec.get("09_CFW", {}).get("ACLRules") or []):
        kind = str(r.get("Kind") or "").strip().lower()
        direction = str(r.get("Direction") or "").strip().lower()
        if kind == "eip" and direction in ("", "inbound"):
            toks = _csv(r.get("Source")) + _csv(r.get("Destination"))
            if any(t.lower().startswith("domaingroup:") for t in toks):
                out.append(f"09_CFW: ACLRules[{r.get('Name')}] is an inbound internet rule referencing a "
                           "domain group (platform limitation: rejected at apply, CFW.00400028)")
    return out


@_rule("LZR-011c", "error", "spec", "CFW rule enums: Kind in vpc|nat|eip, Action in allow|deny, Status in enable|disable")
def r_cfw_enums(spec):
    out = []
    for r in (spec.get("09_CFW", {}).get("ACLRules") or []):
        name = r.get("Name")
        kind = str(r.get("Kind") or "").strip().lower()
        if kind and kind not in _CFW_KINDS:
            out.append(f"09_CFW: ACLRules[{name}] Kind={r.get('Kind')!r} (use vpc, nat or eip)")
        act = str(r.get("Action") or "").strip().lower()
        if act and act not in _CFW_ACTIONS:
            out.append(f"09_CFW: ACLRules[{name}] Action={r.get('Action')!r} (use allow or deny)")
        st = str(r.get("Status") or "").strip().lower()
        if st and st not in ("enable", "disable"):
            out.append(f"09_CFW: ACLRules[{name}] Status={r.get('Status')!r} (use enable or disable)")
    return out


@_rule("LZR-011d", "warn", "spec", "CFW service tokens: any | svcgroup:NAME | proto/port/port (icmp -> icmp/any/any)")
def r_cfw_service_format(spec):
    out = []
    for r in (spec.get("09_CFW", {}).get("ACLRules") or []):
        for t in _csv(r.get("Service")):
            tl = t.lower()
            if tl == "any" or tl.startswith("svcgroup:"):
                continue
            parts = tl.split("/")
            if len(parts) != 3 or parts[0] not in _CFW_PROTOS:
                out.append(f"09_CFW: ACLRules[{r.get('Name')}] Service token {t!r} is not "
                           "'any', 'svcgroup:NAME' or 'proto/src-port/dst-port'")
            elif parts[0] == "icmp" and (parts[1], parts[2]) != ("any", "any"):
                out.append(f"09_CFW: ACLRules[{r.get('Name')}] ICMP has no ports: use icmp/any/any")
    return out


@_rule("LZR-011e", "error", "spec", "CFW group tokens must reference existing enabled groups")
def r_cfw_group_refs(spec):
    cfw = spec.get("09_CFW", {})
    addr = {str(g.get("Name") or "").strip() for g in (cfw.get("AddressGroups") or [])}
    dom = {str(g.get("Name") or "").strip() for g in (cfw.get("DomainGroups") or [])}
    svc = {str(g.get("Name") or "").strip() for g in (cfw.get("ServiceGroups") or [])}
    out = []
    for r in (cfw.get("ACLRules") or []):
        name = r.get("Name")
        for t in _csv(r.get("Source")) + _csv(r.get("Destination")):
            tl = t.lower()
            if tl.startswith("addrgroup:") and t.split(":", 1)[1].strip() not in addr:
                out.append(f"09_CFW: ACLRules[{name}] references unknown address group {t!r}")
            if tl.startswith("domaingroup:") and t.split(":", 1)[1].strip() not in dom:
                out.append(f"09_CFW: ACLRules[{name}] references unknown domain group {t!r}")
        # the CFW resource takes ONE destination domain group per rule; a second
        # token would be silently dropped by the module - reject it here
        dom_tokens = [t for t in _csv(r.get("Destination"))
                      if t.lower().startswith("domaingroup:")]
        if len(dom_tokens) > 1:
            out.append(f"09_CFW: ACLRules[{name}] has {len(dom_tokens)} domaingroup: "
                       "destinations - CFW supports one domain group per rule; split "
                       "into one rule per group")
        for t in _csv(r.get("Service")):
            if t.lower().startswith("svcgroup:") and t.split(":", 1)[1].strip() not in svc:
                out.append(f"09_CFW: ACLRules[{name}] references unknown service group {t!r}")
    return out


@_rule("LZR-003", "warn", "spec", "Wildcards in tag-policy values: StringLike matches substrings, not wildcards")
def r_stringlike_wildcard(spec):
    out = []
    for p in (spec.get("01_Foundation", {}).get("TagPolicies") or []):
        vals = _csv(p.get("TagValue"))
        if any("*" in v for v in vals):
            out.append(f"01_Foundation: TagPolicies[{p.get('Name')}] TagValue contains '*': Huawei "
                       "StringLike/StringNotLike are substring matches - confirm the rendered policy "
                       "uses StringMatch for wildcard semantics")
    return out


@_rule("LZR-027", "error", "spec", "Literal secrets never enter the spec (PSK must be blank or a reference)")
def r_vpn_psk_in_sheet(spec):
    # A blank cell, a variable/secret REFERENCE, or an obvious placeholder is
    # fine; anything else is treated as a literal secret and BLOCKS
    # validation/build. Deterministic enforcement - never rely on the model
    # (or the operator) remembering the rule.
    ok_prefixes = ("var.", "secret", "secret://", "tbd", "<", "replace_with", "${")
    out = []
    for c in (spec.get("10_VPN", {}).get("Connections") or []):
        psk = str(c.get("PSK") or "").strip()
        if psk and not psk.lower().startswith(ok_prefixes):
            out.append(f"10_VPN: Connections[{c.get('Name')}] carries a literal PSK - "
                       "use a reference (secret://... / var....) or a REPLACE_WITH placeholder; "
                       "the real value belongs in the env's gitignored secrets tfvars only")
    return out


@_rule("LZR-030", "error", "spec", "SG rules must reference existing groups; sg:/self remotes stay in-account; vocab and ports must parse")
def r_sgacl_rules(spec):
    m = spec.get("11_SGACL", {})
    groups = m.get("SecurityGroups") or []
    sg_account = {}
    out = []
    accounts = {str(a.get("Name") or "").strip()
                for t in ("WorkloadAccounts", "CoreAccounts")
                for a in (spec.get("01_Foundation", {}).get(t) or [])}
    for r in groups:
        name = str(r.get("Name") or "").strip()
        acct = str(r.get("Account") or "").strip()
        if not name:
            continue
        if name in sg_account:
            out.append(f"11_SGACL: SecurityGroups[{name}] duplicate group name (names must be unique across accounts)")
        sg_account[name] = acct
        if accounts and acct and acct not in accounts:
            out.append(f"11_SGACL: SecurityGroups[{name}] Account={acct!r} is not a 01_Foundation account")

    def _ports_ok(p):
        p = str(p or "").strip()
        if not p:
            return True
        for part in p.split(","):
            part = part.strip()
            bits = part.split("-")
            if not (1 <= len(bits) <= 2) or not all(b.strip().isdigit() and 1 <= int(b) <= 65535 for b in bits):
                return False
            if len(bits) == 2 and int(bits[0]) > int(bits[1]):
                return False
        return True

    for r in m.get("SGRules") or []:
        sg = str(r.get("SG") or "").strip()
        label = f"11_SGACL: SGRules[{sg or '?'}/{r.get('Remote')}]"
        if sg not in sg_account:
            out.append(f"{label} SG={sg!r} does not name a SecurityGroups row")
            continue
        d = str(r.get("Direction") or "").strip().lower()
        if d and d not in ("ingress", "egress"):
            out.append(f"{label} Direction={d!r} must be ingress|egress")
        proto = str(r.get("Protocol") or "").strip().lower()
        if proto and proto not in ("tcp", "udp", "icmp", "any"):
            out.append(f"{label} Protocol={proto!r} must be tcp|udp|icmp|any")
        act = str(r.get("Action") or "").strip().lower()
        if act and act not in ("allow", "deny"):
            out.append(f"{label} Action={act!r} must be allow|deny")
        if not _ports_ok(r.get("Ports")):
            out.append(f"{label} Ports={r.get('Ports')!r} must be port | a-b | comma list (1-65535)")
        remote = str(r.get("Remote") or "").strip()
        if not remote:
            out.append(f"{label} Remote is required (CIDR | sg:<Name> | self)")
        elif remote.startswith("sg:"):
            target = remote[3:].strip()
            if target not in sg_account:
                out.append(f"{label} Remote={remote!r} does not name a SecurityGroups row")
            elif sg_account[target] != sg_account[sg]:
                out.append(f"{label} Remote={remote!r} is in account {sg_account[target]!r} but the rule's group "
                           f"is in {sg_account[sg]!r} - SG references cannot cross accounts")
        elif remote != "self" and _net(remote) is None:
            out.append(f"{label} Remote={remote!r} is not a valid CIDR / sg:<Name> / self")
    return out


@_rule("LZR-031", "error", "spec", "NetworkACLs/ACLRules are reserved tables - ACL support is not implemented")
def r_sgacl_reserved(spec):
    m = spec.get("11_SGACL", {})
    out = []
    for t in ("NetworkACLs", "ACLRules"):
        n = len(m.get(t) or [])
        if n:
            out.append(f"11_SGACL: {t} has {n} enabled row(s) but network-ACL support is not implemented "
                       "(tables are reserved; see terraform/modules/secgroups/README.md)")
    return out


_PLACEHOLDER_PREFIXES = ("replace_with", "replace-with", "tbd", "to be confirmed", "xxx")
# The VPN PSK is the ONE sanctioned placeholder: LZR-027 demands it there
# (a literal secret would be worse), and lzctl preflight/apply blocks a
# placeholder psk before it can become a live tunnel key.
_PLACEHOLDER_EXEMPT = {("10_VPN", "Connections", "PSK")}


def _walk_strings(node, sheet, table, path=""):
    """(path, column, value) for every string leaf under a sheet table."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _walk_strings(v, sheet, table, f"{path}.{k}" if path else str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            label = None
            if isinstance(v, dict):
                label = v.get("Name") or v.get("VPCName") or v.get("UserName") or v.get("Key")
            yield from _walk_strings(v, sheet, table, f"{path}[{label or i}]")
    elif isinstance(node, str):
        yield path, path.rsplit(".", 1)[-1], node


def placeholder_findings(spec) -> list:
    """Every unresolved placeholder in a spec, structured.

    Public because the app renders these as a to-do list with deep links,
    and app and CLI must never disagree about what counts as a placeholder.
    """
    out = []
    for sheet, tables in (spec or {}).items():
        if not isinstance(tables, dict):
            continue
        for table, node in tables.items():
            for path, column, value in _walk_strings(node, sheet, table, table):
                if (sheet, table, column) in _PLACEHOLDER_EXEMPT:
                    continue
                v = value.strip().lower()
                # SUBSTRING, not prefix: "acme-lz-REPLACE_WITH_SUFFIX" is as
                # unresolved as a bare sentinel, and prefix matching let those
                # reach build.
                if any(t in v for t in _PLACEHOLDER_PREFIXES) or (
                        v.startswith("<") and v.endswith(">")):
                    out.append({"sheet": sheet, "table": table, "column": column,
                                "path": f"{sheet}.{path}", "value": value})
    return out


@_rule("LZR-032", "error", "spec",
       "No unresolved placeholder may survive into a buildable spec")
def r_unresolved_placeholders(spec):
    """A `REPLACE_WITH_...` sentinel is how the intake flow records a value
    nobody has supplied yet. It must never reach build: the generated tfvars
    would carry it into Terraform, where it either fails at the API with an
    opaque error or - worse - is accepted as a real value.

    `lzctl assess` cannot catch these: it classifies only what the
    QUESTIONNAIRE left blank, so a fully answered questionnaire yields zero
    OPEN items while the spec still needs facts no question asked for. This
    rule is that gap's gate.
    """
    return [f"{f['path']} = {f['value']!r} is an unresolved placeholder - "
            "supply the real value (the app's spec editor is the intended "
            f"way), or set the field to null and declare it with `lzctl gap "
            f"add --field {f['path']}`. Registering a gap does NOT make a "
            "placeholder acceptable: null is how this spec spells 'not known "
            "yet'; it must not reach build"
            for f in placeholder_findings(spec)]


@_rule("LZR-033", "error", "spec",
       "Reserved security toggles deploy nothing - HSS/DBSS must stay FALSE")
def r_reserved_security_toggles(spec):
    """`enable_hss` / `enable_dbss` are wired from the sheet to the security
    module's variables, but no resource consumes them: turning them on
    deploys NOTHING while reading as a delivered control in the spec, the
    generated tfvars, and any document built from them.

    Record the intent to adopt HSS/DBSS as a decision or a follow-up, not as
    a spec value that silently does nothing. Remove this rule when the
    module actually implements them.
    """
    s = (spec.get("07_Security") or {}).get("Settings") or {}
    out = []
    for field, service in (("enable_hss", "Host Security Service"),
                           ("enable_dbss", "Database Security Service")):
        if _truthy(s.get(field)):
            out.append(f"07_Security: Settings.{field}=TRUE but {service} is NOT "
                       "implemented in terraform/modules/security - the flag deploys "
                       "nothing. Set it FALSE and record the requirement as a "
                       "decision/follow-up instead of a value that reads as delivered")
    return out


@_rule("LZR-015b", "warn", "spec", "Account emails should be well-formed")
def r_email_format(spec):
    m1 = spec.get("01_Foundation", {})
    out = []
    for t in ("CoreAccounts", "WorkloadAccounts"):
        for a in (m1.get(t) or []):
            em = str(a.get("Email") or "").strip()
            if em and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", em):
                out.append(f"01_Foundation: {t}[{a.get('Name')}] Email={em!r} does not look like an email address")
    return out


# ────────────────────────────────────────────────────────────────────────────
# Tree rules (executable against a generated envs tree / modules dir)
# ────────────────────────────────────────────────────────────────────────────

_SKIP_FLAGS = ("skip_requesting_account_id", "skip_s3_checksum", "skip_region_validation",
               "skip_credentials_validation", "skip_metadata_api_check")


@_rule("LZR-004", "error", "tree", "OBS S3 backend blocks must set all five skip_* flags")
def r_backend_flags(envs_dir: Path, modules_dir: Path):
    out = []
    for env in sorted(p for p in envs_dir.iterdir() if p.is_dir()):
        texts = []
        for tf in env.glob("*.tf"):
            texts.append(tf.read_text(encoding="utf-8"))
        blob = "\n".join(texts)
        if 'backend "s3"' not in blob:
            continue  # local backend (00-bootstrap)
        missing = [f for f in _SKIP_FLAGS if f not in blob]
        if missing:
            out.append(f"{env.name}: backend \"s3\" is missing {', '.join(missing)} "
                       "(init fails silently without all five)")
    return out


@_rule("LZR-002", "error", "tree", "SCP documents must use v5 syntax (no \"Version\": \"2012-10-17\")")
def r_scp_v5(envs_dir: Path, modules_dir: Path):
    out = []
    roots = [d for d in (modules_dir, envs_dir) if d and d.exists()]
    for root in roots:
        for p in root.rglob("*"):
            if p.suffix not in (".tf", ".json") or not p.is_file():
                continue
            if ".terraform" in p.parts:
                continue
            try:
                text = p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if re.search(r'"Version"\s*:\s*"2012-10-17"', text):
                out.append(f"{p.relative_to(root)}: contains a v2012 IAM policy Version - "
                           "Huawei SCPs require \"5.0\" and service:resourceType:action grammar")
    return out


@_rule("LZR-009", "warn", "tree", "OBS network-perimeter enforcement requires an OBS VPCEP in every spoke first")
def r_perimeter_enforce(envs_dir: Path, modules_dir: Path):
    import json as _json
    out = []
    for env in sorted(p for p in envs_dir.iterdir() if p.is_dir()):
        tv = env / "terraform.tfvars.json"
        if not tv.exists():
            continue
        try:
            data = _json.loads(tv.read_text(encoding="utf-8"))
        except ValueError:
            continue
        for k, v in data.items():
            if re.search(r"perimeter", k, re.I) and re.search(r"enforce|enabled", k, re.I) and v is True:
                out.append(f"{env.name}: {k}=true - confirm every spoke VPC already has its OBS VPC "
                           "endpoint, or the org locks itself out of its own state bucket")
    return out


# ────────────────────────────────────────────────────────────────────────────
# Registry-only entries (enforced elsewhere; listed so the registry is complete)
# ────────────────────────────────────────────────────────────────────────────

_doc("LZR-001", "error", "runtime", "CTS org tracker region is hard-coded in the module, not a variable",
     "terraform/modules/compliance-audit design")
_doc("LZR-005", "error", "runtime", "TF >= 1.11 needs AWS_REQUEST/RESPONSE_CHECKSUM_* = when_required",
     "runner preflight (lzctl) + README")
_doc("LZR-006", "error", "runtime", "OBS / v5-IAM / org-RMS cross-account work needs the assume_role block",
     "build_envs provider emitters (mode chosen per env)")
_doc("LZR-007", "error", "runtime", "No native state locking: single apply + state-pull backup first",
     "runner (lzctl apply) + CI concurrency groups")
_doc("LZR-008", "error", "runtime", "Remote-state producer env must be applied before its consumers",
     "lzctl deps (build) + lzctl check deps (verify)")
_doc("LZR-010", "error", "runtime", "Mandatory-tags SCP lists only tag-in-request create APIs",
     "terraform/modules/perimeter curated action list")
_doc("LZR-012", "error", "runtime", "VPN gateway eip1/eip2 are create-time-only (change = replacement, new IPs)",
     "plan triage protected-type escalation")
_doc("LZR-013", "error", "runtime", "No ER static routes to VPN attachments (ER.04006105)",
     "terraform/modules/vpn design (assoc/propagation only)")
_doc("LZR-015", "error", "runtime", "Account names 6-32 chars; unique root emails",
     "build_envs.validate()")
_doc("LZR-016", "error", "runtime", "OU depth <= 2; no parent cycles",
     "build_envs.validate()")
_doc("LZR-017", "error", "runtime", "Conformance template keys / SCP service codes are tenant-dependent",
     "documented only - no live tenant check exists yet (backlog)")
_doc("LZR-018", "warn", "runtime", "Known transient apply errors retry once (LTS.2101, EP propagation, agency 403)",
     "runner retry policy + cookbook")
_doc("LZR-019", "warn", "runtime", "Known benign drift: resolver endpoint IP order; obs_dir_prefix_name",
     "tools/plan_triage.py benign rules")
_doc("LZR-020", "error", "runtime", "LTS converge: admin-local sources transfer directly, never converge",
     "build_envs logconverge emitter")
_doc("LZR-021", "error", "runtime", "Provider ~> 1.87, Terraform >= 1.6.3",
     "versions.tf pins + lock files")


# ────────────────────────────────────────────────────────────────────────────
# Runners
# ────────────────────────────────────────────────────────────────────────────

def _unset(v) -> bool:
    """A value nobody has supplied: absent, null, or blank."""
    return v is None or (isinstance(v, str) and not v.strip())


@_rule("LZR-034", "error", "spec",
       "Every unset required value is either supplied or declared as a gap")
def r_undeclared_unknowns(spec):
    """`null` is the sanctioned way to say "not known yet" - but only once
    somebody has been asked. An unset required field with no OPEN decision
    naming it is an unknown nobody is tracking, and it reaches build as a
    silently missing value.

    This is what makes step 5's "0 errors" reachable while real gaps remain:
    declare the gap and the field stops being an error, while `lzctl build`
    still refuses until the decision carries a resolution.
    """
    ctx = decisions_context()
    if not ctx["loaded"]:
        return []                      # no decisions file: nothing to join to
    from . import specpath
    out = []
    for path in specpath.required_scalars():
        sheet, table, field = path.split(".", 2)
        node = (spec.get(sheet) or {}).get(table)
        if not isinstance(node, dict) or field not in node:
            continue
        if not _unset(node.get(field)):
            continue
        if path in ctx["declared"]:
            continue
        out.append(f"{sheet}: {table}.{field} is unset and no OPEN decision "
                   f"tracks it - supply the value, or record who owes it with "
                   f"`lzctl gap add --field {path} --question \"...\"`")
    return out


@_rule("LZR-035", "error", "spec",
       "An answered question's target must not be left empty")
def r_dropped_answers(spec):
    """The customer answered; the spec says nothing. Emptying a table is the
    cheapest way to make a validator go quiet, so the one thing that must
    never validate clean is an ANSWERED decision whose target holds nothing.

    Exception: a target some OPEN decision also declares. A prose answer can
    settle intent ("centralized egress via the hub") without containing the
    rows the table needs; the sanctioned move is `lzctl gap add` on the
    concrete target, which is visible in review and blocks build until
    resolved. Silencing this rule therefore still costs an auditable, build-
    blocking artifact - silent emptying stays an error.
    """
    ctx = decisions_context()
    if not ctx["loaded"]:
        return []
    declared = ctx["declared"]

    def _covered(path) -> bool:
        """An OPEN declaration on the path, its enclosing table, or one of
        the table's columns - each means somebody is on record as owing it."""
        return any(d == path or d.startswith(path + ".") or
                   path.startswith(d + ".") for d in declared)

    def _touched(sheet_name) -> bool:
        """Has anything on this sheet been interpreted yet?

        On a neutral draft NOTHING is populated, so every answered target is
        empty and this rule would fire on all of them - noise that buries the
        findings a reader can act on. The failure worth catching is SELECTIVE:
        a sheet somebody filled in, with one answered table emptied out.
        """
        for tbl in (spec.get(sheet_name) or {}).values():
            if isinstance(tbl, list) and tbl:
                return True
            if isinstance(tbl, dict) and any(not _unset(v) for v in tbl.values()):
                return True
        return False

    out = []
    for path, ref in sorted(ctx["answered"].items()):
        parts = path.split(".")
        if len(parts) < 2:
            continue
        sheet, table = parts[0], parts[1]
        if not _touched(sheet) or _covered(path):
            continue
        node = (spec.get(sheet) or {}).get(table)
        if node is None:
            continue
        if len(parts) == 2:
            if isinstance(node, list) and not node:
                out.append(f"{sheet}: {table} is empty, but decision {ref} is "
                           f"ANSWERED - the answer was dropped. Fill the rows, "
                           f"or, if the answer settles intent but not the "
                           f"values, declare them owed: `lzctl gap add --field "
                           f"{path} --question \"...\"`")
        elif isinstance(node, dict) and _unset(node.get(parts[2])):
            out.append(f"{sheet}: {table}.{parts[2]} is unset, but decision "
                       f"{ref} is ANSWERED - the answer was dropped. Fill it, "
                       f"or, if the answer settles intent but not the value, "
                       f"declare it owed: `lzctl gap add --field {path} "
                       f"--question \"...\"`")
    return out


@_rule("LZR-036", "error", "spec",
       "An enabled network plane must define at least one VPC")
def r_enabled_plane_is_empty(spec):
    """enable_hub/enable_spoke are the switches the builders read. Leaving a
    plane switched on with no VPCs generates an env that deploys nothing,
    which looks identical to a clean run."""
    n = spec.get("05_Network") or {}
    st = n.get("Settings") or {}
    out = []
    for flag, table in (("enable_hub", "HubVPCs"), ("enable_spoke", "SpokeVPCs")):
        v = st.get(flag)
        on = v is True or (isinstance(v, str) and v.strip().lower() in ("true", "1", "yes", "y"))
        if on and not (n.get(table) or []):
            out.append(f"05_Network: {flag} is on but {table} is empty - "
                       f"the env would deploy nothing. Add the VPCs, or turn "
                       f"{flag} off deliberately")
    return out

# Decisions context for the rules that need to know what has been DECLARED.
# Set by check_spec() for the duration of one run; empty means "no decisions
# file", in which case those rules stay silent rather than guess.
_CTX = {"declared": frozenset(), "answered": {}, "loaded": False}


def set_decisions_context(declared=None, answered=None, loaded=False):
    _CTX["declared"] = frozenset(declared or ())
    _CTX["answered"] = dict(answered or {})
    _CTX["loaded"] = bool(loaded)


def decisions_context() -> dict:
    return dict(_CTX)


def declared_targets(decisions_doc: dict) -> set:
    """Normalized field paths an OPEN decision already tracks.

    Both original questionnaire OPENs and agent-registered gaps count: each
    is a value somebody has been asked for. Unparseable targets are skipped
    - they declare nothing a machine can join to a field.
    """
    from . import specpath
    out = set()
    for item in (decisions_doc or {}).get("items", []):
        if item.get("state") != "OPEN":
            continue
        tg = item.get("targets") or []
        for t in ([tg] if isinstance(tg, str) else tg):
            for one in str(t).replace(" and ", ",").split(","):
                one = one.strip()
                if not one:
                    continue
                try:
                    out.add(specpath.normalize(one))
                except Exception:
                    continue
    return out


def answered_targets(decisions_doc: dict) -> dict:
    """{normalized path: ref} for ANSWERED decisions - the customer supplied
    something for these, so an empty target means the answer was dropped."""
    from . import specpath
    out = {}
    for item in (decisions_doc or {}).get("items", []):
        if item.get("state") != "ANSWERED":
            continue
        tg = item.get("targets") or []
        for t in ([tg] if isinstance(tg, str) else tg):
            for one in str(t).replace(" and ", ",").split(","):
                one = one.strip()
                if not one:
                    continue
                try:
                    out.setdefault(specpath.normalize(one), item.get("ref", "?"))
                except Exception:
                    continue
    return out


def run_spec_rules(spec: dict) -> list:
    findings = []
    for r in REGISTRY:
        if r.check != "spec" or r.fn is None:
            continue
        for msg in r.fn(spec):
            findings.append(Finding(r.rule_id, r.severity, msg))
    return findings


def run_tree_rules(envs_dir: Path, modules_dir: Path = None) -> list:
    findings = []
    for r in REGISTRY:
        if r.check != "tree" or r.fn is None:
            continue
        for msg in r.fn(envs_dir, modules_dir):
            findings.append(Finding(r.rule_id, r.severity, msg))
    return findings


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workbook", help="workbook to check (spec rules)")
    ap.add_argument("--envs-dir", help="generated envs tree to check (tree rules)")
    ap.add_argument("--modules-dir", help="modules dir for tree rules (default: <repo>/terraform/modules)")
    ap.add_argument("--list", action="store_true", help="print the full rule registry and exit")
    args = ap.parse_args()

    if args.list:
        for r in sorted(REGISTRY, key=lambda x: x.rule_id):
            how = r.check if r.fn else f"runtime -> {r.enforced_by}"
            print(f"{r.rule_id:9} {r.severity:5} {r.origin:14} [{how}] {r.title}")
        return 0

    findings = []
    if args.workbook:
        sys.path.insert(0, str(Path(__file__).parent.parent / "lz_spec"))
        from lz_spec.build_envs import parse_workbook
        spec = parse_workbook(Path(args.workbook))
        findings += run_spec_rules(spec)
    if args.envs_dir:
        envs = Path(args.envs_dir)
        modules = Path(args.modules_dir) if args.modules_dir else \
            Path(__file__).resolve().parents[2] / "terraform" / "modules"
        findings += run_tree_rules(envs, modules)

    errors = [f for f in findings if f.severity == "error"]
    for f in findings:
        print(str(f))
    print(f"rules: {len(findings)} finding(s), {len(errors)} error(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
