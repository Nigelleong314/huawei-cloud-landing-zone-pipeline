"""Generate the IP-management workbook (block ledger + subnets + hosts) from
the 05-network tfvars of any envs tree. Customer-agnostic.

Usage:
    py tools/gen_ipam.py --envs-dir envs --out ipam.xlsx \
        [--title "Example Landing Zone - IP Management"] [--block-prefix 22] \
        [--reserve "10.42.8.0/22=CFW inspection block; never assign"] \
        [--hosts hosts.csv] [--states-dir states]

--states-dir (a folder of state-<env>.json pulls, as for gen_checklist) makes the
VPC notes and subnet purposes describe what is actually deployed in each VPC and
subnet; without it they carry only the hub/spoke role.

--reserve is repeatable for blocks held outside Terraform (for example a VPC
planned but not provisioned). The firewall's ER-mode inspection range is read
from 05-network (inspection_cidr_reservation) and reserved automatically. --hosts seeds the Hosts sheet from a
CSV (ip,subnet,resource,env,notes); otherwise the sheet ships as an empty
register with headers.
"""

import argparse
import csv
import ipaddress
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import openpyxl
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

sys.path.insert(0, str(Path(__file__).parent))
from envtree import BOX, HDR_FILL, HDR_FONT, WRAP, tfvars

NOTE_FONT = Font(size=9, italic=True, color="595959")
FILL = {"Free": PatternFill("solid", fgColor="E2EFDA"),
        "Allocated": PatternFill("solid", fgColor="FCE4EC"),
        "Reserved": PatternFill("solid", fgColor="FFF2CC")}


def header(ws, row, cols):
    for i, c in enumerate(cols, 1):
        cell = ws.cell(row=row, column=i, value=c)
        cell.font, cell.fill, cell.border = HDR_FONT, HDR_FILL, BOX
    ws.freeze_panes = ws.cell(row=row + 1, column=1)


def fit(ws, widths):
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w


def collect(n5: dict):
    """(vpcs, subnets) from 05-network tfvars: hub_vpcs + spokes."""
    vpcs, subnets = [], []
    hub = n5.get("hub_account", "")
    for name, v in (n5.get("hub_vpcs") or {}).items():
        role = next((HUB_ROLE[t] for t in name.split("-") if t in HUB_ROLE), "")
        vpcs.append((name, v.get("cidr"), "Hub VPC" + (f" ({hub})" if hub else "") + (f" - {role}" if role else "")))
        for s in v.get("subnets", []):
            subnets.append((name, s.get("name"), s.get("cidr")))
    for name, sp in (n5.get("spokes") or {}).items():
        acct = sp.get("account", "")
        att = "" if sp.get("er_attach", True) else ", detached from the ER"
        vpcs.append((name, sp.get("vpc_cidr"), f"Spoke VPC ({acct}){att}"))
        for s in sp.get("subnets", []):
            subnets.append((name, s.get("name"), s.get("cidr")))
    return vpcs, subnets


# Resource types worth naming in a remark, and the label used for them.
KIND = {
    "huaweicloud_compute_instance": "ECS VM",
    "huaweicloud_er_vpc_attachment": "ER attachment",
    "huaweicloud_dns_endpoint": "DNS resolver endpoint",
    "huaweicloud_natv3_gateway": "NAT gateway",
    "huaweicloud_nat_gateway": "NAT gateway",
    "huaweicloud_nat_private_gateway": "private NAT gateway",
    "huaweicloud_vpn_gateway": "VPN gateway",
    "huaweicloud_elb_loadbalancer": "load balancer",
    "huaweicloud_lb_loadbalancer": "load balancer",
    "huaweicloud_vpcep_endpoint": "VPC endpoint",
    "huaweicloud_dc_virtual_gateway": "Direct Connect gateway",
    "huaweicloud_rds_instance": "RDS instance",
    "huaweicloud_cce_cluster": "CCE cluster",
}
# Subnet-name tokens of the naming convention, and the use they imply.
TIER = {"att": "the ER attachment", "nat": "NAT gateways", "elb": "load balancers",
        "vpn": "the VPN gateway", "dc": "Direct Connect", "dns": "DNS resolver endpoints",
        "web": "the web tier", "compute": "the application tier", "data": "the database tier"}
HUB_ROLE = {"dmz": "internet edge (DMZ)", "access": "hybrid access", "ss": "shared services"}


def _strings(o):
    if isinstance(o, dict):
        for v in o.values():
            yield from _strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from _strings(v)
    elif isinstance(o, str):
        yield o


def inventory(states_dir: Path):
    """Per subnet name: [(label, resource name)]; per VPC name: Counter of VPC-level features.

    A resource belongs to the subnet (else the VPC) whose ID appears anywhere in its
    attributes; the IDs come from the vpc and vpc_subnet resources in the same states.
    """
    states = [json.loads(f.read_text(encoding="utf-8")) for f in sorted(states_dir.glob("state-*.json"))]
    managed = [(r["type"], i["attributes"]) for st in states for r in st.get("resources", [])
               if r.get("mode") == "managed" for i in r.get("instances", [])]
    vpc_ids = {a["id"]: a["name"] for t, a in managed if t == "huaweicloud_vpc"}
    sub_ids = {}
    for t, a in managed:
        if t == "huaweicloud_vpc_subnet":
            for k in ("id", "subnet_id"):
                if a.get(k):
                    sub_ids[a[k]] = a["name"]
    by_subnet, by_vpc = defaultdict(list), defaultdict(Counter)
    for t, a in managed:
        if t in ("huaweicloud_vpc", "huaweicloud_vpc_subnet"):
            continue
        refs = set(_strings(a))
        subnets = {sub_ids[x] for x in refs if x in sub_ids}
        if t in KIND:
            label = KIND[t]
            if t == "huaweicloud_dns_endpoint" and a.get("direction"):
                label = f"{a['direction']} {label}"
            tags = a.get("tags") or {}
            workload = ", ".join(v for v in (tags.get("project"), tags.get("env")) if v) \
                if t == "huaweicloud_compute_instance" else ""
            for n in sorted(subnets):
                by_subnet[n].append((label, a.get("name", ""), KIND[t], workload))
        elif not subnets:
            for v in {vpc_ids[x] for x in refs if x in vpc_ids}:
                if t == "huaweicloud_vpc_flow_log":
                    by_vpc[v]["flow log"] += 1
                elif t == "huaweicloud_dns_resolver_rule_associate":
                    by_vpc[v]["DNS forwarding rule"] += 1
    return by_subnet, by_vpc


def _tier(name: str) -> str:
    for tok in reversed((name or "").split("-")):
        if tok in TIER:
            return TIER[tok]
    return ""


def subnet_purpose(name: str, hosted=None) -> str:
    if hosted is None:
        return "ER attachment" if "-att" in (name or "") else ""
    tier = _tier(name)
    if not hosted:
        return f"Intended for {tier}; nothing deployed yet." if tier else "Nothing deployed yet."
    items = "; ".join(f"{label} {res}".strip() for label, res, _, _ in hosted)
    if not tier or any(base.lower() in tier.lower() for _, _, base, _ in hosted):
        return f"Hosts {items}."
    return f"For {tier}. Hosts {items}."


def _count(label: str, n: int) -> str:
    return f"{n} {label}{'' if n == 1 else 's'}"


def vpc_note(kind: str, subnets: list, by_subnet: dict, features: Counter) -> str:
    hosted = Counter(label for s in subnets for label, _, _, _ in by_subnet.get(s, []))
    workloads = sorted({w for s in subnets for _, _, _, w in by_subnet.get(s, []) if w})
    idle = [s for s in subnets if not by_subnet.get(s)]
    parts = [kind + "."]
    if hosted:
        items = [_count(lb, n) + (f" ({'; '.join(workloads)})" if lb == "ECS VM" and workloads else "")
                 for lb, n in sorted(hosted.items())]
        parts.append("Hosts " + ", ".join(items) + ".")
        if idle:
            tiers = Counter(_tier(s) or "other use" for s in idle)
            parts.append(f"{len(idle)} of {len(subnets)} subnets still empty ("
                         + ", ".join(f"{n} for {t}" for t, n in sorted(tiers.items())) + ").")
    else:
        parts.append("Nothing deployed in its subnets yet.")
    for f, n in sorted(features.items()):
        parts.append("Flow log enabled." if f == "flow log" else _count(f, n)[0].upper() + _count(f, n)[1:] + " associated.")
    return " ".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--envs-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", default="Landing Zone - IP Management")
    ap.add_argument("--block-prefix", type=int, default=22)
    ap.add_argument("--supernet", help="override; default = 05-network spoke_private_supernet")
    ap.add_argument("--reserve", action="append", default=[], metavar="CIDR=note")
    ap.add_argument("--hosts", help="CSV of ip,subnet,resource,env,notes")
    ap.add_argument("--states-dir", help="folder of state-<env>.json pulls; describes what each VPC and subnet hosts")
    args = ap.parse_args()

    n5 = tfvars(Path(args.envs_dir), "05-network")
    if not n5:
        print("05-network/terraform.tfvars.json not found", file=sys.stderr)
        return 2
    supernet = ipaddress.ip_network(args.supernet or n5["spoke_private_supernet"])
    vpcs, subnets = collect(n5)
    by_subnet, by_vpc = inventory(Path(args.states_dir)) if args.states_dir else (None, None)
    vpc_subnets = defaultdict(list)
    for vpc, name, _ in subnets:
        vpc_subnets[vpc].append(name)

    reserved = {}
    for r in args.reserve:
        cidr, _, note = r.partition("=")
        reserved[ipaddress.ip_network(cidr.strip())] = note.strip()
    insp = n5.get("inspection_cidr_reservation")
    if insp:
        reserved.setdefault(ipaddress.ip_network(insp),
                            "Reserved range for CFW: east-west inspection in ER mode. Managed by the "
                            "Cloud Firewall service, not a VPC - do not assign.")
    held = {}
    for net, note in reserved.items():
        for block in supernet.subnets(new_prefix=args.block_prefix):
            if net.overlaps(block):
                held[str(block)] = note

    # map VPC allocations onto the /N carving
    alloc = {}
    for name, cidr, kind in vpcs:
        if not cidr:
            continue
        net = ipaddress.ip_network(cidr)
        for block in supernet.subnets(new_prefix=args.block_prefix):
            if net.overlaps(block):
                note = kind if by_subnet is None else vpc_note(
                    kind, vpc_subnets[name], by_subnet, by_vpc.get(name, Counter()))
                alloc[str(block)] = (name, note)

    wb = openpyxl.Workbook()
    s = wb.active
    s.title = "Summary"
    s["A1"] = args.title
    s["A1"].font = Font(bold=True, size=14)
    n_blocks = 2 ** (args.block_prefix - supernet.prefixlen)
    s["A2"] = (f"The {supernet} supernet is divided into {n_blocks} /{args.block_prefix} blocks. "
               "Keep the Blocks sheet updated; the summary below recalculates automatically.")
    s["A2"].font = NOTE_FONT
    last = n_blocks + 1
    rows = [
        ("Supernet", str(supernet)),
        (f"Total /{args.block_prefix} blocks", f"=COUNTA(Blocks!A2:A{last})"),
        ("Allocated", f'=COUNTIF(Blocks!D2:D{last},"Allocated")'),
        ("Reserved", f'=COUNTIF(Blocks!D2:D{last},"Reserved")'),
        ("Free blocks", f'=COUNTIF(Blocks!D2:D{last},"Free")'),
        ("Next available block", f'=INDEX(Blocks!A2:A{last},MATCH("Free",Blocks!D2:D{last},0))'),
        ("Registered host IPs", "=COUNTA(Hosts!A2:A500)"),
    ]
    for i, (k, v) in enumerate(rows, 4):
        s.cell(row=i, column=1, value=k).font = Font(bold=True)
        s.cell(row=i, column=2, value=v)
    fit(s, [24, 40])

    b = wb.create_sheet("Blocks")
    header(b, 1, [f"Block (/{args.block_prefix})", "First IP", "Last IP", "Status", "Assigned to", "Notes"])
    dv = DataValidation(type="list", formula1='"Allocated,Reserved,Free"', allow_blank=False)
    b.add_data_validation(dv)
    r = 2
    for net in supernet.subnets(new_prefix=args.block_prefix):
        cidr = str(net)
        if cidr in alloc:
            status, owner, note = "Allocated", alloc[cidr][0], alloc[cidr][1]
        elif cidr in held:
            status, owner, note = "Reserved", "", held[cidr]
        else:
            status, owner, note = "Free", "", ""
        for c, v in enumerate([cidr, str(net[0]), str(net[-1]), status, owner, note], 1):
            cell = b.cell(row=r, column=c, value=v)
            cell.border, cell.alignment = BOX, WRAP
        b.cell(row=r, column=4).fill = FILL[status]
        dv.add(b.cell(row=r, column=4))
        r += 1
    fit(b, [18, 15, 15, 12, 34, 55 if by_subnet is None else 90])

    sn = wb.create_sheet("Subnets")
    header(sn, 1, ["VPC", "Subnet", "CIDR", "Purpose", "Usable IPs", "Host IPs in use"])
    for i, (vpc, name, cidr) in enumerate(subnets, 2):
        size = (ipaddress.ip_network(cidr).num_addresses - 5) if cidr else ""
        purpose = subnet_purpose(name, None if by_subnet is None else by_subnet.get(name, []))
        vals = [vpc, name, cidr, purpose, size, f'=COUNTIF(Hosts!B2:B500,B{i})']
        for c, v in enumerate(vals, 1):
            cell = sn.cell(row=i, column=c, value=v)
            cell.border, cell.alignment = BOX, WRAP
    fit(sn, [30, 38, 18, 22 if by_subnet is None else 70, 11, 14])

    h = wb.create_sheet("Hosts")
    header(h, 1, ["IP", "Subnet", "Resource", "Environment", "Notes"])
    if args.hosts:
        with open(args.hosts, newline="", encoding="utf-8") as fh:
            for i, row in enumerate(csv.reader(fh), 2):
                for c, v in enumerate(row[:5], 1):
                    cell = h.cell(row=i, column=c, value=v)
                    cell.border, cell.alignment = BOX, WRAP
    fit(h, [16, 38, 34, 8, 45])

    wb.save(args.out)
    print(f"written: {args.out}  (blocks: {n_blocks}, allocated: {len(alloc)}, "
          f"reserved: {len(held)}, subnets: {len(subnets)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
