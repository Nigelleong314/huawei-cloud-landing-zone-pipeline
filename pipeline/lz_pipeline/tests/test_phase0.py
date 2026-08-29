"""Phase 0 unit tests: rules registry, depsgraph, plan triage.

Dependency-free (no pytest). Run:  py tests/test_phase0.py
All fixtures deliberately use NON-the customer names/CIDRs (example, 10.77.x) so a
pass here demonstrates the checks are generic, not tuned to one customer.
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))          # lz_spec
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

import rules
import depsgraph
import plan_triage

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}  {detail}")
        FAILED.append(name)


def ids(findings):
    return sorted({f.rule_id for f in findings})


# ────────────────────────────────────────────────────────────────────────────
print("== rules: clean synthetic spec produces no findings ==")
GOOD = {
    "01_Foundation": {
        "CoreAccounts": [{"Name": "EXAMPLE-Log-Archive", "Email": "log@example.com"}],
        "WorkloadAccounts": [{"Name": "EXAMPLE-Workload-A", "Email": "wla@example.com"}],
        "TagPolicies": [{"Name": "tp-env", "TagKey": "env", "TagValue": "prd,dev"}],
    },
    "05_Network": {
        "Settings": {"spoke_private_supernet": "10.77.0.0/16"},
        "HubVPCs": [{"VPCName": "example-hub-vpc-01", "CIDR": "10.77.0.0/22"}],
        "HubSubnets": [
            {"VPCName": "example-hub-vpc-01", "Name": "example-hub-sub-a", "CIDR": "10.77.0.0/24"},
            {"VPCName": "example-hub-vpc-01", "Name": "example-hub-sub-b", "CIDR": "10.77.1.0/24"},
        ],
        "SpokeVPCs": [{"AccountName": "EXAMPLE-Workload-A", "VPCName": "example-spoke-vpc-01", "CIDR": "10.77.4.0/22"}],
        "SpokeSubnets": [{"VPCName": "example-spoke-vpc-01", "Name": "example-spoke-sub-a", "CIDR": "10.77.4.0/25"}],
    },
    "08_DNS": {
        "ResolverEndpoints": [{"Name": "in-ep", "Direction": "inbound", "VPC": "example-hub-vpc-01"}],
        "ResolverRules": [{"Name": "corp", "VPCs": "example-hub-vpc-01,example-spoke-vpc-01"}],
        "PrivateZones": [{"Name": "corp.example", "VPCs": "example-hub-vpc-01"}],
    },
    "09_CFW": {
        "AddressGroups": [{"Name": "ag-app", "Members": "10.77.4.0/24,10.77.5.0/24"}],
        "DomainGroups": [{"Name": "dg-vendor", "Domains": "*.vendor.example"}],
        "ServiceGroups": [{"Name": "sg-web", "Members": "tcp/any/443"}],
        "ACLRules": [
            {"Name": "r1", "Kind": "vpc", "Action": "allow", "Source": "addrgroup:ag-app",
             "Destination": "10.77.0.10/32", "Service": "tcp/any/443", "Status": "enable"},
            {"Name": "r2", "Kind": "nat", "Action": "allow", "Source": "addrgroup:ag-app",
             "Destination": "domaingroup:dg-vendor", "Service": "svcgroup:sg-web",
             "Status": "enable", "Direction": "outbound"},
        ],
    },
    "10_VPN": {"Connections": [{"Name": "c1", "PSK": None}]},
}
f = rules.run_spec_rules(GOOD)
check("clean spec -> 0 findings", not f, ids(f))

# ────────────────────────────────────────────────────────────────────────────
print("== rules: each rule fires on its bad fixture ==")
import copy

def mutate(path_fn):
    bad = copy.deepcopy(GOOD)
    path_fn(bad)
    return rules.run_spec_rules(bad)

r = mutate(lambda s: s["05_Network"]["HubVPCs"].__setitem__(0, {"VPCName": "v", "CIDR": "10.77.0.5/22"}))
check("LZR-022 host bits", "LZR-022" in ids(r), ids(r))

r = mutate(lambda s: s["05_Network"]["HubSubnets"].__setitem__(0, {"VPCName": "example-hub-vpc-01", "Name": "x", "CIDR": "10.88.0.0/24"}))
check("LZR-023 subnet outside vpc", "LZR-023" in ids(r), ids(r))

r = mutate(lambda s: s["05_Network"]["SpokeVPCs"].__setitem__(0, {"AccountName": "A", "VPCName": "sp", "CIDR": "10.77.1.0/24"}))
check("LZR-024 vpc overlap", "LZR-024" in ids(r), ids(r))

r = mutate(lambda s: s["05_Network"]["HubSubnets"].append({"VPCName": "example-hub-vpc-01", "Name": "dup", "CIDR": "10.77.0.128/25"}))
check("LZR-025 subnet overlap", "LZR-025" in ids(r), ids(r))

r = mutate(lambda s: s["05_Network"]["SpokeVPCs"].__setitem__(0, {"AccountName": "A", "VPCName": "sp", "CIDR": "10.99.0.0/22"}))
check("LZR-026 spoke outside supernet", "LZR-026" in ids(r), ids(r))

r = mutate(lambda s: s["08_DNS"]["ResolverRules"].__setitem__(0, {"Name": "corp", "VPCs": "example-spoke-vpc-01"}))
check("LZR-014 rule missing resolver vpc", "LZR-014" in ids(r), ids(r))

r = mutate(lambda s: s["08_DNS"]["PrivateZones"].__setitem__(0, {"Name": "z", "VPCs": "example-spoke-vpc-01"}))
check("LZR-014b zone missing resolver vpc", "LZR-014b" in ids(r), ids(r))

r = mutate(lambda s: s["09_CFW"]["AddressGroups"].__setitem__(0, {"Name": "ag-app", "Members": "10.77.4.0/24,10.77.4.128/25"}))
check("LZR-011a addrgroup overlap", "LZR-011a" in ids(r), ids(r))

r = mutate(lambda s: s["09_CFW"]["ACLRules"].append(
    {"Name": "bad-in", "Kind": "eip", "Action": "allow", "Source": "any",
     "Destination": "domaingroup:dg-vendor", "Service": "tcp/any/443"}))
check("LZR-011b inbound domaingroup", "LZR-011b" in ids(r), ids(r))

r = mutate(lambda s: s["09_CFW"]["ACLRules"].append(
    {"Name": "bad-enum", "Kind": "wan", "Action": "permit", "Service": "tcp/any/443", "Status": "on"}))
check("LZR-011c enums", "LZR-011c" in ids(r), ids(r))

r = mutate(lambda s: s["09_CFW"]["ACLRules"].append(
    {"Name": "bad-svc", "Kind": "vpc", "Action": "allow", "Service": "icmp/any/8"}))
check("LZR-011d icmp ports", "LZR-011d" in ids(r), ids(r))

r = mutate(lambda s: s["09_CFW"]["ACLRules"].append(
    {"Name": "bad-ref", "Kind": "vpc", "Action": "allow", "Source": "addrgroup:missing", "Service": "any"}))
check("LZR-011e unknown group ref", "LZR-011e" in ids(r), ids(r))

r = mutate(lambda s: s["01_Foundation"]["TagPolicies"].__setitem__(0, {"Name": "tp", "TagKey": "k", "TagValue": "web-*"}))
check("LZR-003 wildcard tag value", "LZR-003" in ids(r), ids(r))

r = mutate(lambda s: s["10_VPN"]["Connections"].__setitem__(0, {"Name": "c1", "PSK": "SuperSecret123!"}))
check("LZR-027 psk in sheet", "LZR-027" in ids(r), ids(r))

r = mutate(lambda s: s["01_Foundation"]["CoreAccounts"].__setitem__(0, {"Name": "EXAMPLE-Log-Archive", "Email": "not-an-email"}))
check("LZR-015b email format", "LZR-015b" in ids(r), ids(r))

# severity sanity: errors only from error-severity rules
bad_all = rules.run_spec_rules(GOOD)
check("severities well-formed", all(x.severity in ("error", "warn") for x in rules.run_spec_rules(GOOD) + r), "")

# ────────────────────────────────────────────────────────────────────────────
print("== rules: tree rules on synthetic env tree ==")
with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    good_env = root / "01-foundation"
    good_env.mkdir()
    (good_env / "backend.tf").write_text(
        'terraform { backend "s3" {\n'
        "  skip_requesting_account_id = true\n  skip_s3_checksum = true\n"
        "  skip_region_validation = true\n  skip_credentials_validation = true\n"
        "  skip_metadata_api_check = true\n} }\n", encoding="utf-8")
    bad_env = root / "02-finance"
    bad_env.mkdir()
    (bad_env / "backend.tf").write_text('terraform { backend "s3" { skip_s3_checksum = true } }\n', encoding="utf-8")
    (bad_env / "policy.json").write_text('{"Version": "2012-10-17", "Statement": []}\n', encoding="utf-8")
    (bad_env / "terraform.tfvars.json").write_text('{"obs_perimeter_enforce": true}\n', encoding="utf-8")
    tf = rules.run_tree_rules(root, None)
    tids = ids(tf)
    check("LZR-004 missing skip flags", "LZR-004" in tids, tids)
    check("LZR-002 v2012 policy", "LZR-002" in tids, tids)
    check("LZR-009 perimeter enforce warn", "LZR-009" in tids, tids)
    check("good env not flagged", not any("01-foundation" in x.message for x in tf),
          [str(x) for x in tf if "01-foundation" in x.message])

# ────────────────────────────────────────────────────────────────────────────
print("== depsgraph: synthetic tree ==")
with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    for name, tf in {
        "01-base": "",
        "02-mid": 'data "terraform_remote_state" "base" {}\n'
                  'variable "k" { default = "envs/01-base/terraform.tfstate" }\n',
        "03-top": 'data "terraform_remote_state" "mid" {}\n'
                  'variable "k" { default = "envs/02-mid/terraform.tfstate" }\n',
    }.items():
        d = root / name
        d.mkdir()
        (d / "main.tf").write_text(tf, encoding="utf-8")
    g = depsgraph.scan(root)
    check("edges resolved via variable defaults",
          g["02-mid"]["consumes"] == ["01-base"] and g["03-top"]["consumes"] == ["02-mid"], g)
    check("clean ordering passes", depsgraph.check(g) == [], depsgraph.check(g))
    order = depsgraph.apply_order(g)
    check("topo order", order == ["01-base", "02-mid", "03-top"], order)
    # inversion: an early env consuming a later one must fail LZR-008
    (root / "01-base" / "main.tf").write_text(
        'data "terraform_remote_state" "x" {}\n'
        'variable "k" { default = "envs/03-top/terraform.tfstate" }\n', encoding="utf-8")
    errs = depsgraph.check(depsgraph.scan(root))
    check("LZR-008 inversion detected", any("does not sort before" in e for e in errs), errs)

# ────────────────────────────────────────────────────────────────────────────
print("== plan triage ==")
def plan(*rcs):
    return {"resource_changes": list(rcs)}

def rc(addr, rtype, actions, before=None, after=None, unknown=None):
    return {"address": addr, "type": rtype,
            "change": {"actions": actions, "before": before or {}, "after": after or {},
                       "after_unknown": unknown or {}}}

b = plan_triage.triage(plan())
check("empty plan", sum(len(v) for v in b.values()) == 0, b)

b = plan_triage.triage(plan(
    rc("module.dns.huaweicloud_dns_endpoint.in", "huaweicloud_dns_endpoint", ["update"],
       before={"ip_addresses": [{"ip": "10.9.0.5"}, {"ip": "10.9.0.6"}]},
       after={"ip_addresses": [{"ip": "10.9.0.6"}, {"ip": "10.9.0.5"}]}),
    rc("module.logs.huaweicloud_lts_transfer.t", "huaweicloud_lts_transfer", ["update"],
       before={"log_transfer_info": [{"log_transfer_detail": [{"obs_dir_prefix_name": "a/"}]}]},
       after={"log_transfer_info": [{"log_transfer_detail": [{"obs_dir_prefix_name": "a"}]}]}),
))
check("both LZR-019 drifts classify benign", len(b["benign"]) == 2 and not b["update"], b)

b = plan_triage.triage(plan(
    rc("module.dns.huaweicloud_dns_endpoint.in", "huaweicloud_dns_endpoint", ["update"],
       before={"ip_addresses": [{"ip": "10.9.0.5"}], "name": "ep-a"},
       after={"ip_addresses": [{"ip": "10.9.0.6"}], "name": "ep-b"})))
check("mixed attr change NOT benign", len(b["update"]) == 1 and not b["benign"], b)

b = plan_triage.triage(plan(
    rc("module.x.huaweicloud_vpc.v", "huaweicloud_vpc", ["delete", "create"]),
    rc("module.x.huaweicloud_vpn_gateway.g", "huaweicloud_vpn_gateway", ["delete", "create"]),
    rc("module.x.huaweicloud_vpc_route.r", "huaweicloud_vpc_route", ["create"]),
))
check("replace = destructive", len(b["destructive"]) == 2 and len(b["create"]) == 1, b)
check("vpn gateway flagged protected", any(c["protected"] for c in b["destructive"] if c["type"] == "huaweicloud_vpn_gateway"), b)

# exit-code semantics through main() classification
check("no-op filtered", plan_triage.classify_change(rc("a", "t", ["no-op"]), [], []) is None, "")

# ────────────────────────────────────────────────────────────────────────────
print()
if FAILED:
    print(f"FAILED: {len(FAILED)} -> {FAILED}")
    sys.exit(1)
print("all phase-0 tests passed")
