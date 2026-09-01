"""spec dict -> per-env terraform.tfvars dicts (BUILDERS map)."""

import json
from pathlib import Path
from .helpers import (_home_region, _truthy, _scalar, _default_tags, _drop_none, _group_by, _csv_or_all, _split_csv, _parse_kv_csv, _normalize_ou_parent, _render_tag_policy, _account_names)


def _lc(v, default):
    return str(v).strip().lower() if v is not None and str(v).strip() != "" else default


def build_00_bootstrap(spec):
    g = spec.get("Global", {}).get("Settings", {})
    return _drop_none({
        "home_region":       _home_region(g),
        "state_bucket_name": _scalar(g, "state_bucket_name"),
    })


def build_01_foundation(spec):
    g = spec.get("Global", {}).get("Settings", {})
    m1 = spec.get("01_Foundation", {})
    s = m1.get("Settings", {})

    out = {
        "home_region": _home_region(g),
        "default_tags": _default_tags(spec),
        # No master_default_tags here: 01-foundation's provider is deliberately
        # untagged — org ACCOUNTS must not inherit the master tag set. IC content
        # (03-identity) still receives MasterDefaultTags via its own provider.
    }

    if s:
        for k in (
            "identity_center_alias",
            "cross_account_agency_name",
            "create_enterprise_project",
            "enterprise_project_name",
        ):
            v = s.get(k)
            if v is not None:
                out[k] = v

    epts = m1.get("EnabledPolicyTypes") or []
    if epts:
        out["enabled_policy_types"] = [e["Name"] for e in epts if e.get("Name")]

    ous = m1.get("OrganizationalUnits") or []
    if ous:
        out["organizational_units"] = {
            o["Name"]: {"parent": _normalize_ou_parent(o.get("Parent"))}
            for o in ous if o.get("Name")
        }

    ts = m1.get("TrustedServices") or []
    if ts:
        out["trusted_services"] = [t["Name"] for t in ts if t.get("Name")]
        deleg = {
            t["Name"]: str(t["DelegatedAdmin"]).strip()
            for t in ts
            if t.get("Name") and t.get("DelegatedAdmin") and str(t["DelegatedAdmin"]).strip()
        }
        if deleg:
            out["delegated_administrators"] = deleg

    core = m1.get("CoreAccounts") or []
    out["core_accounts"] = {
        a["Name"]: _drop_none({
            "email":       a.get("Email"),
            "ou":          a.get("OU") or "",
            "description": a.get("Description") or "",
        })
        for a in core if a.get("Name")
    }

    workload = m1.get("WorkloadAccounts") or []
    if workload:
        out["workload_accounts"] = {
            a["Name"]: _drop_none({
                "email":       a.get("Email"),
                "ou":          a.get("OU") or "",
                "description": a.get("Description") or "",
            })
            for a in workload if a.get("Name")
        }

    tps = m1.get("TagPolicies") or []
    if tps:
        out["tag_policies"] = [_render_tag_policy(t) for t in tps if t.get("Name") and t.get("TagKey")]

    return out


def _tag_keys_scp_keys(spec) -> list:
    """Distinct TagKey values from sheet-01 TagPolicies, case PRESERVED (the SCP's
    g:TagKeys is case-sensitive). Used by the require_tag_keys guardrail in the
    consolidated SCP (module 04) when Settings.enforce_tag_keys_scp is on."""
    m1 = spec.get("01_Foundation", {})
    keys = []
    for t in (m1.get("TagPolicies") or []):
        k = str(t.get("TagKey", "") or "").strip()
        if k and k not in keys:
            keys.append(k)
    return keys


def _multi_ep_enabled(spec) -> bool:
    s = spec.get("02_Finance", {}).get("Settings", {})
    return bool(_scalar(s, "enable_multi_ep", True))


def _eps_accounts(spec) -> list:
    """Every account that gets EPS enabled when multi-EP is on: master + all
    M1 accounts. Empty when multi-EP is off."""
    if not _multi_ep_enabled(spec):
        return []
    return ["master"] + _account_names(spec)


def _cost_centers_by_account(spec) -> dict:
    """{account: {ep_name: {description, type}}} for EVERY EPS account.

    When multi-EP is on, every account (master + all M1 accounts) gets an entry
    so its module call enables EPS authority there, even with zero cost centers.
    CostCenters rows add EPs to their target accounts. Account tokens: names
    (01_Foundation), 'master', 'all' (master + every account); blank = master.
    """
    accts = _eps_accounts(spec)
    if not accts:
        return {}
    by_acct = {a: {} for a in accts}            # every account, EPS-enabled
    every = ["master"] + _account_names(spec)
    for c in (spec.get("02_Finance", {}).get("CostCenters") or []):
        name = c.get("Name")
        if not name:
            continue
        targets = _csv_or_all(c.get("Accounts"))
        if not targets:
            targets = ["master"]
        elif "all" in targets:
            targets = every
        ep = _drop_none({
            "description":             c.get("Description") or "",
            "enterprise_project_type": c.get("EnterpriseProjectType") or "prod",
        })
        for acct in targets:
            by_acct.setdefault(acct, {})[name] = ep
    return by_acct


def build_02_finance(spec):
    g = spec.get("Global", {}).get("Settings", {})
    out = {
        "home_region":            _home_region(g),
        "default_tags":            _default_tags(spec),
        "foundation_state_bucket": _scalar(g, "state_bucket_name", ""),
    }
    by_acct = _cost_centers_by_account(spec)
    if by_acct:
        out["cost_centers_by_account"] = by_acct
    return out


def build_03_identity(spec):
    g = spec.get("Global", {}).get("Settings", {})
    m2 = spec.get("03_Identity", {})
    s = m2.get("Settings", {})

    out = {
        "home_region":             _home_region(g),
        "default_tags":             _default_tags(spec),
        "master_default_tags":      _default_tags(spec),  # IC content runs in master
        "foundation_state_bucket": _scalar(g, "state_bucket_name", ""),
    }
    # enable_identity_center_content / enable_iam_baseline are structural (the env
    # scaffold fixes IC content to master and the baseline to per-account calls),
    # so they are not emitted as tfvars. session_duration is a real input.
    if s.get("session_duration") is not None:
        out["session_duration"] = s["session_duration"]

    ic_pw = _drop_none({
        "min_password_length":       s.get("ic_min_password_length"),
        "password_max_age_days":     s.get("ic_password_max_age_days"),
    })
    if ic_pw:
        out["ic_password_policy"] = ic_pw

    ic_mfa = _drop_none({"mfa_required": s.get("ic_mfa_required")})
    if ic_mfa:
        out["ic_mfa_management"] = ic_mfa

    iam_login = _drop_none({
        "session_timeout":  s.get("iam_session_timeout_minutes"),
        "lockout_duration": s.get("iam_lockout_duration_minutes"),
    })
    if iam_login:
        out["iam_login_policy"] = iam_login

    groups = m2.get("Groups") or []
    if groups:
        out["groups"] = [
            {"name": g_["Name"], "description": g_.get("Description") or ""}
            for g_ in groups if g_.get("Name")
        ]

    users = m2.get("Users") or []
    if users:
        out["users"] = [
            {
                "user_name":    u["UserName"],
                "display_name": u.get("DisplayName") or u["UserName"],
                "family_name":  u.get("FamilyName") or "",
                "given_name":   u.get("GivenName") or "",
                "email":        u.get("Email") or "",
                "group_names":  u.get("GroupNames") if isinstance(u.get("GroupNames"), list) else _split_csv(u.get("GroupNames")),
            }
            for u in users if u.get("UserName")
        ]

    psets = m2.get("PermissionSets") or []
    if psets:
        out["permission_sets"] = {
            p["Name"]: _drop_none({
                "description":     p.get("Description") or "",
                "session_duration":p.get("SessionDuration") or None,
                "system_policies": p.get("SystemPolicies") if isinstance(p.get("SystemPolicies"), list) else _split_csv(p.get("SystemPolicies")),
            })
            for p in psets if p.get("Name")
        }

    assigns = m2.get("AccountAssignments") or []
    if assigns:
        out["account_assignments"] = [
            {
                "account_name":    a["AccountName"],  # build_envs leaves resolution to env via foundation state
                "group_name":      a["GroupName"],
                "permission_set":  a["PermissionSet"],
            }
            for a in assigns if a.get("AccountName")
        ]

    regs = m2.get("RegisteredRegions")
    if regs:
        out["registered_regions"] = regs

    agencies = m2.get("ServiceAgencies") or []
    if agencies:
        out["service_agencies"] = [
            _drop_none({
                "name":              a["Name"],
                "description":       a.get("Description") or "",
                "delegated_service": a["DelegatedService"],
                "policies":          a.get("Policies") if isinstance(a.get("Policies"), list) else _split_csv(a.get("Policies")),
                "all_resources":     _truthy(a.get("AllResources")) if a.get("AllResources") is not None else None,
                "project_name":      a.get("ProjectName") or None,
            })
            for a in agencies if a.get("Name")
        ]

    return out


_SCP_CSV_FIELDS = {
    "MandatoryTags":      "mandatory_tags",
    "AdminPrincipalURNs": "admin_principal_urns",
    "AllowedRegions":     "allowed_regions",
}


def build_04_perimeter(spec):
    g = spec.get("Global", {}).get("Settings", {})
    m4 = spec.get("04_Perimeter", {})

    out = {
        "home_region":             _home_region(g),
        "default_tags":            _default_tags(spec),
        "foundation_state_bucket": _scalar(g, "state_bucket_name", ""),
    }

    # SCPs table → scps object. The parser drops rows with Enabled=FALSE, so only
    # enabled policies appear here; the module defaults any omitted policy to
    # disabled. Each policy carries only its own settings (cells left blank in
    # the sheet are simply not emitted, so the module default applies).
    scps = {}
    for row in (m4.get("SCPs") or []):
        key = row.get("Policy")
        if not key:
            continue
        block = {}
        if row.get("Name"):
            block["name"] = str(row["Name"]).strip()
        if _truthy(row.get("Enforce")):
            block["enforce"] = True
        if row.get("AllowedOrgPath"):
            block["allowed_org_path"] = str(row["AllowedOrgPath"]).strip()
        for col, field in _SCP_CSV_FIELDS.items():
            v = row.get(col)
            if v:
                block[field] = v if isinstance(v, list) else _split_csv(v)
        # deny_public_obs: a BLANK ExceptionTagKey is meaningful (no exception →
        # public denied outright), so emit it explicitly as "".
        if key == "deny_public_obs":
            block["exception_tag_key"] = str(row["ExceptionTagKey"]).strip() if row.get("ExceptionTagKey") else ""
            if row.get("ExceptionTagValue"):
                block["exception_tag_value"] = str(row["ExceptionTagValue"]).strip()
        scps[key] = block

    # require_tag_keys guardrail (9th): folded into the consolidated SCP here in
    # module 04, but driven by sheet 01 - keys are the TagPolicies TagKey values
    # (case PRESERVED; g:TagKeys is case-sensitive), enabled + enforced via
    # sheet-01 Settings.enforce_tag_keys_scp.
    if _truthy(spec.get("01_Foundation", {}).get("Settings", {}).get("enforce_tag_keys_scp")):
        keys = _tag_keys_scp_keys(spec)
        if keys:
            scps["require_tag_keys"] = {"enforce": True, "tag_keys": keys}

    if scps:
        out["scps"] = scps

    # Predefined-tag dictionary (applied per account via generated fan-out).
    # Tag keys are normalized to lowercase.
    tags = m4.get("PredefinedTags") or []
    if tags:
        out["predefined_tags"] = [
            {
                "key":    str(t["Key"]).strip().lower(),
                "values": t["Values"] if isinstance(t.get("Values"), list) else _split_csv(t.get("Values")),
            }
            for t in tags if t.get("Key")
        ]

    # Config (RMS) org setup. config_admin_account selects the account the
    # org-wide Config resources run on (generated fan-out wires the provider);
    # the rest populate the module's `config` object. Emitted only when an admin
    # account is named — blank = skip all Config setup.
    cfg = m4.get("ConfigSetup", {}) or {}
    admin = str(cfg.get("config_admin_account", "") or "").strip()
    if admin:
        out["config_admin_account"] = admin
        config = {}
        for sheet_key, mod_key in _CONFIG_FIELD_MAP.items():
            v = cfg.get(sheet_key)
            if v is not None and v != "":
                config[mod_key] = v
        out["config"] = config

        # Conformance packs (org-wide). Rows are pre-filtered to Enabled=TRUE by
        # the reader. template_key blank = auto-resolve by name in the module.
        packs = []
        for row in (m4.get("ConfigConformancePacks") or []):
            pkg = str(row.get("Package", "") or "").strip()
            if not pkg:
                continue
            pack = {"name": pkg, "enabled": True}
            tk = str(row.get("TemplateKey", "") or "").strip()
            if tk:
                pack["template_key"] = tk
            pn = str(row.get("Name", "") or "").strip()
            if pn:
                pack["pack_name"] = pn
            # Vars: 'key=value' overrides (comma-separated). Values are JSON-encoded
            # as strings to match the template's var_value format (e.g. PCI DSS
            # trackBucket). Templates with non-string params would need pre-encoded
            # values, but the empty-default params that need overriding are strings.
            vraw = row.get("Vars")
            overrides = {}
            for item in (vraw if isinstance(vraw, list) else _split_csv(vraw)):
                s = str(item).strip()
                if "=" in s:
                    k, _, v = s.partition("=")
                    if k.strip():
                        overrides[k.strip()] = json.dumps(v.strip())
            if overrides:
                pack["vars"] = overrides
            # Accounts to exempt from this pack. Account Names (resolved to domain
            # IDs by the config_packs codegen) or raw 32-hex domain IDs. Master is
            # always excluded by the codegen, so it need not be listed here.
            eraw = row.get("ExcludedAccounts")
            excl = [str(x).strip() for x in (eraw if isinstance(eraw, list) else _split_csv(eraw)) if str(x).strip()]
            if excl:
                pack["excluded_accounts"] = excl
            packs.append(pack)
        if packs:
            out["conformance_packs"] = packs

    return out


_CONFIG_FIELD_MAP = {
    "enable_config_recorder":   "enable_recorder",
    "recorder_agency_name":     "recorder_agency_name",
    "create_recorder_agency":   "create_recorder_agency",
    "recorder_bucket_name":     "recorder_bucket_name",
    "create_recorder_bucket":   "create_recorder_bucket",
    "recorder_bucket_region":   "recorder_bucket_region",
    "recorder_all_supported":   "recorder_all_supported",
    "recorder_smn_topic_urn":   "recorder_smn_topic_urn",
    "enable_config_aggregator": "enable_aggregator",
    "aggregator_name":          "aggregator_name",
}


def build_06_observability(spec):
    g = spec.get("Global", {}).get("Settings", {})
    obs = spec.get("06_Observability", {})  # modules 6 + 7 share this env/sheet
    s6 = obs.get("AuditSettings", {})
    s7 = obs.get("OpsSettings", {})

    out = {
        "home_region":             _home_region(g),
        "default_tags":             _default_tags(spec),
        "foundation_state_bucket": _scalar(g, "state_bucket_name", ""),
    }
    for k in (
        "audit_retention_days",
        "audit_cold_after_days",
        "lts_hot_retention_days",
        "kms_pending_days",
        "audit_bucket_name",
        "kms_audit_alias",
        "cts_log_group_name",
        "cts_log_stream_name",
        "audit_bucket_force_destroy",
    ):
        v = s6.get(k)
        if v is not None:
            out[k] = v

    # Module 12 inputs (org log aggregation; the converge fan-out itself is
    # generated — see _emit_observability_codegen).
    la = obs.get("LogAggregation", {})
    for k in (
        "enable_log_aggregation",
        "archive_bucket_name",
        "kms_archive_alias",
        "archive_retention_days",
        "archive_cold_after_days",
        "converged_retention_days",
        "transfer_period",
        "transfer_period_unit",
        "archive_bucket_force_destroy",
    ):
        v = la.get(k)
        if v is not None:
            out[k] = v
    # Blank archive names default to the {account-name} pattern (the module
    # substitutes the token with the LTS delegated-admin account name).
    if _truthy(la.get("enable_log_aggregation")):
        if not str(out.get("archive_bucket_name") or "").strip():
            out["archive_bucket_name"] = "{account-name}-lz-obs-logarchive-01"
        if not str(out.get("kms_archive_alias") or "").strip():
            out["kms_archive_alias"] = "{account-name}-lz-logarchive-key"

    # Module 7 inputs (same env)
    if s7.get("topic_name") is not None:
        out["topic_name"] = s7["topic_name"]

    subs = obs.get("Subscribers") or []
    if subs:
        out["subscribers"] = [
            {"protocol": x["Protocol"], "endpoint": x["Endpoint"]}
            for x in subs if x.get("Protocol") and x.get("Endpoint")
        ]

    ns = obs.get("OneClickNamespaces") or []
    if ns:
        out["one_click_alarms"] = [
            {
                "namespace":     n["Namespace"],
                "event_enabled": _truthy(n.get("EventEnabled")) if n.get("EventEnabled") is not None else True,
            }
            for n in ns if n.get("Namespace")
        ]

    return out


def build_05_network(spec):
    g = spec.get("Global", {}).get("Settings", {})
    m3 = spec.get("05_Network", {})
    s = m3.get("Settings", {})

    out = {
        "home_region":             _home_region(g),
        "default_tags":            _default_tags(spec),
        "foundation_state_bucket": _scalar(g, "state_bucket_name", ""),
    }
    # Settings (hub-wide) + the now-separate EnterpriseRouter / CloudFirewall
    # scalar tables. NAT and ELB are multi-instance object-tables (below).
    er  = m3.get("EnterpriseRouter", {})
    cfw = m3.get("CloudFirewall", {})

    for k in ("hub_account", "spoke_private_supernet", "enterprise_project_name"):
        v = s.get(k)
        if v is not None:
            out[k] = v
    # FIXED ER wiring (not spec input): every hub + spoke VPC attachment
    # associates to er-inbound and propagates into er-outbound.
    out["inbound_route_table"] = "er-inbound"
    out["outbound_route_table"] = "er-outbound"
    v = s.get("snat_vpc_attachment")
    if v is not None:
        out["snat_vpc_attachment"] = v
    # Hub-resolver DNS: DHCP DNS servers on every hub + spoke subnet.
    if s.get("subnet_dns_servers"):
        out["subnet_dns"] = _split_csv(s.get("subnet_dns_servers"))
    # Per-VPC flow logs (hub + spokes; '<vpc>-flowlog' LTS group/stream each).
    for k in ("enable_vpc_flow_logs", "flow_log_retention_days"):
        v = s.get(k)
        if v is not None:
            out[k] = v
    for k in ("er_name", "er_asn", "er_flow_log_name", "er_auto_accept_shared_attachments",
              "er_share_name"):
        v = er.get(k)
        if v is not None:
            out[k] = v
    for k in ("cfw_name", "cfw_flavor", "cfw_ips_protection_mode", "cfw_ips_patch_enabled"):
        v = cfw.get(k)
        if v is not None:
            out[k] = v
    # FIXED: CFW east-west mode is always ER-attached (not spec input).
    out["east_west_firewall_mode"] = "er"
    for k in ("inspection_cidr_reservation",
              "cfw_charging_mode", "cfw_period_unit", "cfw_period", "cfw_auto_renew",
              "cfw_lts_log_enable", "cfw_lts_log_group_name",
              "cfw_lts_traffic_stream_name", "cfw_lts_access_stream_name", "cfw_lts_attack_stream_name"):
        v = cfw.get(k)
        if v is not None:
            out[k] = v

    # EIPs — each with a dedicated bandwidth; NAT (SNAT/DNAT) and ELBs ref by name.
    eips = m3.get("EIPs") or []
    if eips:
        out["eips"] = [
            {
                "name":           r["Name"],
                "type":           r.get("Type") or "5_bgp",
                "billed_by":      r.get("BilledBy") or "bandwidth",
                "bandwidth_size": int(r.get("BandwidthSize") or 100),
                "description":    r.get("Description") or "",
            }
            for r in eips if r.get("Name")
        ]

    nats = m3.get("NATGateways") or []
    if nats:
        out["nat_gateways"] = [
            {
                "name":   r["Name"],
                "spec":   r.get("Specification") or "Small",
                "vpc":    r["VPC"],
                "subnet": r.get("Subnet") or "",
            }
            for r in nats if r.get("Name")
        ]

    elbs = m3.get("ELBs") or []
    if elbs:
        out["elbs"] = [
            {
                "name":            r["Name"],
                "azs":             _split_csv(r.get("AZ")),
                "vpc":             r["VPC"],
                "frontend_subnet": r.get("FrontendSubnet") or "",
                "backend_subnet":  r.get("BackendSubnet") or "",
                "ip_as_backend":   _truthy(r.get("IPAsBackend")),
                "eip":             r.get("EIP") or "",
            }
            for r in elbs if r.get("Name")
        ]

    azs = m3.get("ERAvailabilityZones")
    if azs:
        out["er_availability_zones"] = azs

    vpcs = m3.get("HubVPCs") or []
    subnets_by_vpc = _group_by(m3.get("HubSubnets") or [], "VPCName")
    if vpcs:
        out["hub_vpcs"] = {}
        for v in vpcs:
            name = v.get("VPCName")
            if not name:
                continue
            out["hub_vpcs"][name] = {
                "cidr": v["CIDR"],
                "subnets": [
                    {"name": sn["Name"], "cidr": sn["CIDR"]}
                    for sn in subnets_by_vpc.get(name, []) if sn.get("Name")
                ],
            }

    # Explicit HUB ER attachments (hub-account VPC attachments).
    er_atts = m3.get("HubERAttachments") or []
    if er_atts:
        out["er_attachments"] = [
            {
                "name":           r["Name"],
                "vpc":            r["VPC"],
                "subnet":         r.get("Subnet") or "",
                "auto_add_route": _truthy(r.get("AutoAddRoute")),
                "description":    r.get("Description") or "",
            }
            for r in er_atts if r.get("Name")
        ]

    # FIXED ER route tables (not spec input): the whole inspection topology is
    # wired from these three names + Settings.snat_vpc_attachment. er-hybrid
    # carries the 0.0.0.0/0 -> CFW default so VPN/DC traffic is inspected.
    out["er_route_tables"] = [
        {"name": "er-inbound",  "description": "All VPC attachments auto-associate; auto static route 0.0.0.0/0 -> CFW"},
        {"name": "er-outbound", "description": "CFW auto-associates; VPC CIDRs auto-propagated; auto 0.0.0.0/0 -> SNAT VPC attachment"},
        {"name": "er-hybrid",   "description": "VPN/DC attachments associate here (10_VPN.ERAssocRouteTable); 0/0 -> CFW keeps DC traffic inspected"},
    ]
    out["cfw_default_route_tables"] = ["er-hybrid"]

    # ER routing is AUTO-wired by the module from inbound_route_table /
    # outbound_route_table / snat_vpc_attachment: every hub + spoke VPC associates
    # to inbound + propagates to outbound; CFW associates to outbound; static
    # routes inbound 0.0.0.0/0 -> CFW and outbound 0.0.0.0/0 -> snat_vpc_attachment.

    # VPC default-route tables are AUTO-wired by the module from snat_vpc_attachment
    # + spoke_private_supernet: the SNAT VPC gets 0.0.0.0/0 -> NAT and <supernet> ->
    # ER; every other hub + spoke VPC gets 0.0.0.0/0 -> ER. No per-row tables.

    snats = m3.get("SNATRules") or []
    if snats:
        out["snat_rules"] = [
            {"nat_name": r.get("NATName") or "", "cidr": r["CIDR"], "eip": r.get("EIP") or "", "description": r.get("Description") or ""}
            for r in snats if r.get("CIDR")
        ]

    dnats = m3.get("DNATRules") or []
    if dnats:
        out["dnat_rules"] = [
            {
                "nat_name":      r.get("NATName") or "",
                "eip":           r.get("EIP") or "",
                "external_port": int(r["ExternalPort"]),
                "internal_ip":   r["InternalIP"],
                "internal_port": int(r["InternalPort"]),
                "protocol":      r.get("Protocol") or "tcp",
                "description":   r.get("Description") or "",
            }
            for r in dnats if r.get("ExternalPort") is not None
        ]

    ram = m3.get("RAMSharePrincipals")
    if ram:
        out["ram_share_principals"] = ram

    # Spokes are deployed in the SAME env/apply as the hub.
    spokes = _build_spokes(m3)
    if spokes:
        out["spokes"] = spokes

    # VPN was un-merged into env 10-network-vpn (2026-07): its tfvars come from
    # build_10_vpn; nothing VPN-related lands here anymore.
    return out


def _build_spokes(m3) -> dict:
    """Spoke VPCs/subnets from the combined 05_Network sheet, keyed by VPC name
    (any number per account — the env fans out one module call per spoke VPC and
    one provider per distinct account). The spoke VPC default route (0.0.0.0/0 ->
    hub ER) and attachment wiring are handled by the module."""
    spoke_vpcs = m3.get("SpokeVPCs") or []
    subnets_by_vpc = _group_by(m3.get("SpokeSubnets") or [], "VPCName")
    att_by_vpc = {a.get("VPC"): a for a in (m3.get("SpokeERAttachments") or []) if a.get("VPC")}
    spokes = {}
    for v in spoke_vpcs:
        vpc_name = v.get("VPCName")
        acct = v.get("AccountName")
        if not (vpc_name and acct):
            continue
        att = att_by_vpc.get(vpc_name, {})
        spokes[vpc_name] = {
            "account":  acct,
            "vpc_name": vpc_name,
            "vpc_cidr": v["CIDR"],
            # No SpokeERAttachments row = isolated spoke (no attachment/route/wiring).
            "er_attach":          vpc_name in att_by_vpc,
            "er_attachment_name": att.get("Name") or "",
            "er_attach_subnet":   att.get("Subnet") or "",
            "auto_add_route":     _truthy(att.get("AutoAddRoute")),
            "vpc_tags": _parse_kv_csv(v.get("Tags")),
            "subnets": [
                {"name": sn["Name"], "cidr": sn["CIDR"], "tags": _parse_kv_csv(sn.get("Tags"))}
                for sn in subnets_by_vpc.get(vpc_name, []) if sn.get("Name")
            ],
        }
    return spokes


def build_07_dns(spec):
    g = spec.get("Global", {}).get("Settings", {})
    m = spec.get("08_DNS", {})
    s = m.get("Settings", {})

    out = {
        "home_region":             _home_region(g),
        "default_tags":            _default_tags(spec),
        "foundation_state_bucket": _scalar(g, "state_bucket_name", ""),
        "network_state_bucket":    _scalar(g, "state_bucket_name", ""),
    }
    if s.get("dns_account") is not None:
        out["dns_account"] = s["dns_account"]
    if s.get("enterprise_project_name") is not None:
        out["enterprise_project_name"] = s["enterprise_project_name"]

    # Object-tables are already Enabled-filtered by the reader; csv-list columns
    # arrive as raw strings, so split them here. Blank TTL is dropped so the
    # module's optional(ttl, 300) default applies.
    pub = m.get("PublicZones") or []
    if pub:
        out["public_zones"] = [
            _drop_none({
                "name":        z["Name"],
                "email":       z.get("Email") or "",
                "ttl":         int(z["TTL"]) if z.get("TTL") is not None else None,
                "description": z.get("Description") or "",
            })
            for z in pub if z.get("Name")
        ]

    priv = m.get("PrivateZones") or []
    if priv:
        out["private_zones"] = [
            _drop_none({
                "name":        z["Name"],
                "vpcs":        _split_csv(z.get("VPCs")),
                "ttl":         int(z["TTL"]) if z.get("TTL") is not None else None,
                "recursive":   _truthy(z.get("Recursive")),
                "description": z.get("Description") or "",
            })
            for z in priv if z.get("Name")
        ]

    recs = m.get("RecordSets") or []
    if recs:
        out["recordsets"] = [
            _drop_none({
                "zone":        r["Zone"],
                "name":        r["Name"],
                "type":        r["Type"],
                "records":     _split_csv(r.get("Records")),
                "ttl":         int(r["TTL"]) if r.get("TTL") is not None else None,
                "description": r.get("Description") or "",
            })
            for r in recs if r.get("Zone") and r.get("Name") and r.get("Type")
        ]

    eps = m.get("ResolverEndpoints") or []
    if eps:
        out["resolver_endpoints"] = [
            {
                "name":      e["Name"],
                "direction": e["Direction"],
                "vpc":       e.get("VPC") or "",
                "subnets":   _split_csv(e.get("Subnets")),
                "ips":       _split_csv(e.get("IPs")),
            }
            for e in eps if e.get("Name") and e.get("Direction")
        ]

    rules = m.get("ResolverRules") or []
    if rules:
        out["resolver_rules"] = [
            {
                "name":        r["Name"],
                "endpoint":    r.get("Endpoint") or "",
                "domain_name": r.get("DomainName") or "",
                "target_ips":  _split_csv(r.get("TargetIPs")),
                "vpcs":        _split_csv(r.get("VPCs")),
            }
            for r in rules if r.get("Name")
        ]

    logs = m.get("AccessLogs") or []
    if logs:
        out["access_logs"] = [
            {
                "name":       a.get("Name") or "",
                "lts_group":  a.get("LTSGroup") or "",
                "lts_stream": a.get("LTSStream") or "",
                "vpcs":       _split_csv(a.get("VPCs")),
            }
            for a in logs if a.get("LTSGroup") and a.get("LTSStream")
        ]

    return out


def build_08_cfw(spec):
    g = spec.get("Global", {}).get("Settings", {})
    m = spec.get("09_CFW", {})
    s = m.get("Settings", {})

    out = {
        "home_region":             _home_region(g),
        "default_tags":            _default_tags(spec),
        "foundation_state_bucket": _scalar(g, "state_bucket_name", ""),
        "network_state_bucket":    _scalar(g, "state_bucket_name", ""),
    }
    if s.get("cfw_account") is not None:
        out["cfw_account"] = s["cfw_account"]
    # EP the hub CFW lives in (from 05_Network) - the attack-defense data source
    # and reverse-shell rules are EP-scoped, so the env resolves this to an ID.
    epn = spec.get("05_Network", {}).get("Settings", {}).get("enterprise_project_name")
    if epn:
        out["enterprise_project_name"] = epn
    for k in ("enable_anti_virus", "enable_reverse_shell_defense", "alarm_topic_name",
              "enable_attack_alarm", "enable_traffic_alarm",
              "enable_eip_unprotected_alarm", "enable_threat_intel_alarm"):
        if s.get(k) is not None:
            out[k] = s[k]

    ag = m.get("AddressGroups") or []
    if ag:
        out["address_groups"] = [
            {
                "name":         r["Name"],
                "border":       _lc(r.get("Border"), "internet"),
                "address_type": _lc(r.get("AddressType"), "ipv4"),
                "members":      _split_csv(r.get("Members")),
                "description":  r.get("Description") or "",
            }
            for r in ag if r.get("Name")
        ]

    dg = m.get("DomainGroups") or []
    if dg:
        out["domain_groups"] = [
            {
                "name":        r["Name"],
                "border":      _lc(r.get("Border"), "internet"),
                "type":        _lc(r.get("Type"), "application"),
                "domains":     _split_csv(r.get("Domains")),
                "description": r.get("Description") or "",
            }
            for r in dg if r.get("Name")
        ]

    sg = m.get("ServiceGroups") or []
    if sg:
        out["service_groups"] = [
            {
                "name":        r["Name"],
                "border":      _lc(r.get("Border"), "internet"),
                "members":     _split_csv(r.get("Members")),
                "description": r.get("Description") or "",
            }
            for r in sg if r.get("Name")
        ]

    # Rule token lists (Source/Destination/Service) are NOT lowercased — group
    # names and L7 app tokens (app:HTTPS) are case-sensitive.
    acl = m.get("ACLRules") or []
    if acl:
        out["acl_rules"] = [
            {
                "name":        r["Name"],
                "kind":        _lc(r.get("Kind"), "eip"),
                "action":      _lc(r.get("Action"), "allow"),
                "source":      _split_csv(r.get("Source")) or ["any"],
                "destination": _split_csv(r.get("Destination")) or ["any"],
                "service":     _split_csv(r.get("Service")) or ["any"],
                "status":      _lc(r.get("Status"), "enable"),
                "direction":   _lc(r.get("Direction"), ""),
                "description": r.get("Description") or "",
            }
            for r in acl if r.get("Name") and r.get("Kind")
        ]

    bw = m.get("BlackWhiteLists") or []
    if bw:
        out["black_white_lists"] = [
            {
                "name":         r.get("Name") or "",
                "border":       _lc(r.get("Border"), "internet"),
                "list_type":    _lc(r.get("ListType"), "blacklist"),
                "direction":    _lc(r.get("Direction"), "source"),
                "protocol":     _lc(r.get("Protocol"), "any"),
                "address_type": _lc(r.get("AddressType"), "ipv4"),
                "address":      r["Address"],
                "port":         str(r["Port"]).strip() if r.get("Port") is not None else "",
                "description":  r.get("Description") or "",
            }
            for r in bw if r.get("ListType") and r.get("Address")
        ]

    return out


def build_10_vpn(spec):
    """10_VPN -> envs/10-network-vpn: S2C VPN gateways/customer gateways/
    connections. Standalone env since 2026-07 (was merged into 05-network);
    reads hub/spoke IDs from the 05-network remote state. vpn_account provider
    assumes the hub account (same as hub_account)."""
    g = spec.get("Global", {}).get("Settings", {})
    m = spec.get("10_VPN", {})
    s = m.get("Settings", {})
    n5s = spec.get("05_Network", {}).get("Settings", {})

    out = {
        "home_region":             _home_region(g),
        "default_tags":            _default_tags(spec),
        "foundation_state_bucket": _scalar(g, "state_bucket_name", ""),
        "network_state_bucket":    _scalar(g, "state_bucket_name", ""),
    }
    # EP: the 10_VPN sheet's own setting wins; fall back to the hub's LZ EP.
    epn = s.get("enterprise_project_name")
    if epn is None:
        epn = n5s.get("enterprise_project_name")
    if epn is not None:
        out["enterprise_project_name"] = epn
    if s.get("vpn_account") is not None:
        out["vpn_account"] = s["vpn_account"]

    gws = m.get("Gateways") or []
    if gws:
        out["gateways"] = [
            _drop_none({
                "name":           r["Name"],
                "attachment":     _lc(r.get("Attachment"), "er"),
                "vpc":            r.get("VPC") or "",
                "connect_subnet": r.get("ConnectSubnet") or "",
                "local_subnets":  _split_csv(r.get("LocalSubnets")),
                "network_type":   _lc(r.get("NetworkType"), "public"),
                "ha_mode":        _lc(r.get("HAMode"), "active-standby"),
                "flavor":         r.get("Flavor") or "",
                "azs":            _split_csv(r.get("AZs")),
                "asn":            int(r["ASN"]) if r.get("ASN") is not None else None,
                "bandwidth_size": int(r["BandwidthSize"]) if r.get("BandwidthSize") is not None else None,
                "eip_charge_mode": _lc(r.get("EIPChargeMode"), "bandwidth"),
                "er_association_route_table": r.get("ERAssocRouteTable") or "",
                "er_propagation_route_table": r.get("ERPropRouteTable") or "",
            })
            for r in gws if r.get("Name")
        ]

    # GatewayRoutes (static ER routes -> VPN attachment) was WITHDRAWN: Huawei ER
    # rejects static routes to VPN attachments (ER.04006105); on-prem routes enter
    # route tables via the gateway's PROPAGATION only. Any leftover sheet rows are
    # deliberately ignored.

    cgs = m.get("CustomerGateways") or []
    if cgs:
        out["customer_gateways"] = [
            _drop_none({
                "name":       r["Name"],
                "ip":         r.get("IP") or "",
                "asn":        int(r["ASN"]) if r.get("ASN") is not None else None,
                "route_mode": _lc(r.get("RouteMode"), "bgp"),
            })
            for r in cgs if r.get("Name")
        ]

    conns = m.get("Connections") or []
    if conns:
        out["connections"] = [
            {
                "name":             r["Name"],
                "gateway":          r.get("Gateway") or "",
                "customer_gateway": r.get("CustomerGateway") or "",
                "vpn_type":         _lc(r.get("VPNType"), "bgp"),
                "peer_subnets":     _split_csv(r.get("PeerSubnets")),
                "ha_role":          _lc(r.get("HARole"), "master"),
                "psk":              str(r.get("PSK")) if r.get("PSK") is not None else "",
            }
            for r in conns if r.get("Name")
        ]

    return out


def build_09_sgacl(spec):
    """11_SGACL -> envs/11-network-sgacl: workload security groups, grouped by
    owning account for the per-account module fan-out. Rules inherit their
    group's account via the SG name (names are globally unique - LZR-030)."""
    g = spec.get("Global", {}).get("Settings", {})
    m = spec.get("11_SGACL", {})

    out = {
        "home_region":             _home_region(g),
        "default_tags":            _default_tags(spec),
        "foundation_state_bucket": _scalar(g, "state_bucket_name", ""),
    }

    def _s(v):
        """Excel cell -> clean string ('' for blank; 443 -> '443', 443.0 -> '443')."""
        if v is None:
            return ""
        if isinstance(v, float) and v.is_integer():
            return str(int(v))
        return str(v).strip()

    groups = m.get("SecurityGroups") or []
    rules = m.get("SGRules") or []
    sg_account = {}
    secgroups = {}
    for r in groups:
        acct, name = _s(r.get("Account")), _s(r.get("Name"))
        if not (acct and name):
            continue
        sg_account[name] = acct
        secgroups.setdefault(acct, {"groups": [], "rules": []})["groups"].append({
            "name":        name,
            "description": r.get("Description") or "",
            "tags":        _parse_kv_csv(r.get("Tags")),
        })
    for r in rules:
        sg = _s(r.get("SG"))
        acct = sg_account.get(sg)
        if not acct:
            continue  # unknown SG reference - LZR-030 fails the build loudly
        secgroups[acct]["rules"].append({
            "sg":          sg,
            "direction":   _lc(r.get("Direction"), "ingress"),
            "protocol":    _lc(r.get("Protocol"), "any"),
            "ports":       _s(r.get("Ports")),
            "remote":      _s(r.get("Remote")),
            "action":      _lc(r.get("Action"), "allow"),
            "description": r.get("Description") or "",
        })
    if secgroups:
        out["secgroups"] = secgroups

    return out


def build_10_security(spec):
    g = spec.get("Global", {}).get("Settings", {})
    m5 = spec.get("07_Security", {})
    s = m5.get("Settings", {})

    out = {
        "home_region":                _home_region(g),
        "default_tags":                _default_tags(spec),
        "foundation_state_bucket":    _scalar(g, "state_bucket_name", ""),
        "observability_state_bucket": _scalar(g, "state_bucket_name", ""),
    }
    for k in (
        "secmaster_workspace_name",
        "enable_hss",
        "hss_quota_count",
        "enable_dbss",
        "enable_member_workspaces",
    ):
        v = s.get(k)
        if v is not None:
            out[k] = v

    mods = m5.get("SecMasterModules")
    if mods:
        out["secmaster_modules"] = mods

    rules = m5.get("AlertRules") or []
    if rules:
        out["alert_rules"] = [
            _drop_none({
                "name":        r["Name"],
                "description": r.get("Description") or "",
                "severity":    r["Severity"],
                "rule_type":   r.get("RuleType") or "log",
                "query":       r.get("Query") or "",
            })
            for r in rules if r.get("Name")
        ]

    if s.get("security_account") is not None:
        out["security_account"] = s["security_account"]

    # ── Module 13 (edge protection) — deploys into the 05_Network hub account ──
    m3s = spec.get("05_Network", {}).get("Settings", {})
    if m3s.get("hub_account") is not None:
        out["hub_account"] = m3s["hub_account"]
    out["network_state_bucket"] = _scalar(g, "state_bucket_name", "")

    add = m5.get("AntiDDoS") or []
    if add:
        out["antiddos"] = [
            {
                "name":           r["Name"],
                "eip":            r.get("EIP") or "",
                "threshold_mbps": int(r["ThresholdMbps"]) if r.get("ThresholdMbps") is not None else 100,
                "alarm_topic":    r.get("AlarmTopic") or "",
            }
            for r in add if r.get("Name")
        ]

    waf = m5.get("WAF", {})
    for k in ("enable_waf", "waf_instance_name", "waf_specification_code",
              "waf_availability_zone", "waf_vpc", "waf_subnet", "waf_policy_name"):
        v = waf.get(k)
        if v is not None:
            out[k] = v

    wds = m5.get("WAFDomains") or []
    if wds:
        out["waf_domains"] = [
            _drop_none({
                "domain":          r["Domain"],
                "client_protocol": (r.get("ClientProtocol") or "HTTP").upper(),
                "server_protocol": (r.get("ServerProtocol") or "HTTP").upper(),
                "origin_address":  r.get("OriginAddress") or "",
                "origin_port":     int(r["OriginPort"]) if r.get("OriginPort") is not None else 80,
                "certificate_id":  r.get("CertificateId") or "",
            })
            for r in wds if r.get("Domain")
        ]

    return out


BUILDERS = {
    "00-bootstrap":     build_00_bootstrap,
    "01-foundation":    build_01_foundation,
    "02-finance":       build_02_finance,
    "03-identity":      build_03_identity,
    "04-perimeter":     build_04_perimeter,
    "06-observability": build_06_observability,
    "05-network":       build_05_network,
    "08-network-dns":   build_07_dns,
    "09-network-cfw":   build_08_cfw,
    "10-network-vpn":   build_10_vpn,
    "11-network-sgacl": build_09_sgacl,
    "07-security":      build_10_security,
}
