"""Phase 5 gates: profile-driven export.

  1. Feature strip: an export whose profile disables a feature must omit that
     module, and the same export with it enabled must include it. Asserted on
     the export's own output, not against a shipped snapshot - "is the shipped
     artifact current?" is a release question, and the artifact is regenerated
     by the export job rather than hand-maintained, so a spec edit must not
     fail this suite.
  2. example export: release files + runner present, secmaster kept (feature on),
     secrets stripped, no absolute/parent module paths, zero customer strings.
  3. Changelog derivation: second release with a spec change lists the delta.

Run: py tests/test_phase5.py
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

PKG = Path(__file__).parent.parent       # lz_pipeline
ROOT = PKG.parent.parent
HERE = ROOT / "pipeline" / "lz_spec"

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}  {str(detail)[:400]}")
        FAILED.append(name)


def export(profile, target, extra=None):
    return subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "lz_pipeline.export_v2",
         "--profile", str(profile), "--target", str(target)] + (extra or []),
        capture_output=True, text=True, cwd=str(ROOT))


with tempfile.TemporaryDirectory(prefix="lz-p5-") as td:
    tmp = Path(td)

    print("== 1. feature strip + compat rewrite ==")
    prof_off = tmp / "secmaster-off.json"
    prof_off.write_text(json.dumps({
        "customer": "example", "features": {"secmaster": False},
        "envs_dir": "terraform/envs-example", "docs_dir": None,
        "ir": "lz_pipeline/fixtures/example.spec.json"}), encoding="utf-8")
    tgt = tmp / "compat"
    r = export(prof_off, tgt, ["--compat"])
    check("compat export runs", r.returncode == 0, r.stderr[-300:])
    stripped = (tgt / "envs/07-security/main.tf").read_text(encoding="utf-8")
    check("secmaster stripped (feature off)", 'module "security"' not in stripped)
    check("sibling module in the same env survives the strip",
          'module "edge_protection"' in stripped)
    tf_files = [p for p in tgt.rglob("*.tf")]
    check("compat rewrite leaves no parent-relative module sources",
          not [p.relative_to(tgt).as_posix() for p in tf_files
               if re.search(r'source\s*=\s*"\.\./\.\./\.\.', p.read_text(encoding="utf-8"))])
    check("no secrets shipped",
          not [p.relative_to(tgt).as_posix() for p in tgt.rglob("secrets.auto.tfvars.json")])

    print("== 2. example export ==")
    tgt = tmp / "example"
    r = export(PKG / "profiles" / "example.json", tgt,
               ["--version", "1.0.0", "--releases-dir", str(tmp / "rel")])
    check("example export runs", r.returncode == 0, r.stderr[-300:])
    names = {p.relative_to(tgt).as_posix() for p in tgt.rglob("*") if p.is_file()}
    for want in ("VERSION", "CHANGELOG.md", "MANIFEST.txt", "runner/lzctl.py",
                 "runner/plan_triage.py", "envs/deps.json"):
        check(f"ships {want}", want in names)
    main10 = (tgt / "envs/07-security/main.tf").read_text(encoding="utf-8")
    check("secmaster kept (feature on)", 'module "security"' in main10)
    # Customer identifiers are DERIVED from every non-example profile, so
    # onboarding a customer extends this check with no regex to remember.
    forbidden = set()
    for prof in sorted((PKG / "profiles").glob("*.json")):
        cfg = json.loads(prof.read_text(encoding="utf-8"))
        ir_path = ROOT / cfg["ir"]
        if not ir_path.exists() or ir_path.name == "example.spec.json":
            continue
        sh = json.loads(ir_path.read_text(encoding="utf-8")).get("sheets", {})
        forbidden.add(str(cfg.get("customer", "")))
        for sheet, table, col in (("01_Foundation", "CoreAccounts", "Name"),
                                  ("01_Foundation", "WorkloadAccounts", "Name"),
                                  ("01_Foundation", "OrganizationalUnits", "Name"),
                                  ("02_Finance", "CostCenters", "Name"),
                                  ("05_Network", "HubVPCs", "VPCName"),
                                  ("05_Network", "SpokeVPCs", "VPCName")):
            for row in sh.get(sheet, {}).get(table, []) or []:
                forbidden.add(str(row.get(col, "")))
        sup = sh.get("05_Network", {}).get("Settings", {}).get("spoke_private_supernet")
        if sup:
            forbidden.add(sup.rsplit(".", 2)[0] + ".")   # 10.42.0.0/16 -> "10.42."
        # On-prem identifiers leak through the firewall/DNS payload, not just
        # account names: harvest group names, member CIDR prefixes (first two
        # octets), forwarder domains, and account-email domains too.
        # ponytail: three-octet prefixes, whole-RFC1918 blocks skipped — a
        # customer on a /16 that collides with a generic example shape can
        # still slip; tighten to per-member exact CIDRs if that ever happens.
        _generic = {"10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"}
        for row in sh.get("09_CFW", {}).get("AddressGroups", []) or []:
            forbidden.add(str(row.get("Name", "")))
            for m in str(row.get("Members", "")).split(","):
                m = m.strip()
                if m in _generic or m.count(".") < 3:
                    continue
                pref = ".".join(m.split(".")[:3]) + "."
                if pref in ("10.0.0.", "172.16.0.", "192.168.0."):
                    continue  # canonical private roots — generic example shapes
                forbidden.add(pref)
        for row in sh.get("09_CFW", {}).get("DomainGroups", []) or []:
            for d in str(row.get("Members", "")).split(","):
                d = d.strip().lstrip("*.")
                if "." in d:
                    forbidden.add(d)
        for row in sh.get("08_DNS", {}).get("ResolverRules", []) or []:
            forbidden.add(str(row.get("DomainName", "")).rstrip("."))
        for tbl in ("CoreAccounts", "WorkloadAccounts"):
            for row in sh.get("01_Foundation", {}).get(tbl, []) or []:
                email = str(row.get("Email", ""))
                if "@" in email:
                    forbidden.add(email.split("@", 1)[1])
    forbidden = {t.lower() for t in forbidden if len(t) >= 5}
    # Public example specs must never contain any customer-derived token —
    # this is the control that failed when lz.spec.example.json shipped with
    # live on-prem data (found 2026-08-30).
    example_specs = [PKG / "fixtures" / "example.spec.json"]
    example_specs += sorted((ROOT / "pipeline" / "lz_spec").glob("lz.spec.*.json"))
    ex_hits = []
    for p in example_specs:
        if not p.exists():
            continue
        body = p.read_text(encoding="utf-8", errors="ignore").lower()
        found = sorted(t for t in forbidden if t in body)
        if found:
            ex_hits.append(f"{p.name}: {found[:3]}")
    check("zero customer strings in example specs", not ex_hits, ex_hits)
    hits = []
    for p in tgt.rglob("*"):
        rel = p.relative_to(tgt).as_posix()
        if not (p.is_file() and rel.startswith("envs/")
                and p.suffix in (".tf", ".json", ".hcl", ".md", ".example")):
            continue
        body = p.read_text(encoding="utf-8", errors="ignore").lower()
        found = sorted(t for t in forbidden if t in body)
        if found:
            hits.append(f"{rel}: {found[:3]}")
    check(f"zero customer strings under envs/ ({len(forbidden)} identifiers checked)",
          not hits, hits)
    # The workbook is generated from schema.py text + the spec, so a customer
    # identifier in a schema description or sample row would ship here.
    wb_path = tgt / "landing-zone-spec.xlsx"
    check("artifact ships the generated Excel workbook", wb_path.exists())
    if wb_path.exists():
        import openpyxl
        cells = []
        for ws in openpyxl.load_workbook(wb_path, data_only=True).worksheets:
            for row in ws.iter_rows(values_only=True):
                for c in row:
                    if c is not None:
                        cells.append(str(c).lower())
        blob = "\n".join(cells)
        wb_hits = sorted(t for t in forbidden if t in blob)
        check("zero customer strings in the workbook", not wb_hits, wb_hits)
    man = (tgt / "MANIFEST.txt").read_text(encoding="utf-8")
    check("manifest carries version+features", "version: 1.0.0" in man and "features" in man)

    print("== 3. changelog derivation across releases ==")
    ir2 = tmp / "example-changed.spec.json"
    ir = json.loads((PKG / "fixtures" / "example.spec.json").read_text(encoding="utf-8"))
    ir["sheets"]["01_Foundation"]["WorkloadAccounts"].append(
        {"Name": "EXAMPLE-Prod-B", "Email": "cloud-prod-b@example.com", "OU": "Workloads",
         "Description": "Production workload B"})
    ir2.write_text(json.dumps(ir), encoding="utf-8")
    prof2 = tmp / "example2-profile.json"
    prof2.write_text(json.dumps({
        "customer": "example", "features": {"secmaster": True},
        "envs_dir": "terraform/envs-example", "docs_dir": None,
        "ir": os.path.relpath(ir2, ROOT).replace("\\", "/")}), encoding="utf-8")
    tgt2 = tmp / "example-110"
    r = export(prof2, tgt2, ["--version", "1.1.0", "--releases-dir", str(tmp / "rel")])
    check("second release exports", r.returncode == 0, r.stderr[-300:])
    cl = (tgt2 / "CHANGELOG.md").read_text(encoding="utf-8")
    check("changelog lists the spec delta",
          "Changes against release 1.0.0" in cl and "EXAMPLE-Prod-B" in cl, cl[:300])

    # data-loss guard: a populated non-export target is refused, untouched
    foreign = tmp / "not-an-artifact"
    foreign.mkdir()
    (foreign / "precious.txt").write_text("do not delete", encoding="utf-8")
    r = export(prof2, foreign)
    check("populated non-export target refused", r.returncode != 0,
          "export cleared a foreign directory")
    check("foreign directory left untouched",
          (foreign / "precious.txt").exists())
    # ...but re-exporting over a previous export still works
    r = export(prof2, tgt2, ["--version", "1.1.1", "--releases-dir", str(tmp / "rel")])
    check("re-export over a previous artifact still allowed", r.returncode == 0,
          r.stderr[-300:])

print()
if FAILED:
    print(f"FAILED: {len(FAILED)} -> {FAILED}")
    sys.exit(1)
print("all phase-5 tests passed")
