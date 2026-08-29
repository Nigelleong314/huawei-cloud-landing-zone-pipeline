"""Semantic validation of a parsed spec (validate())."""

from .helpers import (_truthy, _scalar, _group_by, _split_csv, _normalize_ou_parent, _account_names,
                      _lts_admin)


def validate(spec):
    errs = []
    g = spec.get("Global", {}).get("Settings", {})
    if not _scalar(g, "home_region"):
        errs.append("Global.home_region is required")
    if not _scalar(g, "state_bucket_name"):
        errs.append("Global.state_bucket_name is required")

    m1 = spec.get("01_Foundation", {})
    core = m1.get("CoreAccounts") or []
    if len(core) < 2:
        errs.append("01_Foundation.CoreAccounts must have at least 2 rows (log + security)")
    if {a.get("Name") for a in core} - {a.get("Name") for a in core if a.get("Email")}:
        errs.append("01_Foundation.CoreAccounts rows must all have Email")

    all_accts = [a for a in (core + (m1.get("WorkloadAccounts") or [])) if a.get("Name")]
    # Huawei account name must be 6-32 chars (server-side rule, not in provider).
    for a in all_accts:
        n = str(a["Name"]).strip()
        if not (6 <= len(n) <= 32):
            errs.append(f"01_Foundation account name {n!r} must be 6-32 characters (got {len(n)})")
    # Account emails must be unique (each is the account root identity).
    emails = [str(a["Email"]).strip().lower() for a in all_accts if a.get("Email")]
    dupes = {e for e in emails if emails.count(e) > 1}
    for e in sorted(dupes):
        errs.append(f"01_Foundation: account Email {e!r} is used by more than one account (must be unique)")

    account_names = {a.get("Name") for a in core if a.get("Name")} | {
        a.get("Name") for a in (m1.get("WorkloadAccounts") or []) if a.get("Name")
    }
    for t in (m1.get("TrustedServices") or []):
        admin = t.get("DelegatedAdmin")
        if admin and str(admin).strip() and str(admin).strip() not in account_names:
            errs.append(
                f"01_Foundation.TrustedServices row {t.get('Name')!r}: "
                f"DelegatedAdmin={str(admin).strip()!r} is not a Name in CoreAccounts or WorkloadAccounts"
            )

    ous = m1.get("OrganizationalUnits") or []
    ou_names = {o["Name"] for o in ous if o.get("Name")}
    parents = {o["Name"]: _normalize_ou_parent(o.get("Parent")) for o in ous if o.get("Name")}
    for name, parent in parents.items():
        if parent and parent not in ou_names:
            errs.append(f"01_Foundation.OrganizationalUnits row {name!r}: Parent={parent!r} is not another OU Name (use 'root' for top-level)")
    # Cycle detection
    for start in parents:
        seen = set()
        cur = start
        while cur and cur not in seen:
            seen.add(cur)
            cur = parents.get(cur, "")
            if cur == start:
                errs.append(f"01_Foundation.OrganizationalUnits parent cycle involving {start!r}")
                break
    # Max 2 levels (root -> top -> child). A child whose parent is also a child
    # is unsupported (Terraform can't self-reference a for_each resource).
    for name, parent in parents.items():
        if parent and parents.get(parent):  # parent has its own non-root parent
            errs.append(
                f"01_Foundation.OrganizationalUnits row {name!r}: parent {parent!r} is itself "
                f"nested - only 2 levels supported (root -> OU -> sub-OU)"
            )

    # FK checks
    m3 = spec.get("05_Network", {})  # combined hub + spoke tables (one sheet/env)
    m_spoke = m3
    vpc_names = {v.get("VPCName") for v in (m3.get("HubVPCs") or [])}
    subnets_by_vpc = _group_by(m3.get("HubSubnets") or [], "VPCName")
    for sn in (m3.get("HubSubnets") or []):
        if sn.get("VPCName") and sn["VPCName"] not in vpc_names:
            errs.append(f"05_Network.HubSubnets row references unknown VPCName={sn['VPCName']!r}")
    # Spoke tables mirror the hub: SpokeVPCs (+AccountName) / SpokeSubnets.
    # Any number of spoke VPCs per account; the env fans out one module call per
    # VPC and one provider per distinct account. VPC names must be unique (they
    # key the spokes map + generated module/provider names), and the account must
    # be a real M1 account (the spoke provider assumes its agency).
    spoke_vpc_names = {v.get("VPCName") for v in (m_spoke.get("SpokeVPCs") or [])}
    m1_acct_names = set(_account_names(spec))
    seen_vpc = {}
    for v in (m_spoke.get("SpokeVPCs") or []):
        vn = v.get("VPCName")
        if vn:
            seen_vpc[vn] = seen_vpc.get(vn, 0) + 1
        acct = v.get("AccountName")
        if acct and acct not in m1_acct_names:
            errs.append(f"05_Network.SpokeVPCs[{vn}] AccountName={acct!r} is not an account Name in 01_Foundation")
    for vn, c in seen_vpc.items():
        if c > 1:
            errs.append(f"05_Network.SpokeVPCs has {c} rows for VPCName {vn!r} (VPC names must be unique)")
    spoke_subnets_by_vpc = _group_by(m_spoke.get("SpokeSubnets") or [], "VPCName")
    for sn in (m_spoke.get("SpokeSubnets") or []):
        if sn.get("VPCName") and sn["VPCName"] not in spoke_vpc_names:
            errs.append(f"05_Network.SpokeSubnets references unknown VPCName={sn['VPCName']!r}")

    # ER attachments (hub + spoke). Route tables are FIXED (er-inbound /
    # er-outbound / er-hybrid, hard-coded in build_05_network — not spec input).
    er_rt_names  = {"er-inbound", "er-outbound", "er-hybrid"}
    er_att_names = {a.get("Name") for a in (m3.get("HubERAttachments") or [])}

    # Hub ER attachments: VPC FK + subnet must belong to that VPC.
    for a in (m3.get("HubERAttachments") or []):
        if a.get("VPC") and a["VPC"] not in vpc_names:
            errs.append(f"05_Network.HubERAttachments[{a.get('Name')}] references unknown VPC={a['VPC']!r}")
        if a.get("VPC") and a.get("Subnet"):
            snames = {sn.get("Name") for sn in subnets_by_vpc.get(str(a["VPC"]).strip(), [])}
            if a["Subnet"] not in snames:
                errs.append(f"05_Network.HubERAttachments[{a.get('Name')}].Subnet={a['Subnet']!r} is not a subnet of {a['VPC']!r}")

    # Spoke ER attachments: VPC FK -> SpokeVPCs; subnet must belong to that spoke VPC;
    # at most one per spoke VPC (one attachment per spoke module call).
    seen_spoke_att = {}
    for a in (m_spoke.get("SpokeERAttachments") or []):
        vpc = a.get("VPC")
        if vpc and vpc not in spoke_vpc_names:
            errs.append(f"05_Network.SpokeERAttachments[{a.get('Name')}] references unknown VPC={vpc!r}")
        elif vpc and a.get("Subnet"):
            snames = {sn.get("Name") for sn in spoke_subnets_by_vpc.get(str(vpc).strip(), [])}
            if a["Subnet"] not in snames:
                errs.append(f"05_Network.SpokeERAttachments[{a.get('Name')}].Subnet={a['Subnet']!r} is not a subnet of {vpc!r}")
        if vpc:
            seen_spoke_att[vpc] = seen_spoke_att.get(vpc, 0) + 1
    for vpc, c in seen_spoke_att.items():
        if c > 1:
            errs.append(f"05_Network.SpokeERAttachments has {c} attachments for VPC {vpc!r} (one per spoke VPC)")

    # Auto-wiring: the SNAT VPC attachment must be a defined ER attachment.
    snat_att = _scalar(m3.get("Settings", {}), "snat_vpc_attachment")
    if snat_att and snat_att not in er_att_names:
        errs.append(f"05_Network.Settings.snat_vpc_attachment={snat_att!r} is not a HubERAttachments.Name")
    # EIP / NAT / ELB instance tables: VPC + subnet + EIP FKs and NAT-name FKs.
    nat_names = {n.get("Name") for n in (m3.get("NATGateways") or [])}
    eip_names = {e.get("Name") for e in (m3.get("EIPs") or [])}
    all_subnet_names = {sn.get("Name") for sn in (m3.get("HubSubnets") or [])}
    for n in (m3.get("NATGateways") or []):
        if n.get("VPC") and n["VPC"] not in vpc_names:
            errs.append(f"05_Network.NATGateways[{n.get('Name')}] references unknown VPC={n['VPC']!r}")
        if n.get("Subnet") and n["Subnet"] not in all_subnet_names:
            errs.append(f"05_Network.NATGateways[{n.get('Name')}] references unknown Subnet={n['Subnet']!r}")
    for e in (m3.get("ELBs") or []):
        if e.get("VPC") and e["VPC"] not in vpc_names:
            errs.append(f"05_Network.ELBs[{e.get('Name')}] references unknown VPC={e['VPC']!r}")
        for col in ("FrontendSubnet", "BackendSubnet"):
            if e.get(col) and e[col] not in all_subnet_names:
                errs.append(f"05_Network.ELBs[{e.get('Name')}].{col} references unknown subnet {e[col]!r}")
        if e.get("EIP") and e["EIP"] not in eip_names:
            errs.append(f"05_Network.ELBs[{e.get('Name')}] references unknown EIP={e['EIP']!r}")
    for tbl in ("SNATRules", "DNATRules"):
        for r in (m3.get(tbl) or []):
            if r.get("NATName") and r["NATName"] not in nat_names:
                errs.append(f"05_Network.{tbl} references unknown NATName={r['NATName']!r}")
            if r.get("EIP") and r["EIP"] not in eip_names:
                errs.append(f"05_Network.{tbl} references unknown EIP={r['EIP']!r}")

    # Hub enterprise project must be a CostCenters.Name in sheet 02 (or blank).
    ep_name = _scalar(m3.get("Settings", {}), "enterprise_project_name")
    if ep_name:
        cc_names = {c.get("Name") for c in (spec.get("02_Finance", {}).get("CostCenters") or [])}
        if ep_name not in cc_names:
            errs.append(f"05_Network.Settings.enterprise_project_name={ep_name!r} is not a CostCenters.Name in 02_Finance")

    # OBS bucket name + KMS alias are required (globally unique, no fallback).
    m6s = spec.get("06_Observability", {}).get("AuditSettings", {})
    for k in ("audit_bucket_name", "kms_audit_alias"):
        if not _scalar(m6s, k):
            errs.append(f"06_Observability.AuditSettings.{k} is required (OBS/KMS names have no default)")

    # cts_no_transfer_accounts must be valid M1 account names.
    m1_names = set(_account_names(spec))
    for a in _split_csv(_scalar(m6s, "cts_no_transfer_accounts", "")):
        if a not in m1_names:
            errs.append(f"06_Observability.AuditSettings.cts_no_transfer_accounts: {a!r} is not an account Name in 01_Foundation")

    # ── Log aggregation (module 12) ─────────────────────────────────────────
    la = spec.get("06_Observability", {}).get("LogAggregation", {})
    lc_rows = spec.get("06_Observability", {}).get("LogConverge") or []
    if _truthy(la.get("enable_log_aggregation")):
        # The admin account is DERIVED (not input): the enabled TrustedServices
        # service.LTS row's DelegatedAdmin. The converge API only works via it.
        lagg_admin = _lts_admin(spec)
        if not lagg_admin:
            errs.append("06_Observability.LogAggregation: enable_log_aggregation=TRUE needs an ENABLED "
                        "01_Foundation.TrustedServices service.LTS row with a DelegatedAdmin "
                        "(the aggregation admin account is derived from it)")
        elif lagg_admin not in m1_names:
            errs.append(f"01_Foundation.TrustedServices service.LTS DelegatedAdmin={lagg_admin!r} "
                        "is not an account Name in 01_Foundation")
        per = _scalar(la, "transfer_period", 30)
        unit = str(_scalar(la, "transfer_period_unit", "min")).strip().lower()
        if (unit, int(per)) not in {("min", 2), ("min", 5), ("min", 30), ("hour", 1), ("hour", 3), ("hour", 6), ("hour", 12)}:
            errs.append(f"06_Observability.LogAggregation.transfer_period={per!r} {unit!r} invalid: use 2|5|30 min or 1|3|6|12 hour")
    for r in lc_rows:
        a = str(r.get("Account") or "").strip()
        if a and a not in m1_names:
            errs.append(f"06_Observability.LogConverge: Account={a!r} is not an account Name in 01_Foundation")
        for col in ("Account", "SourceGroup", "SourceStream"):
            if not str(r.get(col) or "").strip():
                errs.append(f"06_Observability.LogConverge row {r.get('SourceStream') or r.get('SourceGroup') or '?'}: {col} is required")

    # ── VPN ER routing (10_VPN) ─────────────────────────────────────────────
    m_vpn = spec.get("10_VPN", {})
    gw_names = {gw.get("Name") for gw in (m_vpn.get("Gateways") or []) if gw.get("Name")}
    gw_by_name = {gw.get("Name"): gw for gw in (m_vpn.get("Gateways") or []) if gw.get("Name")}
    for gw in (m_vpn.get("Gateways") or []):
        for col in ("ERAssocRouteTable", "ERPropRouteTable"):
            rt = str(gw.get(col) or "").strip()
            if rt and rt not in er_rt_names:
                errs.append(f"10_VPN.Gateways[{gw.get('Name')}].{col}={rt!r} is not one of the fixed "
                            "ER route tables (er-inbound | er-outbound | er-hybrid)")
            if rt and str(gw.get("Attachment") or "er").strip().lower() != "er":
                errs.append(f"10_VPN.Gateways[{gw.get('Name')}].{col} only applies to Attachment=er gateways")
    # (GatewayRoutes checks removed with the withdrawn feature — build_09_vpn
    # ignores the table; ER rejects static routes to VPN attachments.)

    # ── Edge protection (07_Security: AntiDDoS + WAF) ───────────────────────
    m10 = spec.get("07_Security", {})
    for r in (m10.get("AntiDDoS") or []):
        if r.get("EIP") and r["EIP"] not in eip_names:
            errs.append(f"07_Security.AntiDDoS[{r.get('Name')}] references unknown 05_Network EIP={r['EIP']!r}")
    waf = m10.get("WAF", {})
    if _truthy(waf.get("enable_waf")):
        for k in ("waf_availability_zone", "waf_vpc", "waf_subnet"):
            if not _scalar(waf, k):
                errs.append(f"07_Security.WAF.{k} is required when enable_waf=TRUE")
        wvpc = _scalar(waf, "waf_vpc", "")
        if wvpc and wvpc not in vpc_names:
            errs.append(f"07_Security.WAF.waf_vpc={wvpc!r} is not a 05_Network HubVPCs.VPCName")
        wsub = _scalar(waf, "waf_subnet", "")
        if wvpc and wsub:
            snames = {sn.get("Name") for sn in subnets_by_vpc.get(str(wvpc).strip(), [])}
            if wsub not in snames:
                errs.append(f"07_Security.WAF.waf_subnet={wsub!r} is not a subnet of {wvpc!r}")
    sec_acct = _scalar(m10.get("Settings", {}), "security_account", "")
    if sec_acct and sec_acct not in m1_names:
        errs.append(f"07_Security.Settings.security_account={sec_acct!r} is not an account Name in 01_Foundation")

    return errs
