"""lz_app HTTP server: JSON API + single-page UI + pipeline job runner.

Local tool: binds 127.0.0.1, no auth. All pipeline work is delegated to the
workspace's real entry points (lz_pipeline verbs, lzctl.py - untouched -,
verify_pipeline.py) via subprocesses, so the app can never drift from the CLI
behaviour. Mutating cloud operations (a real apply) require an explicit
confirm flag; everything defaults to dry-run.
"""

import argparse
import json
import os
import secrets
import subprocess
import sys
import tempfile
import threading
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

# Per-process CSRF token: injected into the served page, required on every
# mutating request. The custom header also forces a CORS preflight, so a
# malicious website cannot fire simple cross-origin POSTs at localhost.
TOKEN = secrets.token_urlsafe(24)

from . import find_workspace, wire, __version__
from . import workbook_io

STATE = {
    "workspace": None,   # Path
    "ir": None,          # current spec IR (dict)
    "source": None,      # where it was loaded from
    "file": None,        # current file NAME inside the spec folder (save target)
}
JOBS = {}                # id -> {"verb", "status", "output", "rc"}
HIDDEN_ENVS = {"12-workloads"}   # hand-managed; planned/applied manually, not via the app


# ── Spec file folder (lz_spec/): the UI picks files by NAME, never by path ──

def spec_dir() -> Path:
    """specs/ in the workspace (created on demand); legacy lz_spec/ honored."""
    ws = STATE["workspace"]
    legacy = ws / "lz_spec"
    if legacy.is_dir() and not (ws / "specs").is_dir():
        return legacy
    d = ws / "specs"
    d.mkdir(exist_ok=True)
    return d


def spec_files():
    """Spec files offered in the UI dropdown: json spec IRs in lz_spec/.
    The json IR is the CANONICAL store; Excel is a generated artifact
    (gen_workbook.py), never an input here."""
    out = []
    for p in sorted(spec_dir().iterdir()):
        n = p.name
        if not p.is_file() or p.suffix.lower() != ".json":
            continue
        if ".bak" in n.lower() or n.endswith(".schema.json"):
            continue
        out.append({"name": n, "mtime": int(p.stat().st_mtime)})
    return out


def spec_path(name: str) -> Path:
    """Resolve a bare file name inside the spec folder; reject path tricks."""
    if not name or name != Path(name).name or name.startswith("~$"):
        raise ValueError(f"invalid spec file name: {name!r}")
    return spec_dir() / name


# ── Decisions: the questionnaire gate, rendered instead of hand-edited ──────
#
# `lzctl assess` writes lz.spec.<c>.decisions.json beside the spec, and
# `lzctl build` refuses to run while an OPEN item lacks a resolution. Until
# now the only way to record one was to hand-edit that JSON - the exact thing
# every other part of this tool tells people not to do. These endpoints make
# it a form: the app writes ONLY `resolution` blocks, never a decision itself
# (the set is hash-bound into the spec's provenance).

_RESOLUTION_STATUSES = ("ANSWERED", "ACCEPTED_DEFAULT")


def decisions_path():
    """The decisions file for the loaded spec, or None.

    Located by the spec's own provenance (which names its decisions file), so
    a renamed or copied spec still finds its lineage - same rule the build
    gate uses.
    """
    ir, name = STATE["ir"], STATE["file"]
    if ir is None:
        return None
    prov = ir.get("provenance") or {}
    src = STATE["source"]
    base = Path(src) if src and src not in ("(new)",) and Path(src).is_absolute() \
        else (spec_dir() / name if name else None)
    if base is None:
        return None
    p = base.with_name(prov.get("decisions_file") or (base.stem + ".decisions.json"))
    return p if p.exists() else None


def decisions_payload():
    p = decisions_path()
    gaps = []
    try:
        from lz_pipeline.rules import placeholder_findings
        gaps = placeholder_findings((STATE["ir"] or {}).get("sheets") or {})
    except Exception:                                             # noqa: BLE001
        pass
    if p is None:
        return {"available": False, "file": None, "items": [], "counts": {},
                "gaps": gaps,
                "note": "This spec has no decisions file beside it — it did not come "
                        "from `lzctl assess`, so there is no questionnaire gate to work."}
    doc = json.loads(p.read_text(encoding="utf-8"))
    items = doc.get("items") or []
    resolved = sum(1 for i in items
                   if i.get("state") == "OPEN" and isinstance(i.get("resolution"), dict))
    counts = {
        "open": sum(1 for i in items if i.get("state") == "OPEN"),
        "defaulted": sum(1 for i in items if i.get("state") == "DEFAULTED"),
        "answered": sum(1 for i in items if i.get("state") == "ANSWERED"),
        "resolved": resolved,
    }
    counts["blocking"] = counts["open"] - resolved
    return {"available": True, "file": p.name, "customer": doc.get("customer"),
            "source_file": doc.get("source_file"), "items": items,
            "counts": counts, "gaps": gaps}


def resolve_decision(ref: str, status: str, approved_by: str, reason: str):
    """Write one item's `resolution`; touch nothing else.

    The decision itself (ref/state/question/targets/default_if_silent) is
    hashed into the spec's provenance - editing any of it blocks the build.
    So this writes the one editable field and rewrites the file with the same
    formatting `lzctl assess` used.
    """
    p = decisions_path()
    if p is None:
        raise ValueError("no decisions file for the loaded spec")
    if status not in _RESOLUTION_STATUSES:
        raise ValueError(f"status must be one of {' / '.join(_RESOLUTION_STATUSES)}")
    if not approved_by.strip() or not reason.strip():
        raise ValueError("approved_by and reason are both required - a resolution "
                         "records WHO decided and WHY, or it is not auditable")
    doc = json.loads(p.read_text(encoding="utf-8"))
    for item in doc.get("items") or []:
        if item.get("ref") == ref:
            item["resolution"] = {"status": status,
                                  "approved_by": approved_by.strip(),
                                  "reason": reason.strip()}
            p.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
                         encoding="utf-8")
            return item
    raise ValueError(f"no decision {ref!r} in {p.name}")


def default_envs_dir() -> str:
    """Default envs tree: the neutral example first; a customer tree is always
    an explicit choice, never the default."""
    for d in ("envs", "envs-example", "terraform/envs-example",
              "terraform/envs-example"):
        if (STATE["workspace"] / d).is_dir():
            return d
    return "envs"


# ────────────────────────────────────────────────────────────────────────────
# Schema / pipeline access (in-process, read-only)
# ────────────────────────────────────────────────────────────────────────────

# Table/sheet classification shown as pills in the editor. Anything not listed
# is "mandatory" (free/core landing-zone config). "optional" = billable
# service, leave empty if not needed. "reserved" = schema placeholder, no
# input accepted. "auto" = derived on build when left empty (your rows win).
BADGES = {
    ("05_Network", "EIPs"): "optional",
    ("05_Network", "NATGateways"): "optional",
    ("05_Network", "ELBs"): "optional",
    ("05_Network", "SNATRules"): "optional",
    ("05_Network", "DNATRules"): "optional",
    ("05_Network", "RAMSharePrincipals"): "auto",
    ("06_Observability", "LogConverge"): "auto",
    ("08_DNS", "PublicZones"): "optional",
    ("07_Security", "WAF"): "optional",
    ("07_Security", "WAFDomains"): "optional",
    ("07_Security", "AntiDDoS"): "optional",
    ("07_Security", "SecMasterModules"): "optional",
    ("07_Security", "AlertRules"): "optional",
    ("11_SGACL", "NetworkACLs"): "reserved",
    ("11_SGACL", "ACLRules"): "reserved",
}
SHEET_BADGES = {"07_Security": "optional", "08_DNS": "optional", "09_CFW": "optional",
                "10_VPN": "optional", "11_SGACL": "optional"}
SHEET_LABELS = {"_meta": "File Info"}
BADGE_NOTES = {
    "optional": "Billable service — leave empty if not needed",
    "reserved": "Not implemented yet — no input accepted (rows marked Enabled fail validation)",
    "auto": "Filled in automatically at build time when left empty; rows you add take precedence",
}

# Non-input module items still shown in the UI (fixed by the platform).
FIXED_NOTES = {
    "05_Network": [
        {"after": "HubERAttachments", "title": "ERRouteTables (fixed — no input)",
         "rows": [["er-inbound",  "All hub and spoke VPC attachments associate automatically; a static route 0.0.0.0/0 sends traffic to the firewall"],
                  ["er-outbound", "The firewall associates automatically; VPC ranges propagate automatically; 0.0.0.0/0 goes to the SNAT VPC attachment (Settings.snat_vpc_attachment)"],
                  ["er-hybrid",   "VPN and Direct Connect attachments associate here (10_VPN); 0.0.0.0/0 to the firewall keeps on-premises traffic inspected"]],
         "note": "The whole inspection topology is wired automatically from these three tables. 10_VPN references them by name."},
        {"after": "CloudFirewall", "title": "east_west_firewall_mode (fixed — no input)",
         "rows": [["er", "The firewall gets its own Enterprise Router attachment; traffic is steered through the fixed route tables above"]],
         "note": ""},
    ],
    "06_Observability": [
        {"after": "LogAggregation", "title": "lts_admin_account (derived — no input)",
         "rows": [["From 01_Foundation", "The DelegatedAdmin of service.LTS in TrustedServices — log targets and the archive bucket deploy there"]],
         "note": "Blank archive_bucket_name / kms_archive_alias default to the {account-name} pattern."},
        {"after": "LogConverge", "title": "LogConverge fills itself in (no input needed)",
         "rows": [["CTS audit stream", "From AuditSettings cts_admin_account + cts_log_group/stream_name"],
                  ["DNS query logs",   "From the 08_DNS AccessLogs rows, in dns_account"],
                  ["Firewall streams", "Traffic, access, and attack logs from 05_Network CloudFirewall, in hub_account"],
                  ["VPC flow logs",    "One <vpc>-flowlog per hub and spoke VPC (when enable_vpc_flow_logs is on)"]],
         "note": "Filled in on every build while the table above is empty. Add rows only to curate the list: "
                 "extra application streams, or to leave a source out (once you add rows, your table takes over)."},
    ],
}

# Fields only rendered when another field of the same table has a value.
CONDITIONAL = {
    ("05_Network", "CloudFirewall"): {
        "fields": ["cfw_period_unit", "cfw_period", "cfw_auto_renew"],
        "when": ["cfw_charging_mode", "subscription"],
    },
}


def _fk_sources(val):
    """Normalize an FK map value to a list of [sheet, table, column(, prefix)]."""
    srcs = val if isinstance(val[0], (tuple, list)) else (val,)
    return [list(s) for s in srcs]


def schema_meta():
    from lz_spec import schema as wb_schema
    from lz_spec import gen_template as gt
    sheets = []
    for s in wb_schema.SHEETS:
        if s.name in wb_schema.INFO_SHEETS:
            continue
        tables = []
        for t in s.tables:
            if t.kind == "scalar":
                fields = []
                for kv in t.rows:
                    f = {"name": kv.name, "type": kv.type, "sample": str(kv.sample or ""),
                         "description": kv.description}
                    fk = gt.SCALAR_FK.get((s.name, t.name, kv.name))
                    if fk:
                        f["fk"] = _fk_sources(fk)
                    fields.append(f)
                tab = {"name": t.name, "kind": t.kind,
                       "description": t.description, "fields": fields}
                cond = CONDITIONAL.get((s.name, t.name))
                if cond:
                    tab["conditional"] = cond
            elif t.kind == "list-single":
                tab = {"name": t.name, "kind": t.kind, "description": t.description}
            else:
                cols = []
                if not t.mandatory and not any(c[0] == "Enabled" for c in t.columns):
                    cols.append({"name": "Enabled", "type": "bool", "description": "Include this row"})
                for name, typ, desc in t.columns:
                    c = {"name": name, "type": typ, "description": desc}
                    enum = gt.ENUM_COLS.get((s.name, t.name, name))
                    if enum:
                        c["enum"] = enum.split(",")
                    fk = gt.FK_COLS.get((s.name, t.name, name))
                    if fk:
                        c["fk"] = _fk_sources(fk)
                    hint = gt.MULTI_FK.get((s.name, t.name, name))
                    if hint:
                        c["fk_hint"] = _fk_sources(hint)
                    # first sample row supplies the placeholder
                    if t.sample_rows and isinstance(t.sample_rows[0], dict):
                        sv = t.sample_rows[0].get(name)
                        if sv not in (None, "", False):
                            c["sample"] = str(sv)
                    cols.append(c)
                tab = {"name": t.name, "kind": t.kind,
                       "description": t.description, "columns": cols}
            badge = BADGES.get((s.name, t.name))
            if badge:
                tab["badge"] = badge
                tab["badge_note"] = BADGE_NOTES[badge]
            tables.append(tab)
        sh = {"name": s.name, "description": s.description, "tables": tables}
        if s.name in SHEET_LABELS:
            sh["label"] = SHEET_LABELS[s.name]
        if s.name in SHEET_BADGES:
            sh["badge"] = SHEET_BADGES[s.name]
            sh["badge_note"] = BADGE_NOTES[SHEET_BADGES[s.name]]
        if s.name in FIXED_NOTES:
            sh["fixed_notes"] = FIXED_NOTES[s.name]
        sheets.append(sh)
    return {"schema_version": wb_schema.SCHEMA_VERSION, "sheets": sheets}


def run_validate(ir):
    from lz_pipeline import schema_check, rules
    from lz_pipeline.core.cli import check_spec
    errors, warnings = schema_check.check(ir)
    sheets = ir.get("sheets", {})
    sem = check_spec(sheets)  # validate() + LZR rule errors, unscoped
    warns = [str(f) for f in rules.run_spec_rules(sheets) if f.severity == "warn"]
    return {"errors": errors + sem, "warnings": warnings + warns}


# ────────────────────────────────────────────────────────────────────────────
# Jobs (subprocess passthrough to the real CLIs)
# ────────────────────────────────────────────────────────────────────────────

def job_argv(verb: str, args: dict):
    ws = STATE["workspace"]
    envs = args.get("envs_dir")
    if not envs:
        raise ValueError("envs_dir is required")
    envs_abs = str((ws / envs) if not Path(envs).is_absolute() else Path(envs))
    py = [sys.executable, "-X", "utf8"]
    lzctl = [*py, "-m", "lz_pipeline.lzctl"]
    if verb == "build":
        ir_tmp = Path(tempfile.gettempdir()) / "lz_app-current.spec.json"
        ir_tmp.write_text(json.dumps(STATE["ir"], indent=2), encoding="utf-8")
        argv = [*py, "-m", "lz_pipeline", "build", "--ir", str(ir_tmp), "--envs-dir", envs_abs]
        if args.get("scaffold_dir"):
            argv += ["--scaffold-dir", str(ws / args["scaffold_dir"])]
        return argv, str(ws)
    if verb == "verify":
        which = args.get("check", "all")
        return [*py, "-m", "lz_spec.verify_pipeline", which], str(ws / "lz_spec")
    if verb == "export":
        # Combined job, run as sequential STEPS in one console stream. The UI
        # picks which components to produce via args.include (default: all):
        #   docs     - doc set (ipam / config book / checklist-if-states) -> <out>/docs
        #   workbook - the Excel LLD workbook, generated INTO the artifact by the
        #              package step from that profile's own spec IR
        #   package  - the Terraform artifact -> <out>/artifact
        # Everything is namespaced per envs tree so two profiles never mix.
        include = set(args.get("include") or ["docs", "workbook", "package"])
        name = Path(envs_abs).name.removeprefix("envs-")
        out = ws / "dist" / name
        steps = []
        if "docs" in include:
            docs_argv = [*lzctl, "docs", "--envs-dir", envs_abs,
                         "--out-dir", str(out / "docs"),
                         "--customer", args.get("customer", "")]
            if args.get("states_dir"):
                docs_argv += ["--states-dir", args["states_dir"]]
            steps.append(docs_argv)
        # Standalone workbook only when no artifact is being built - otherwise the
        # package step generates it. Never write into a customer's handover-docs:
        # the loaded spec need not be that customer's.
        if "workbook" in include and "package" not in include and STATE.get("file"):
            (out / "docs").mkdir(parents=True, exist_ok=True)
            steps.append([*py, "-m", "lz_pipeline.tools.gen_workbook",
                          "--ir", str(spec_dir() / STATE["file"]),
                          "-o", str(out / "docs" / "landing-zone-spec.xlsx")])
        if "package" in include:
            # profile follows the selected envs tree (envs-<name> -> <name>.json);
            # workspace profiles/ first, then the packaged example profile -
            # never a customer default
            import lz_pipeline as _lzp
            pkg_profiles = Path(_lzp.__file__).parent / "profiles"
            derived = None
            for cand in (ws / "profiles" / f"{name}.json",
                         ws / f"lz_pipeline/profiles/{name}.json",
                         pkg_profiles / "example.json"):
                if cand.exists():
                    derived = str(cand)
                    break
            profile = args.get("profile", derived)
            target = args.get("target") or str(out / "artifact")
            pkg = [*py, "-m", "lz_pipeline.export_v2", "--profile", str(profile),
                   "--target", target, "--version", args.get("version", "0.0.0-dev"),
                   "--compat"]
            if "workbook" not in include:
                pkg.append("--no-workbook")
            steps.append(pkg)
        if not steps:
            raise ValueError("nothing selected to export")
        return steps, str(ws)
    if verb in ("preflight", "plan", "apply", "drift"):
        argv = [*lzctl, verb, "--envs-dir", envs_abs]
        if verb in ("plan", "apply"):
            sel = args.get("envs") or []
            argv += [",".join(sel)] if sel else ["--all"]
        if verb == "drift":
            sel = args.get("envs") or []
            if sel:
                argv += [",".join(sel)]
        if verb == "apply":
            if not args.get("confirm"):
                argv += ["--dry-run"]
            argv += ["--yes"]
            if args.get("allow_destroy"):
                argv += ["--allow-destroy"]
        elif args.get("dry_run") and verb == "plan":
            argv += ["--dry-run"]
        if verb == "drift" and args.get("report"):
            argv += ["--report", str(ws / "drift-report.md")]
        return argv, str(ws)
    raise ValueError(f"unknown verb {verb!r}")


def _backend_creds(envs_dir: str) -> dict:
    """AWS_* env vars for the OBS state backend, loaded from the first env's
    secrets.auto.tfvars.json (master AK/SK - same for every env). Values go
    straight into the subprocess environment and are NEVER logged/returned to
    the browser. {} when no secrets file exists (preflight then reports it)."""
    ws = STATE["workspace"]
    envs = (ws / envs_dir) if not Path(envs_dir).is_absolute() else Path(envs_dir)
    if envs.exists():
        for env_dir in sorted(envs.iterdir()):
            sec = env_dir / "secrets.auto.tfvars.json"
            if env_dir.is_dir() and sec.exists():
                try:
                    s = json.loads(sec.read_text(encoding="utf-8"))
                    ak, sk = s.get("master_access_key"), s.get("master_secret_key")
                    if ak and sk:
                        return {"AWS_ACCESS_KEY_ID": ak, "AWS_SECRET_ACCESS_KEY": sk,
                                "AWS_REQUEST_CHECKSUM_CALCULATION": "when_required",
                                "AWS_RESPONSE_CHECKSUM_VALIDATION": "when_required"}
                except (ValueError, OSError):
                    continue
    return {}


def start_job(verb, args):
    args = dict(args or {})
    creds_in = args.pop("creds", None) or {}
    override = {}
    if creds_in.get("ak") and creds_in.get("sk"):
        override = {"AWS_ACCESS_KEY_ID": creds_in["ak"],
                    "AWS_SECRET_ACCESS_KEY": creds_in["sk"],
                    "AWS_REQUEST_CHECKSUM_CALCULATION": creds_in.get("req_checksum") or "when_required",
                    "AWS_RESPONSE_CHECKSUM_VALIDATION": creds_in.get("resp_checksum") or "when_required"}
    ret, cwd = job_argv(verb, args)
    steps = ret if isinstance(ret[0], list) else [ret]   # multi-step (export) or single
    jid = uuid.uuid4().hex[:12]

    def _label(argv):
        return " ".join(argv[3:] if len(argv) > 2 and argv[2] == "utf8" else argv)

    while len(JOBS) > 50:   # long sessions must not leak job output forever
        oldest = next(iter(JOBS))
        if JOBS[oldest]["status"] == "running":
            break
        del JOBS[oldest]
    JOBS[jid] = {"verb": verb, "status": "running", "output": "", "rc": None}

    def _run():
        try:
            # PYTHONUNBUFFERED: python children block-buffer stdout when piped,
            # which would batch the whole log until exit; line-buffer instead so
            # the UI console streams progress live (inherited by grandchildren).
            # Backend creds are auto-loaded from the envs' secrets files so
            # lzctl verbs (preflight/plan/apply/drift) work from the app.
            env = {**os.environ, "PYTHONUNBUFFERED": "1",
                   **(_backend_creds(args.get("envs_dir") or default_envs_dir()) or {}),
                   **override}
            def _step_name(a):
                if "-m" in a:
                    return a[a.index("-m") + 1]
                s = next((x for x in a if x.endswith(".py")), None)
                return Path(s).name if s else _label(a)

            for i, argv in enumerate(steps):
                if len(steps) > 1:
                    JOBS[jid]["output"] += f"== step {i + 1}/{len(steps)}: {_step_name(argv)} ==\n"
                p = subprocess.Popen(argv, cwd=cwd, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True,
                                     encoding="utf-8", errors="replace", env=env)
                for line in p.stdout:
                    JOBS[jid]["output"] += line
                    if len(JOBS[jid]["output"]) > 400_000:
                        JOBS[jid]["output"] = JOBS[jid]["output"][-300_000:]
                p.wait()
                if p.returncode != 0:
                    JOBS[jid]["rc"] = p.returncode
                    JOBS[jid]["status"] = f"failed ({p.returncode})"
                    if len(steps) > 1:
                        JOBS[jid]["output"] += (f"\n== RESULT: FAILED at step {i + 1}/{len(steps)} "
                                                f"({_step_name(argv)}, exit {p.returncode}) ==\n")
                    return
            if len(steps) > 1:
                JOBS[jid]["output"] += f"\n== RESULT: ALL {len(steps)} STEP(S) COMPLETE ==\n"
            JOBS[jid]["rc"] = 0
            JOBS[jid]["status"] = "done"
        except Exception as e:                                    # noqa: BLE001
            JOBS[jid]["status"] = "error"
            JOBS[jid]["output"] += f"\n{e}"
    threading.Thread(target=_run, daemon=True).start()
    return jid


# ────────────────────────────────────────────────────────────────────────────
# HTTP
# ────────────────────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *a):
        pass

    def _send(self, obj, code=200, ctype="application/json"):
        body = obj if isinstance(obj, bytes) else json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        try:
            if self.path in ("/", "/index.html"):
                html = (Path(__file__).parent / "static" / "index.html").read_bytes()
                html = html.replace(b"__LZ_TOKEN__", TOKEN.encode("ascii"))
                return self._send(html, ctype="text/html; charset=utf-8")
            if self.path == "/api/meta":
                return self._send({"version": __version__,
                                   "workspace": str(STATE["workspace"]),
                                   "source": STATE["source"],
                                   "file": STATE["file"],
                                   "envs_dir": default_envs_dir(),
                                   "loaded": STATE["ir"] is not None})
            if self.path == "/api/spec/files":
                return self._send({"dir": str(spec_dir()), "files": spec_files()})
            if self.path.startswith("/api/envs"):
                from urllib.parse import parse_qs, urlparse
                q = parse_qs(urlparse(self.path).query)
                envs_dir = (q.get("dir") or [default_envs_dir()])[0]
                envs = STATE["workspace"] / envs_dir
                # apply order per deps.json (same fallback as lzctl.apply_order)
                order = None
                deps = envs / "deps.json"
                if deps.exists():
                    order = json.loads(deps.read_text(encoding="utf-8")).get("apply_order")
                if not order:
                    import re as _re
                    order = sorted(p.name for p in envs.iterdir()
                                   if p.is_dir() and _re.match(r"^\d{2}-", p.name))
                # hand-managed envs are operated outside the app (interactive-only
                # variables, own local modules) - never offered in the UI
                order = [e for e in order if (envs / e).is_dir() and e not in HIDDEN_ENVS]
                return self._send({"envs": order})
            if self.path == "/api/schema":
                return self._send(schema_meta())
            if self.path == "/api/decisions":
                if STATE["ir"] is None:
                    return self._send({"error": "no spec loaded"}, 404)
                return self._send(decisions_payload())
            if self.path == "/api/spec":
                if STATE["ir"] is None:
                    return self._send({"error": "no spec loaded"}, 404)
                return self._send(STATE["ir"])
            if self.path.startswith("/api/jobs/"):
                j = JOBS.get(self.path.rsplit("/", 1)[1])
                return self._send(j or {"error": "no such job"}, 200 if j else 404)
            if self.path == "/api/jobs":
                return self._send({k: {kk: v[kk] for kk in ("verb", "status", "rc")}
                                   for k, v in JOBS.items()})
            return self._send({"error": "not found"}, 404)
        except Exception as e:                                    # noqa: BLE001
            return self._send({"error": str(e)}, 500)

    def do_POST(self):
        try:
            origin = self.headers.get("Origin")
            if origin and urlsplit(origin).hostname not in ("127.0.0.1", "localhost", "::1"):
                return self._send({"error": "cross-origin request rejected"}, 403)
            if self.headers.get("X-LZ-Token") != TOKEN:
                return self._send({"error": "missing or stale X-LZ-Token - reload the app page"}, 403)
            ws = STATE["workspace"]
            if self.path == "/api/spec/new":
                b = self._body()
                name = (b.get("name") or "").strip()
                if name:                       # UI path: a NAME inside lz_spec/
                    if name.lower().endswith(".xlsx"):
                        return self._send({"error": "the config store is json - Excel is a "
                                           "generated artifact, not an input"}, 400)
                    if not name.lower().endswith(".json"):
                        name += ".json"
                    p = spec_path(name)
                    if p.exists():
                        return self._send({"error": f"{name} already exists - pick it in the dropdown"}, 400)
                from lz_spec import schema as wb_schema
                customer = b.get("customer") or (Path(name).stem if name else "")
                ir = {"format": "lz-spec-ir/1", "schema_version": wb_schema.SCHEMA_VERSION,
                      "customer": customer, "sheets": {}}
                STATE["ir"] = workbook_io.normalize_ir(ir)
                STATE["source"] = "(new)"
                STATE["file"] = name or None
                return self._send({"ok": True, "file": STATE["file"]})
            if self.path == "/api/spec/load":
                b = self._body()
                if b.get("name"):              # UI path: a NAME inside lz_spec/
                    p = spec_path(b["name"])
                    STATE["file"] = b["name"]
                else:                          # CLI/tests: an explicit path
                    p = Path(b["path"])
                    if not p.is_absolute():
                        p = ws / p
                    STATE["file"] = p.name if p.parent.resolve() == spec_dir().resolve() else None
                if p.suffix.lower() == ".xlsx":
                    return self._send({"error": "the config store is json - Excel is a "
                                       "generated artifact, not an input"}, 400)
                from lz_pipeline import model
                ir = model.load(p)
                STATE["ir"] = workbook_io.normalize_ir(ir)
                STATE["source"] = str(p)
                return self._send({"ok": True, "file": STATE["file"],
                                   "warnings": ir.get("_import_warnings", [])})
            if self.path == "/api/spec":
                STATE["ir"] = self._body()
                return self._send({"ok": True})
            if self.path == "/api/spec/save":
                b = self._body()
                name = (b.get("name") or "").strip()
                if name or not b.get("path"):  # UI path: NAME in lz_spec/ (default: current file)
                    name = name or STATE["file"]
                    if not name:
                        return self._send({"error": "no file name - use New or pick a file first"}, 400)
                    if name.lower().endswith(".xlsx"):
                        return self._send({"error": "the config store is json - the Excel workbook "
                                           "is generated into the artifact (docs job)"}, 400)
                    if not name.lower().endswith(".json"):
                        name += ".json"
                    p = spec_path(name)
                else:                          # CLI/tests: an explicit path
                    p = Path(b["path"])
                    if not p.is_absolute():
                        p = ws / p
                    p = p.resolve()
                    if not p.is_relative_to(ws.resolve()):
                        return self._send({"error": "save path must stay inside the workspace"}, 400)
                    if p.suffix.lower() != ".json":
                        return self._send({"error": "the config store is json"}, 400)
                if p.suffix.lower() == ".xlsx":
                    return self._send({"error": "the config store is json - the Excel workbook "
                                       "is generated by the export job, not saved here"}, 400)
                from lz_pipeline import model
                model.save(STATE["ir"], p)
                notes = []
                if p.parent.resolve() == spec_dir().resolve():
                    STATE["file"] = p.name
                return self._send({"ok": True, "path": str(p), "file": STATE["file"],
                                   "notes": notes})
            if self.path == "/api/spec/validate":
                return self._send(run_validate(STATE["ir"]))
            if self.path == "/api/decisions/resolve":
                b = self._body()
                try:
                    item = resolve_decision(b.get("ref") or "", b.get("status") or "",
                                            b.get("approved_by") or "", b.get("reason") or "")
                except ValueError as e:
                    return self._send({"error": str(e)}, 400)
                return self._send({"ok": True, "item": item,
                                   "decisions": decisions_payload()})
            if self.path == "/api/job":
                b = self._body()
                jid = start_job(b["verb"], b.get("args") or {})
                return self._send({"job": jid})
            return self._send({"error": "not found"}, 404)
        except Exception as e:                                    # noqa: BLE001
            return self._send({"error": str(e)}, 500)


def serve(workspace=None, host="127.0.0.1", port=8600, open_browser=False):
    if host not in ("127.0.0.1", "localhost", "::1") and             not os.environ.get("LZ_APP_ALLOW_REMOTE"):
        raise SystemExit(
            f"refusing to bind {host}: the app serves its CSRF token to anyone "
            "who can GET the page, so a non-loopback bind means unauthenticated "
            "remote job execution. Set LZ_APP_ALLOW_REMOTE=1 only behind real "
            "network controls.")
    ws = find_workspace(workspace)
    wire(ws)
    STATE["workspace"] = ws
    httpd = ThreadingHTTPServer((host, port), Handler)
    if open_browser:
        threading.Timer(0.5, webbrowser.open,
                        args=(f"http://{host}:{httpd.server_address[1]}/",)).start()
    return httpd


def main(argv=None):
    ap = argparse.ArgumentParser(prog="lz-app", description="Landing-zone pipeline UI")
    ap.add_argument("--workspace", help="folder containing lz_pipeline/ and lz_spec/")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8600)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args(argv)
    httpd = serve(args.workspace, args.host, args.port, open_browser=not args.no_browser)
    print(f"lz-app {__version__} - workspace {STATE['workspace']}")
    print(f"serving on http://{args.host}:{httpd.server_address[1]}/  (Ctrl+C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
