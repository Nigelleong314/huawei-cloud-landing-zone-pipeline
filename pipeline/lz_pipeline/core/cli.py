"""Build orchestration: env selection, scaffold copy, check_spec, build_from_spec, main."""

import argparse
import os
import shutil
import sys
from pathlib import Path
from .helpers import _home_region, ENV_NAMES, _scalar, _truthy
from .parsing import parse_workbook
from .validation import validate
from .builders import BUILDERS
from .writer import write_env
from .emitters import _CODEGEN


_SHEET_ENV = {
    "Global":          None,
    "01_Foundation":   "01-foundation",
    "02_Finance":      "02-finance",
    "03_Identity":     "03-identity",
    "04_Perimeter":    "04-perimeter",
    "06_Observability":"06-observability",
    "05_Network":      "05-network",
    "08_DNS":          "08-network-dns",
    "09_CFW":          "09-network-cfw",
    "10_VPN":          "10-network-vpn",
    "11_SGACL":        "11-network-sgacl",
    "07_Security":     "07-security",
}



def _is_scaffold(name: str) -> bool:
    return not (name.endswith((".generated.tf", ".bak")) or
                name in ("terraform.tfvars.json", "backend.hcl", "terraform.tfstate") or
                name.startswith(".terraform"))


def _resolve_dir(base: Path, val: str) -> Path:
    """Resolve a dir flag: absolute/existing as-is, else a name under base."""
    p = Path(val)
    if p.is_absolute() or p.exists():
        return p.resolve()
    return (base / val).resolve()


def _select_envs(only: str) -> list:
    """Resolve --only into an apply-ordered subset of ENV_NAMES. Tokens match a
    full env name or its numeric prefix (e.g. '03' -> '03-identity')."""
    if not only:
        return list(ENV_NAMES)
    wanted, unknown = set(), []
    for tok in (t.strip() for t in only.split(",") if t.strip()):
        matches = [e for e in ENV_NAMES if e == tok or e.split("-", 1)[0] == tok]
        if matches:
            wanted.update(matches)
        else:
            unknown.append(tok)
    if unknown:
        print(f"unknown --only env(s): {', '.join(unknown)}", file=sys.stderr)
        print(f"valid: {', '.join(ENV_NAMES)}", file=sys.stderr)
        sys.exit(2)
    return [e for e in ENV_NAMES if e in wanted]


def _err_in_scope(err: str, selected: list) -> bool:
    for prefix, env in _SHEET_ENV.items():
        if err.startswith(prefix):
            return env is None or env in selected
    return True  # unrecognized -> keep (fail-safe)


def _copy_scaffold(src_env: Path, dst_env: Path):
    if src_env.resolve() == dst_env.resolve():
        return  # generating in place; nothing to copy
    if not src_env.exists():
        print(f"scaffold source not found: {src_env}", file=sys.stderr)
        sys.exit(2)
    dst_env.mkdir(parents=True, exist_ok=True)
    for f in src_env.iterdir():
        if f.is_file() and _is_scaffold(f.name):
            shutil.copy2(f, dst_env / f.name)


def check_spec(spec: dict, selected=None, decisions=None, warn_sink=None) -> list:
    """validate() + rule-registry errors scoped to the selected envs.

    `decisions` is the parsed decisions sidecar when one exists; it lets the
    gap-aware rules tell a declared unknown (fine) from an untracked one
    (an error). `warn_sink` collects rule warnings so the caller can count
    and render them with everything else - passing None keeps the legacy
    stderr behaviour.

    Returns the list of blocking error strings.
    """
    selected = selected or ENV_NAMES
    errs = [e for e in validate(spec) if _err_in_scope(e, selected)]

    # Platform rule registry (LZR-*): additive checks codified from the
    # platform constraints. Warnings print; in-scope errors block.
    from .. import rules as _rules
    _rules.set_decisions_context(
        declared=_rules.declared_targets(decisions) if decisions else None,
        answered=_rules.answered_targets(decisions) if decisions else None,
        loaded=decisions is not None)
    for f in _rules.run_spec_rules(spec):
        if f.severity == "error" and _err_in_scope(f.message, selected):
            errs.append(str(f))
        elif warn_sink is not None:
            warn_sink.append(str(f))
        else:
            print(f"  note {f}", file=sys.stderr)
    _rules.set_decisions_context()
    return errs


def derive_log_converge(spec: dict) -> None:
    """Fill an EMPTY 06_Observability.LogConverge table with every LZ-created
    log stream the spec already describes. Runs automatically on every build —
    the table needs no input:
      1. the org CTS stream        (AuditSettings cts_admin_account + group/stream)
      2. DNS query-log streams     (08_DNS AccessLogs, in dns_account)
      3. CFW traffic/access/attack (05_Network CloudFirewall, in hub_account)
      4. one <vpc>-flowlog per VPC (when enable_vpc_flow_logs)

    A non-empty table is curated and authoritative: left untouched (that is
    how deliberate exclusions — e.g. an isolated sandbox spoke — survive).
    """
    n5 = spec.get("05_Network") or {}
    o6 = spec.get("06_Observability") or {}
    settings = n5.get("Settings") or {}
    if not _truthy((o6.get("LogAggregation") or {}).get("enable_log_aggregation")):
        return
    rows = o6.setdefault("LogConverge", [])
    if rows:
        return

    def add(account, group, stream):
        account, group, stream = (str(x or "").strip() for x in (account, group, stream))
        if account and group and stream:
            rows.append({"Enabled": "TRUE", "Account": account, "SourceGroup": group,
                         "SourceStream": stream, "TargetGroup": None, "Description": None})

    aud = o6.get("AuditSettings") or {}
    add(aud.get("cts_admin_account"), aud.get("cts_log_group_name"), aud.get("cts_log_stream_name"))

    dns_account = ((spec.get("08_DNS") or {}).get("Settings") or {}).get("dns_account")
    for r in (spec.get("08_DNS") or {}).get("AccessLogs") or []:
        if _truthy(r.get("Enabled")):
            add(dns_account, r.get("LTSGroup"), r.get("LTSStream"))

    cfw = n5.get("CloudFirewall") or {}
    hub_account = settings.get("hub_account")
    if _truthy(cfw.get("cfw_lts_log_enable")):
        for k in ("cfw_lts_traffic_stream_name", "cfw_lts_access_stream_name",
                  "cfw_lts_attack_stream_name"):
            add(hub_account, cfw.get("cfw_lts_log_group_name"), cfw.get(k))

    if _truthy(settings.get("enable_vpc_flow_logs")):
        vpcs = [(hub_account, v.get("VPCName")) for v in (n5.get("HubVPCs") or [])]
        vpcs += [(v.get("AccountName"), v.get("VPCName")) for v in (n5.get("SpokeVPCs") or [])]
        for account, vpc in vpcs:
            vpc = str(vpc or "").strip()
            if vpc:
                add(account, f"{vpc}-flowlog", f"{vpc}-flowlog")


def build_from_spec(spec: dict, envs_dir: Path, scaffold_dir, selected, ak: str, sk: str,
                    customer: str = ""):
    """Write tfvars/backends/secrets + generated fan-outs for the selected envs.

    The caller is responsible for having run check_spec() first.
    """
    # Tree identity: every env tree is stamped with the customer it was built
    # for (.lz-customer); a spec carrying a different customer refuses to build
    # into it. Empty customer (legacy workbook path) skips the check.
    if customer:
        marker = envs_dir / ".lz-customer"
        if marker.exists():
            have = marker.read_text(encoding="utf-8-sig").strip()
            if have != customer:
                raise SystemExit(f"customer mismatch: spec is for {customer!r} but "
                                 f"{envs_dir.name} is stamped {have!r} - wrong envs dir?")
        else:
            envs_dir.mkdir(parents=True, exist_ok=True)
            marker.write_text(customer + "\n", encoding="utf-8", newline="\n")

    derive_log_converge(spec)
    g = spec.get("Global", {}).get("Settings", {})
    region = _home_region(g)
    state_bucket = _scalar(g, "state_bucket_name", "")

    for env_name in selected:
        env_dir = envs_dir / env_name
        if scaffold_dir is not None:
            _copy_scaffold(scaffold_dir / env_name, env_dir)
        write_env(env_dir, BUILDERS[env_name](spec), state_bucket, ak, sk, region, env_name)
        if env_name in _CODEGEN:
            _CODEGEN[env_name](env_dir, spec)
        print(f"wrote {env_dir}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("workbook")
    p.add_argument("--envs-dir", default=None,
                   help="Target output dir (default: envs/ next to the workbook). "
                        "A bare name is resolved next to the workbook.")
    p.add_argument("--scaffold-dir", default=None,
                   help="Copy static scaffold (main.tf, variables.tf, ...) from this dir's "
                        "matching env subdirs into the target before generating. "
                        "Use when creating a NEW env tree (the repo ships one at "
                        "terraform/scaffold). Bare name resolved next to the workbook.")
    p.add_argument("--only", default=None,
                   help="Comma-separated subset of envs to generate (full name or numeric "
                        "prefix, e.g. '00,01,02,03'). Default: all envs.")
    args = p.parse_args()

    wb_path = Path(args.workbook).resolve()
    if not wb_path.exists():
        print(f"workbook not found: {wb_path}", file=sys.stderr)
        sys.exit(2)

    anchor = wb_path.parent
    envs_dir = _resolve_dir(anchor, args.envs_dir) if args.envs_dir else (anchor / "envs")
    scaffold_dir = _resolve_dir(anchor, args.scaffold_dir) if args.scaffold_dir else None
    selected = _select_envs(args.only)

    # Without a scaffold source, the target env dirs must already exist (in-place).
    if scaffold_dir is None and not envs_dir.exists():
        print(f"envs dir not found: {envs_dir} (pass --scaffold-dir to create a new tree)", file=sys.stderr)
        sys.exit(2)

    ak = os.environ.get("HW_ACCESS_KEY", "")
    sk = os.environ.get("HW_SECRET_KEY", "")
    if not ak or not sk:
        print("WARNING: HW_ACCESS_KEY / HW_SECRET_KEY not set in environment.",
              "secrets.auto.tfvars.json will be skipped.", file=sys.stderr)

    spec = parse_workbook(wb_path)
    errs = check_spec(spec, selected)
    if errs:
        print("Validation errors:", file=sys.stderr)
        for e in errs:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)

    build_from_spec(spec, envs_dir, scaffold_dir, selected, ak, sk)

    print(f"done. ({len(selected)} env(s): {', '.join(selected)})")
