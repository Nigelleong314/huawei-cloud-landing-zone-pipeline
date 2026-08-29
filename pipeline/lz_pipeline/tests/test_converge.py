"""Log-converge derivation.

derive_log_converge on synthetic specs: an empty LogConverge table gets the
full LZ stream set (CTS, DNS access logs, CFW streams, one flow-log row per
VPC); a curated table is authoritative and left untouched; derivation is off
when aggregation is off; flow-log rows are gated on enable_vpc_flow_logs.

Byte-exactness of a built tree belongs to test_goldens.py (frozen fixture).

Run: py tests/test_converge.py
"""

import copy
import sys
from pathlib import Path

PKG = Path(__file__).parent.parent       # lz_pipeline
ROOT = PKG.parent
HERE = ROOT / "lz_spec"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from lz_pipeline.core.cli import derive_log_converge

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}  {str(detail)[:400]}")
        FAILED.append(name)


BASE = {
    "05_Network": {
        "Settings": {"enable_vpc_flow_logs": "TRUE", "hub_account": "HUB"},
        "CloudFirewall": {"cfw_lts_log_enable": "TRUE", "cfw_lts_log_group_name": "hub-cfw",
                          "cfw_lts_traffic_stream_name": "cfw-traffic",
                          "cfw_lts_access_stream_name": "cfw-access",
                          "cfw_lts_attack_stream_name": "cfw-attack"},
        "HubVPCs": [{"VPCName": "hub-vpc-01"}],
        "SpokeVPCs": [{"VPCName": "spoke-a-vpc", "AccountName": "ACCT-A"},
                      {"VPCName": "spoke-b-vpc", "AccountName": "ACCT-B"}],
    },
    "06_Observability": {
        "LogAggregation": {"enable_log_aggregation": "TRUE"},
        "AuditSettings": {"cts_admin_account": "SEC", "cts_log_group_name": "cts-lg",
                          "cts_log_stream_name": "cts-ls"},
    },
    "08_DNS": {
        "Settings": {"dns_account": "HUB"},
        "AccessLogs": [{"Enabled": "TRUE", "Name": "dns-log", "LTSGroup": "dns-lg",
                        "LTSStream": "dns-ls", "VPCs": "hub-vpc-01"}],
    },
}


print("== 1. empty table: full LZ stream set ==")
spec = copy.deepcopy(BASE)
derive_log_converge(spec)
rows = spec["06_Observability"]["LogConverge"]
got = [(r["Account"], r["SourceGroup"], r["SourceStream"]) for r in rows]
want = [("SEC", "cts-lg", "cts-ls"),
        ("HUB", "dns-lg", "dns-ls"),
        ("HUB", "hub-cfw", "cfw-traffic"),
        ("HUB", "hub-cfw", "cfw-access"),
        ("HUB", "hub-cfw", "cfw-attack"),
        ("HUB", "hub-vpc-01-flowlog", "hub-vpc-01-flowlog"),
        ("ACCT-A", "spoke-a-vpc-flowlog", "spoke-a-vpc-flowlog"),
        ("ACCT-B", "spoke-b-vpc-flowlog", "spoke-b-vpc-flowlog")]
check("CTS + DNS + CFW×3 + flowlog×3, in order", got == want, got)

print("== 2. idempotent / curated table is authoritative ==")
derive_log_converge(spec)
check("re-run adds nothing", len(spec["06_Observability"]["LogConverge"]) == len(want))

curated = copy.deepcopy(BASE)
curated["06_Observability"]["LogConverge"] = [
    {"Enabled": "TRUE", "Account": "HUB", "SourceGroup": "only-mine",
     "SourceStream": "only-mine", "TargetGroup": None, "Description": None}]
derive_log_converge(curated)
check("curated table untouched",
      [r["SourceGroup"] for r in curated["06_Observability"]["LogConverge"]] == ["only-mine"],
      curated["06_Observability"]["LogConverge"])

print("== 3. toggles gate the derivation ==")
off = copy.deepcopy(BASE)
off["06_Observability"]["LogAggregation"]["enable_log_aggregation"] = "FALSE"
derive_log_converge(off)
check("aggregation off derives nothing",
      not (off["06_Observability"].get("LogConverge") or []),
      off["06_Observability"].get("LogConverge"))

noflow = copy.deepcopy(BASE)
noflow["05_Network"]["Settings"]["enable_vpc_flow_logs"] = "FALSE"
derive_log_converge(noflow)
groups = [r["SourceGroup"] for r in noflow["06_Observability"]["LogConverge"]]
check("flow logs off: CTS/DNS/CFW rows only",
      groups == ["cts-lg", "dns-lg", "hub-cfw", "hub-cfw", "hub-cfw"], groups)

nocfw = copy.deepcopy(BASE)
nocfw["05_Network"]["CloudFirewall"]["cfw_lts_log_enable"] = "FALSE"
derive_log_converge(nocfw)
check("cfw logging off: no cfw rows",
      not any(r["SourceGroup"] == "hub-cfw" for r in nocfw["06_Observability"]["LogConverge"]))

print()
if FAILED:
    print(f"FAILED: {len(FAILED)} -> {FAILED}")
    sys.exit(1)
print("all converge tests passed")
