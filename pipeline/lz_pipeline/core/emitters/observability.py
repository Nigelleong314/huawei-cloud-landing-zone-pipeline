"""06-observability: audit/ops fan-out + LTS log-converge codegen."""
from pathlib import Path
from ..helpers import MODULE_SOURCE_ROOT, _truthy, _scalar, _split_csv, _csv_or_all, _account_names, _acct_alias, _lts_admin
from ..writer import write_generated
from .common import _assume_role_provider


_AUDIT_MODULE_SRC = MODULE_SOURCE_ROOT + "/compliance-audit"

_OPS_MODULE_SRC   = MODULE_SOURCE_ROOT + "/ops-monitoring"


_CTS_TRACKER_MODULE_SRC = MODULE_SOURCE_ROOT + "/cts-tracker"


_LOGAGG_MODULE_SRC = MODULE_SOURCE_ROOT + "/log-aggregation"


def _emit_observability_codegen(env_dir: Path, spec: dict):
    """Env 05: ONE central audit module (module 6) in the CTS-admin account, a
    per-account ops module (module 7) fan-out over OpsSettings.accounts, and a
    per-account no-transfer CTS tracker over AuditSettings.cts_no_transfer_accounts.
    Everything runs through assume_role providers; {account-name} is substituted in
    the modules."""
    obs   = spec.get("06_Observability", {})
    admin = _scalar(obs.get("AuditSettings", {}), "cts_admin_account", "")
    ops   = _csv_or_all(obs.get("OpsSettings", {}).get("accounts"))
    if "all" in ops:
        ops = _account_names(spec)
    # De-duplicate (preserve first-seen order) so a repeated account in the
    # accounts cell doesn't emit duplicate provider/module blocks.
    ops = [a for a in dict.fromkeys(ops) if a]

    # No-transfer CTS accounts (CTS on, no OBS/LTS). The admin already has the
    # central org tracker, so never duplicate a tracker there.
    cts_nt = _split_csv(_scalar(obs.get("AuditSettings", {}), "cts_no_transfer_accounts", ""))
    cts_nt = [a for a in dict.fromkeys(cts_nt) if a and a != admin]

    # Org log aggregation (module 12): source accounts need per-account LTS
    # lookups; the LTS admin runs the converge + archive bucket.
    la = obs.get("LogAggregation", {}) or {}
    lc_rows = obs.get("LogConverge") or []
    # Admin account is DERIVED from 01_Foundation TrustedServices service.LTS
    # DelegatedAdmin (not spec input).
    lagg_admin = _lts_admin(spec)
    lagg_on = _truthy(la.get("enable_log_aggregation")) and bool(lc_rows) and bool(lagg_admin)

    lc_accounts = []
    if lagg_on:
        for r in lc_rows:
            a = str(r.get("Account") or "").strip()
            if a and a not in lc_accounts:
                lc_accounts.append(a)

    # One assume_role provider per distinct fan-out account (ops + cts-no-transfer
    # + log-converge sources).
    fanout = list(ops)
    for a in cts_nt + lc_accounts:
        if a not in fanout:
            fanout.append(a)

    prov = [
        "# --- Audit and monitoring account providers ---",
        "",
    ]
    if admin:
        prov += _assume_role_provider("audit_admin", admin)
    if lagg_on:
        prov += _assume_role_provider("lts_admin", lagg_admin)
    for a in fanout:
        prov += _assume_role_provider(_acct_alias(a), a)

    calls = [
    ]
    if admin:
        calls += [
            f"# --- Central audit - {admin} ---",
            'module "audit" {',
            f'  source    = "{_AUDIT_MODULE_SRC}"',
            "  providers = { huaweicloud = huaweicloud.audit_admin }",
            "",
            "  environment                = var.environment",
            "  home_region                = var.home_region",
            f'  account_name               = "{admin}"',
            "  audit_bucket_name          = var.audit_bucket_name",
            "  kms_audit_alias            = var.kms_audit_alias",
            "  member_account_ids         = local.member_account_ids",
            "  audit_retention_days       = var.audit_retention_days",
            "  audit_cold_after_days      = var.audit_cold_after_days",
            "  kms_pending_days           = var.kms_pending_days",
            "  audit_bucket_force_destroy = var.audit_bucket_force_destroy",
        ] + _cts_notification_lines(admin, ops) + [
            "}",
            "",
        ]
    for a in ops:
        calls += [
            f'module "ops_{_acct_alias(a)}" {{',
            f'  source    = "{_OPS_MODULE_SRC}"',
            f"  providers = {{ huaweicloud = huaweicloud.{_acct_alias(a)} }}",
            "",
            "  environment           = var.environment",
            f'  account_name          = "{a}"',
            "  topic_name            = var.topic_name",
            "  subscribers           = var.subscribers",
            "  one_click_alarms      = var.one_click_alarms",
            "}",
            "",
        ]
    for a in cts_nt:
        calls += [
            f"# --- Account audit tracker - {a} ---",
            f'module "cts_tracker_{_acct_alias(a)}" {{',
            f'  source    = "{_CTS_TRACKER_MODULE_SRC}"',
            f"  providers = {{ huaweicloud = huaweicloud.{_acct_alias(a)} }}",
            "",
            "  environment = var.environment",
            "}",
            "",
        ]

    # The 08-network-dns query-log group/stream are OWNED HERE (06 applies before
    # 07, so a fresh deploy works strictly in numeric order): this env creates
    # them, converges/archives them, and 08-network-dns attaches the resolver
    # access log to them (dns module manage_query_log_infra = false).
    dns7 = spec.get("08_DNS", {})
    owned = {
        (str(a.get("LTSGroup") or "").strip(), str(a.get("LTSStream") or "").strip())
        for a in (dns7.get("AccessLogs") or [])
        if a.get("LTSGroup") and a.get("LTSStream")
    }
    owned_ep = str((dns7.get("Settings", {}) or {}).get("enterprise_project_name") or "").strip()
    lc_lines = _logconverge_codegen(lagg_on, lagg_admin, lc_rows, lc_accounts, owned, owned_ep)

    write_generated(env_dir, (
        ("providers.generated.tf", prov),
        ("observability.generated.tf", calls),
        ("logconverge.generated.tf", lc_lines),
    ))


def _cts_notification_lines(admin: str, ops: list) -> list:
    """Wire key-event notifications into the audit module: the notifications
    list plus the SMN topic URN of the CTS-admin account's ops module (the
    topic lives there). No ops module for the admin account = no wiring; LZR-037
    rejects a spec that lists notifications in that state."""
    match = [a for a in ops if a.strip().lower() == admin.strip().lower()]
    if not match:
        return []
    return [
        "",
        "  # Key-event notification topic",
        "  cts_notifications          = var.cts_notifications",
        f"  cts_notification_topic_urn = module.ops_{_acct_alias(match[0])}.smn_topic_urn",
    ]


def _logconverge_codegen(enabled: bool, admin: str, rows: list, accounts: list,
                         owned: set = frozenset(), owned_ep: str = "") -> list:
    """Org LTS log aggregation (module 12) fan-in.

    Per source account: one lts_groups lookup (group name -> id) + one lts_streams
    lookup per LogConverge row (stream name -> id, scoped to its group). The module
    call runs on the lts_admin provider and receives the whole mapping as one
    converge_members object; the module owns the target groups/streams, converge
    configs and OBS transfers. A disabled/empty sheet emits this comment stub only
    (clearing any previous generation).

    owned = {(group, stream)} pairs whose LTS infra is CREATED here rather than
    looked up: the 08-network-dns query log. 06 applies before 07, so owning the
    group/stream here makes a fresh deploy work strictly in numeric order;
    08-network-dns attaches its resolver access log to these (manage_query_log_infra =
    false). All other rows keep hard lookups on purpose - a vanished source
    stream should fail the plan loudly. owned_ep names the enterprise project
    for the owned resources (blank = default project)."""
    lines = [
        "# --- Organization log aggregation ---",
        "",
    ]
    if not enabled:
        lines.append("# LogAggregation disabled or no LogConverge rows - nothing generated.")
        return lines

    # Deterministic per-row stream lookups: lc_s<i> in sheet order.
    # members: account -> { (source_group, target_group) -> [(stream, ref, owned?)] }
    members: dict = {}
    ep_emitted = set()
    for i, r in enumerate(rows):
        acct   = str(r.get("Account") or "").strip()
        group  = str(r.get("SourceGroup") or "").strip()
        stream = str(r.get("SourceStream") or "").strip()
        if not (acct and group and stream):
            continue
        target = str(r.get("TargetGroup") or "").strip() or f"agg-{acct.lower()}-{group.lower()}"
        ds = f"lc_s{i}"
        al = _acct_alias(acct)
        is_owned = (group, stream) in owned
        if is_owned:
            ep_ref = ""
            if owned_ep:
                if al not in ep_emitted:
                    lines += [
                        f'data "huaweicloud_enterprise_project" "lc_{al}_ep" {{',
                        f"  provider = huaweicloud.{al}",
                        f'  name     = "{owned_ep}"',
                        "}",
                        "",
                    ]
                    ep_emitted.add(al)
                ep_ref = f"  enterprise_project_id = data.huaweicloud_enterprise_project.lc_{al}_ep.id"
            lines += [
                "# --- DNS query-log source ---",
                "# Note: Created before 08-network-dns attaches query logging.",
                f'resource "huaweicloud_lts_group" "{ds}_group" {{',
                f"  provider    = huaweicloud.{al}",
                f'  group_name  = "{group}"',
                "  ttl_in_days = 30",
            ] + ([ep_ref] if ep_ref else []) + [
                "}",
                "",
                f'resource "huaweicloud_lts_stream" "{ds}" {{',
                f"  provider    = huaweicloud.{al}",
                f"  group_id    = huaweicloud_lts_group.{ds}_group.id",
                f'  stream_name = "{stream}"',
            ] + ([ep_ref] if ep_ref else []) + [
                "}",
                "",
            ]
        else:
            lines += [
                f'data "huaweicloud_lts_streams" "{ds}" {{',
                f"  provider       = huaweicloud.{al}",
                f'  log_group_name = "{group}"',
                f'  name           = "{stream}"',
                "}",
                "",
            ]
        members.setdefault(acct, {}).setdefault((group, target), []).append((stream, ds, is_owned))

    for acct in accounts:
        if acct in members:
            lines += [
                f'data "huaweicloud_lts_groups" "lc_{_acct_alias(acct)}" {{',
                f"  provider = huaweicloud.{_acct_alias(acct)}",
                "}",
                "",
            ]

    lines += [
        'module "log_aggregation" {',
        f'  source    = "{_LOGAGG_MODULE_SRC}"',
        "  providers = { huaweicloud = huaweicloud.lts_admin }",
        "",
        "  enable_log_aggregation       = var.enable_log_aggregation",
        f'  account_name                 = "{admin}"',
        "  home_region                  = var.home_region",
        "  organization_id              = local.foundation.organization_id",
        f'  management_account_id        = local.foundation.accounts["{admin}"].id',
        "  archive_bucket_name          = var.archive_bucket_name",
        "  kms_archive_alias            = var.kms_archive_alias",
        "  archive_retention_days       = var.archive_retention_days",
        "  archive_cold_after_days      = var.archive_cold_after_days",
        "  converged_retention_days     = var.converged_retention_days",
        "  transfer_period              = var.transfer_period",
        "  transfer_period_unit         = var.transfer_period_unit",
        "  archive_bucket_force_destroy = var.archive_bucket_force_destroy",
        "",
        "  converge_members = {",
    ]
    for acct, groups in members.items():
        al = _acct_alias(acct)
        # owned mappings first: preserves the existing mappings order (the dns
        # row is the first mapping in the deployed state)
        ordered = sorted(groups.items(), key=lambda kv: not all(o for (_, _, o) in kv[1]))
        lines += [
            f'    "{acct}" = {{',
            f'      account_id = local.foundation.accounts["{acct}"].id',
            "      mappings = [",
        ]
        for (group, target), streams in ordered:
            all_owned = all(o for (_, _, o) in streams)
            if all_owned:
                ds0 = streams[0][1]
                lines += [
                    "        {",
                    f"          source_log_group_id   = huaweicloud_lts_group.{ds0}_group.id",
                    f'          target_log_group_name = "{target}"',
                    "          streams = [",
                ]
            else:
                lines += [
                    "        {",
                    f'          source_log_group_id   = [for g in data.huaweicloud_lts_groups.lc_{al}.groups : g.id if g.name == "{group}"][0]',
                    f'          target_log_group_name = "{target}"',
                    "          streams = [",
                ]
            for stream, ds, o in streams:
                ref = (f"huaweicloud_lts_stream.{ds}.id" if o
                       else f"data.huaweicloud_lts_streams.{ds}.streams[0].id")
                lines += [
                    "            {",
                    f"              source_log_stream_id   = {ref}",
                    f'              target_log_stream_name = "{stream}"',
                    "            },",
                ]
            lines += [
                "          ]",
                "        },",
            ]
        lines += [
            "      ]",
            "    }",
        ]
    lines += [
        "  }",
        "}",
        "",
    ]
    return lines
