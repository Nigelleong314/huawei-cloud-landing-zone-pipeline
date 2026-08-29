"""P4 gates: monthly cost estimate (pay-per-use x 720 h).

Math, unpriced handling, destroyed-billable note, and the default rate card.
Run: py tests/test_cost.py
"""

import sys
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PKG / "tools"))
import plan_triage

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}  {str(detail)[:300]}")
        FAILED.append(name)


def rc(rtype, actions, after=None):
    return {"address": f"m.{rtype}.x", "type": rtype,
            "change": {"actions": actions, "before": {}, "after": after or {},
                       "after_unknown": {}}}


PLAN = {"resource_changes": [
    rc("huaweicloud_compute_instance", ["create"],
       {"flavor_name": "s7n.large.4", "system_disk_size": 127, "system_disk_type": "GPSSD"}),
    rc("huaweicloud_compute_instance", ["create"], {"flavor_name": "c9.xlarge.4"}),
    rc("huaweicloud_evs_volume", ["create"], {"volume_type": "SSD", "size": 1024}),
    rc("huaweicloud_vpc_eip", ["create"], {"bandwidth": [{"size": 5}]}),
    rc("huaweicloud_cbr_vault", ["create"], {"size": 1300}),
    rc("huaweicloud_natv3_gateway", ["delete"], {}),
    rc("huaweicloud_vpc_route", ["create"], {}),          # non-billable
]}

PRICING = {"currency": "USD", "hours_per_month": 720, "rates": {
    "ecs.s7n.large.4": 0.10,     # -> 72.00 / month
    "evs.GPSSD": 0.10,           # 127 GB -> 12.70
    "evs.SSD": 0.12,             # 1024 GB -> 122.88
    "cbr.backup": 0.05,          # 1300 GB -> 65.00
    "eip.bandwidth": None,       # unpriced (null)
    # ecs.c9.xlarge.4 absent     # unpriced (missing)
}}

print("== cost math ==")
c = plan_triage.cost_summary(PLAN, PRICING)
check("total = 72 + 12.70 + 122.88 + 65", c["total_known"] == 272.58, c["total_known"])
check("two unpriced items", c["unpriced"] == 2, c)
check("destroyed billable counted", c["destroyed_billables"] == 1, c)
check("non-billable ignored", not any("vpc_route" in i["key"] for i in c["items"]))
ecs = [i for i in c["items"] if i["key"] == "ecs.s7n.large.4"][0]
check("hourly item monthly = rate x 720", ecs["monthly"] == 72.0, ecs)
vault = [i for i in c["items"] if i["key"] == "cbr.backup"][0]
check("GB-month item = rate x GB", vault["monthly"] == 65.0, vault)

print("== report text ==")
text = plan_triage.cost_report("06-test", PLAN, PRICING)
check("subtotal line present", "known subtotal: USD 272.58/month" in text, text)
check("unpriced marked", "RATE NOT SET" in text, text)
check("destroy note present", "destroyed (cost reduction)" in text, text)
check("calculator link present", "pricing/calculator" in text, text)

print("== default rate card ==")
card = plan_triage.load_pricing(None)
check("card loads from tools/pricing", card.get("region") == "ap-southeast-3", card.get("region"))
check("pilot flavors pre-keyed", "ecs.s7n.large.4" in card["rates"] and "ecs.c9.xlarge.4" in card["rates"])
c2 = plan_triage.cost_summary(PLAN, card)
check("null rates -> everything unpriced, zero total", c2["total_known"] == 0 and c2["unpriced"] >= 5, c2)

print("== empty plan ==")
check("no billables -> empty report", plan_triage.cost_report("x", {"resource_changes": []}, PRICING) == "")

print()
if FAILED:
    print(f"FAILED: {len(FAILED)} -> {FAILED}")
    sys.exit(1)
print("all cost tests passed")
