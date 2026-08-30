"""lzctl - landing-zone runner.

Wraps the operational lifecycle around the generated Terraform envs: ordered
plans/applies with lock + state backup + plan triage, drift sweeps, import
helper, and preflight for the environment mistakes that otherwise surface as
cryptic mid-apply errors.

Standalone by design: stdlib only, no pipeline imports - this file (plus
plan_triage.py next to it and the envs tree's deps.json) ships inside the
customer handover artifact. Pipeline-side verbs (build/validate/docs) exist
only where the pipeline is installed and say so otherwise.

Usage (lifecycle order):
    lzctl intake       FILLED_QUESTIONNAIRE.xlsx [-o dump.json]
    lzctl assess       DUMP.json --customer <slug> [--workspace <dir>] [--force]
    lzctl validate     SPEC.json            (alias: spec-validate)
    lzctl build        --ir SPEC.json --envs-dir <envs> [--scaffold-dir <dir>]
    lzctl preflight    --envs-dir <envs>
    lzctl plan         --envs-dir <envs> [ENV[,ENV...] | --all] [--dry-run]
    lzctl apply        --envs-dir <envs> [ENV[,ENV...] | --all] [--dry-run]
                       [--allow-destroy] [--yes] [--destroy-confirm ENV]
    lzctl verify       --envs-dir <envs> [ENV[,ENV...]] [--report out.md]
    lzctl report       --envs-dir <envs> [--out <dir>]
    lzctl drift        --envs-dir <envs> [ENV[,ENV...]] [--report out.md]
    lzctl adopt        --envs-dir <envs> ENV ADDRESS CLOUD_ID
    lzctl state-backup --envs-dir <envs> [ENV | --all]
    lzctl triage       PLAN_JSON [...]
    lzctl who-changed  RESOURCE_NAME
    lzctl order        --envs-dir <envs>
    lzctl check        [CHECK]              (regression harness)

Exit codes follow terraform's plan convention where relevant:
0 ok / no changes, 2 changes present, 3 destructive changes present.
"""

import argparse
import datetime
import getpass
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

# Terraform emits box-drawing/arrow characters; a piped stdout on Windows
# defaults to cp1252 and would raise UnicodeEncodeError mid-stream.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import plan_triage  # shipped next to lzctl.py in the artifact
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
    import plan_triage

REQUIRED_ENV = {
    "AWS_ACCESS_KEY_ID": None,
    "AWS_SECRET_ACCESS_KEY": None,
    "AWS_REQUEST_CHECKSUM_CALCULATION": "when_required",
    "AWS_RESPONSE_CHECKSUM_VALIDATION": "when_required",
}
MIN_TF = (1, 6, 3)
LOCK_STALE_S = 2 * 3600
PRICING_PATH = None   # --pricing override; default card sits next to plan_triage


# ────────────────────────────────────────────────────────────────────────────
# Shared plumbing
# ────────────────────────────────────────────────────────────────────────────

def env_dirs(envs: Path):
    return sorted(p for p in envs.iterdir() if p.is_dir() and re.match(r"^\d{2}-", p.name))


def apply_order(envs: Path):
    deps = envs / "deps.json"
    if deps.exists():
        doc = json.loads(deps.read_text(encoding="utf-8"))
        order = doc.get("apply_order")
        if order:
            return [e for e in order if (envs / e).is_dir()]
    return [d.name for d in env_dirs(envs)]


def select(envs: Path, target, all_: bool):
    """Resolve ENV[,ENV...] (exact or unique prefix per token) or --all.
    Multi-selections always run in apply order regardless of token order."""
    if all_:
        return apply_order(envs)
    if not target:
        print("specify an ENV (comma-separate for several) or --all", file=sys.stderr)
        sys.exit(2)
    chosen = []
    for tok in (t.strip() for t in str(target).split(",") if t.strip()):
        matches = [d.name for d in env_dirs(envs)
                   if d.name == tok or d.name.startswith(tok)]
        if len(matches) != 1:
            print(f"ambiguous or unknown env {tok!r}: {matches}", file=sys.stderr)
            sys.exit(2)
        if matches[0] not in chosen:
            chosen.append(matches[0])
    order = apply_order(envs)
    return sorted(chosen, key=order.index)


def run_tf(env_dir: Path, args, dry, log=None, **kw):
    """Run terraform, STREAMING its output live (console + log) so long
    refreshes show progress. Returns a CompletedProcess whose stdout holds
    the output tail (stderr is merged into the stream)."""
    cmd = ["terraform"] + args
    line = f"[{env_dir.name}] $ {' '.join(cmd)}"
    print(line, flush=True)
    if log:
        log.write(line + "\n")
    if dry:
        return subprocess.CompletedProcess(cmd, 0, "", "")
    p = subprocess.Popen(cmd, cwd=str(env_dir), stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True,
                         encoding="utf-8", errors="replace", **kw)
    tail = []
    for out in p.stdout:
        print(out.rstrip("\n"), flush=True)
        if log:
            log.write(out)
        tail.append(out)
        if len(tail) > 300:
            tail.pop(0)
    p.wait()
    return subprocess.CompletedProcess(cmd, p.returncode, "".join(tail), "")


def logfile(envs: Path, name: str):
    d = envs / "lzctl-logs"
    d.mkdir(exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    return (d / f"{ts}-{name}.log").open("w", encoding="utf-8")


class Lock:
    """Advisory machine-local lock: one apply at a time against this tree.
    (There is no remote state locking on the OBS backend; CI concurrency
    groups remain the authoritative serializer across machines.)"""

    def __init__(self, envs: Path):
        self.path = envs / ".lzctl.lock"

    def acquire(self, dry=False):
        if self.path.exists():
            try:
                info = json.loads(self.path.read_text(encoding="utf-8"))
            except ValueError:
                info = {}
            age = time.time() - info.get("time", 0)
            holder = f"{info.get('user','?')}@{info.get('host','?')} pid {info.get('pid','?')}"
            if age < LOCK_STALE_S:
                raise SystemExit(f"lock held by {holder} ({int(age)}s ago) - "
                                 f"one apply at a time; remove {self.path} only if that run is dead")
            print(f"note: breaking STALE lock ({holder}, {int(age)}s old)")
        if not dry:
            self.path.write_text(json.dumps({
                "user": getpass.getuser(), "host": socket.gethostname(),
                "pid": os.getpid(), "time": time.time()}), encoding="utf-8")

    def release(self, dry=False):
        if not dry and self.path.exists():
            self.path.unlink()


def triage_plan(env_dir: Path, dry: bool, log) -> tuple:
    """(exit_class, buckets) from the plan file just written: 0/2/3."""
    if dry:
        return 0, None
    r = subprocess.run(["terraform", "show", "-json", "tf.plan"],
                       cwd=str(env_dir), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print(f"  triage: terraform show failed ({r.stderr[:200]})")
        return 2, None
    plan_json = json.loads(r.stdout)
    buckets = plan_triage.triage(plan_json)
    print(plan_triage.report(env_dir.name, buckets))
    cost = plan_triage.cost_report(env_dir.name, plan_json,
                                   plan_triage.load_pricing(PRICING_PATH))
    if cost:
        print(cost)
    if log:
        log.write(plan_triage.report(env_dir.name, buckets) + "\n")
        if cost:
            log.write(cost + "\n")
    if buckets["destructive"]:
        return 3, buckets
    if any(buckets.values()):
        return 2, buckets
    return 0, buckets


# ────────────────────────────────────────────────────────────────────────────
# Verbs
# ────────────────────────────────────────────────────────────────────────────

def cmd_preflight(args):
    envs = Path(args.envs_dir)
    problems = []
    checks = 0
    print("== preflight checks ==")
    tf = shutil.which("terraform")
    checks += 1
    if not tf:
        problems.append("terraform not on PATH")
    else:
        out = subprocess.run(["terraform", "version", "-json"], capture_output=True, text=True)
        try:
            ver = json.loads(out.stdout).get("terraform_version", "0")
            vt = tuple(int(x) for x in ver.split(".")[:3])
            if vt < MIN_TF:
                problems.append(f"terraform {ver} < required {'.'.join(map(str, MIN_TF))}")
            else:
                print(f"  PASS terraform {ver}")
        except (ValueError, KeyError):
            problems.append("could not parse terraform version")
    for k, want in REQUIRED_ENV.items():
        checks += 1
        v = os.environ.get(k)
        if not v:
            fix = f'set {k}={want}' if want else f"set {k}=<your master {'AK' if 'ACCESS_KEY_ID' in k else 'SK'}>"
            problems.append(f"env var {k} not set  ->  {fix}")
        elif want and v != want:
            problems.append(f"env var {k}={v!r} (must be {want!r} or state save fails AFTER apply)")
        else:
            print(f"  PASS {k}")
    checks += 1
    if not envs.exists():
        problems.append(f"envs dir not found: {envs}")
    elif not (envs / "deps.json").exists():
        problems.append(f"deps.json missing in {envs} (apply order falls back to numeric prefix)")
    else:
        print(f"  PASS deps.json ({len(apply_order(envs))} envs in order)")
    for p in problems:
        print(f"  FAIL {p}")
    if problems:
        print(f"\n== RESULT: FAILED ({checks - len(problems)}/{checks} checks; {len(problems)} problem(s) above) ==")
    else:
        print(f"\n== RESULT: ALL PASSED ({checks}/{checks} checks) ==")
    return 1 if problems else 0


def cmd_order(args):
    envs = Path(args.envs_dir)
    for e in apply_order(envs):
        print(e)
    return 0


def _plan_one(env_dir: Path, dry: bool, log) -> int:
    if not (env_dir / ".terraform").exists() and not dry:
        init_args = ["init", "-input=false"]
        if (env_dir / "backend.hcl").exists():
            init_args.append("-backend-config=backend.hcl")
        r = run_tf(env_dir, init_args, dry, log)
        if r.returncode != 0:
            print(f"  FAIL {env_dir.name}: init error (see output above)")
            return 1
    r = run_tf(env_dir, ["plan", "-input=false", "-out", "tf.plan", "-detailed-exitcode"], dry, log)
    if r.returncode == 1:
        print(f"  FAIL {env_dir.name}: plan error (see output above)")
        return 1
    cls, _ = triage_plan(env_dir, dry, log)
    return cls


def cmd_plan(args):
    envs = Path(args.envs_dir)
    worst = 0
    targets = select(envs, args.env, args.all)
    log = logfile(envs, "plan") if not args.dry_run else None
    for name in targets:
        rc = _plan_one(envs / name, args.dry_run, log)
        if rc == 1:
            print(f"\n== RESULT: FAILED (plan error in {name}) ==")
            return 1
        worst = max(worst, rc)
    if args.dry_run:
        print(f"\n== RESULT: DRY RUN COMPLETE ({len(targets)} env(s), no cloud access) ==")
    elif worst == 0:
        print(f"\n== RESULT: NO CHANGES ({len(targets)}/{len(targets)} env(s) clean) ==")
    elif worst == 2:
        print(f"\n== RESULT: CHANGES PRESENT (review the plan output above before apply) ==")
    else:
        print(f"\n== RESULT: DESTRUCTIVE CHANGES PRESENT (apply is blocked without --allow-destroy) ==")
    return worst


def cmd_state_backup(args):
    envs = Path(args.envs_dir)
    dest = envs / "state-backups"
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    for name in select(envs, args.env, args.all):
        env_dir = envs / name
        if args.dry_run:
            print(f"[{name}] $ terraform state pull > state-backups/{ts}-{name}.tfstate.json")
            continue
        r = subprocess.run(["terraform", "state", "pull"], cwd=str(env_dir),
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if r.returncode != 0 or not r.stdout.strip():
            print(f"  {name}: no state pulled ({(r.stderr or 'empty state').strip()[:120]})")
            continue
        dest.mkdir(exist_ok=True)
        out = dest / f"{ts}-{name}.tfstate.json"
        out.write_text(r.stdout, encoding="utf-8")
        print(f"  {name}: backed up -> {out.name} ({len(r.stdout)} bytes)")
    return 0


# Documented transient platform errors that merit exactly one retry (async
# authority grants, log-service hiccups). Extend per engagement with
# LZ_TRANSIENT_SIGNATURES (comma-separated substrings) rather than editing
# code; keep signatures SPECIFIC - a broad match retries real failures.
TRANSIENT_SIGNATURES = tuple(
    s for s in os.environ.get(
        "LZ_TRANSIENT_SIGNATURES", "LTS.2101,EPS.0004").split(",") if s.strip())


def _is_transient(output: str) -> bool:
    return any(sig in (output or "") for sig in TRANSIENT_SIGNATURES)


def _saved_plan_usable(env_dir: Path) -> bool:
    """A tf.plan from a previous plan/drift run can be applied directly IF no
    configuration input changed after it was written (terraform itself refuses
    the plan if the STATE moved). Skips the expensive re-plan on large envs."""
    tfp = env_dir / "tf.plan"
    if not tfp.exists():
        return False
    newest = 0.0
    for pat in ("*.tf", "terraform.tfvars.json", "backend.hcl", "*.auto.tfvars.json"):
        for f in env_dir.glob(pat):
            newest = max(newest, f.stat().st_mtime)
    return tfp.stat().st_mtime >= newest


def cmd_apply(args):
    envs = Path(args.envs_dir)
    order = select(envs, args.env, args.all)
    lock = Lock(envs)
    lock.acquire(dry=args.dry_run)
    log = logfile(envs, "apply") if not args.dry_run else None
    applied, skipped = 0, 0
    try:
        for name in order:
            env_dir = envs / name
            print(f"== {name} ==")
            # 1. state backup first (LZR-007)
            ns = argparse.Namespace(envs_dir=str(envs), env=name, all=False, dry_run=args.dry_run)
            cmd_state_backup(ns)
            # 2. plan + triage gate - reuse the reviewed plan file when it is
            #    still current (approve-what-you-apply; avoids double-planning
            #    slow envs). terraform refuses the file if state moved since.
            if not args.dry_run and _saved_plan_usable(env_dir):
                print(f"  using the saved plan from the last plan run "
                      f"(configuration unchanged since; terraform verifies state freshness)")
                rc, _ = triage_plan(env_dir, False, log)
            else:
                rc = _plan_one(env_dir, args.dry_run, log)
            if rc == 1:
                print(f"\n== RESULT: FAILED (plan error in {name}; earlier envs were applied) ==")
                return 1
            if rc == 0:
                print(f"  PASS {name}: no changes, skipping apply")
                skipped += 1
                continue
            if rc == 3 and not args.allow_destroy:
                print(f"  FAIL {name}: DESTRUCTIVE changes in plan - stopping. Review the plan; "
                      "re-run with --allow-destroy only if the destruction is intended.")
                print(f"\n== RESULT: BLOCKED (destructive changes in {name}) ==")
                return 3
            if not args.yes and not args.dry_run:
                resp = input(f"  apply {name}? [y/N] ").strip().lower()
                if resp != "y":
                    print("\n== RESULT: STOPPED by operator ==")
                    return 2
            # Destructive applies take a SECOND, explicit confirmation that
            # --yes never satisfies: type the env name, or pre-authorize the
            # specific env with --destroy-confirm <env> (for CI).
            if rc == 3 and not args.dry_run:
                pre = getattr(args, "destroy_confirm", None) or []
                if name not in pre:
                    resp = input(f"  DESTRUCTIVE apply - type the env name "
                                 f"({name}) to confirm: ").strip()
                    if resp != name:
                        print("\n== RESULT: STOPPED (destructive apply not confirmed) ==")
                        return 2
            # 3. apply the reviewed plan file
            r = run_tf(env_dir, ["apply", "-input=false", "tf.plan"], args.dry_run, log)
            if r.returncode != 0 and not args.dry_run and _is_transient(r.stdout):
                # Retry-once on documented transients (async grants, log-service
                # hiccups). The saved plan is stale after a partial apply, so
                # the retry is re-plan + apply of the remainder, never a replay.
                print(f"  RETRY {name}: transient platform error - re-plan + apply once")
                if log:
                    log.write("\n[retry] transient signature matched; re-plan + apply\n")
                rc2 = _plan_one(env_dir, False, log)
                if rc2 == 0:
                    r = subprocess.CompletedProcess([], 0, "", "")
                elif rc2 == 2:
                    r = run_tf(env_dir, ["apply", "-input=false", "tf.plan"], False, log)
                # rc2 in (1, 3): fall through with the original failure
            if r.returncode != 0:
                if "stale" in r.stdout.lower():
                    print(f"  FAIL {name}: the saved plan is stale (state changed since it "
                          "was created) - re-run plan for this env, review, then apply again")
                else:
                    print(f"  FAIL {name}: apply error - state backup is in state-backups/; "
                          "see cookbooks (recovering from a failed apply)")
                print(f"\n== RESULT: FAILED (apply error in {name}) ==")
                return 1
            print(f"  PASS {name}: applied")
            applied += 1
    finally:
        lock.release(dry=args.dry_run)
    if args.dry_run:
        print(f"\n== RESULT: DRY RUN COMPLETE ({len(order)} env(s), no cloud access) ==")
    else:
        print(f"\n== RESULT: APPLIED ({applied} applied, {skipped} already current) ==")
    return 0


def cmd_drift(args):
    envs = Path(args.envs_dir)
    rows = []
    log = logfile(envs, "drift")
    targets = select(envs, args.env, not args.env)   # no ENV -> all
    for name in targets:
        env_dir = envs / name
        if not (env_dir / ".terraform").exists():
            rows.append((name, "SKIP (not initialized)"))
            continue
        r = run_tf(env_dir, ["plan", "-input=false", "-out", "tf.plan", "-detailed-exitcode"],
                   False, log)
        if r.returncode == 0:
            rows.append((name, "clean"))
        elif r.returncode == 1:
            last = next((l for l in reversed(r.stdout.strip().splitlines()) if l.strip()), "?")
            rows.append((name, f"ERROR: {last[:100]}"))
        else:
            cls, buckets = triage_plan(env_dir, False, log)
            if buckets and not buckets["update"] and not buckets["destructive"] and not buckets["create"]:
                rows.append((name, f"known-benign drift only ({len(buckets['benign'])})"))
            else:
                b = buckets or {}
                rows.append((name, f"DRIFT: {len(b.get('destructive', []))} destructive, "
                                   f"{len(b.get('update', []))} update, {len(b.get('create', []))} create"))
    print("\n== drift summary ==")
    for name, status in rows:
        tok = "PASS" if status == "clean" or status.startswith("known-benign") else \
              "SKIP" if status.startswith("SKIP") else "FAIL"
        print(f"  {tok} {name:20} {status}")
    if args.report:
        ts = datetime.datetime.now().isoformat(timespec="seconds")
        md = [f"# Drift report - {ts}", ""]
        md += [f"| Env | Status |", "|---|---|"] + [f"| {n} | {s} |" for n, s in rows]
        Path(args.report).write_text("\n".join(md) + "\n", encoding="utf-8")
        print(f"report -> {args.report}")
    bad = [s for _, s in rows if s.startswith(("DRIFT", "ERROR"))]
    clean = len(rows) - len(bad)
    if bad:
        print(f"\n== RESULT: DRIFT FOUND ({len(bad)} env(s) with drift or errors, {clean} clean) ==")
    else:
        print(f"\n== RESULT: NO UNEXPLAINED DRIFT ({clean}/{len(rows)} env(s) clean or known-benign) ==")
    return 2 if bad else 0


def cmd_adopt(args):
    envs = Path(args.envs_dir)
    env_dir = envs / select(envs, args.env, False)[0]
    r = run_tf(env_dir, ["import", args.address, args.cloud_id], args.dry_run)
    if r.returncode != 0:
        print("  import failed (see output above)")
        return 1
    r = run_tf(env_dir, ["plan", "-input=false", "-detailed-exitcode"], args.dry_run)
    if r.returncode == 2:
        print("  imported, but the plan above still shows differences for review.")
        print("  Align the configuration block with the imported values and re-plan.")
        return 2
    print("  imported clean: configuration matches the resource")
    return 0


def cmd_who_changed(args):
    print(f"CTS query for changes to {args.resource!r}:")
    print("  1. Console: CTS (security/audit account) -> Trace List ->")
    print(f"     filter resource name = {args.resource}, time range as needed.")
    print("  2. Older than the console window: query the aggregated copies in LTS")
    print("     (log admin account), or the audit bucket's org-audit prefix (365 d).")
    return 0


def cmd_triage(args):
    return plan_triage.main_files(args.plans)


def cmd_docs(args):
    """Regenerate the doc set (IPAM / checklist / config book) from the tree."""
    root = Path(__file__).resolve().parent.parent
    tools = Path(__file__).resolve().parent / "tools"
    if not tools.exists():
        print("'docs' needs the build pipeline, which this runtime-only "
              "installation does not include.")
        return 2
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    envs = str(Path(args.envs_dir))
    title = args.customer or "Landing Zone"
    jobs = []
    # The Excel LLD workbook is a generated ARTIFACT of the json spec IR
    # (the canonical store) - regenerate it with the rest of the doc set.
    ir = getattr(args, "ir", None)
    if ir:
        jobs.append((tools / "gen_workbook.py",
                     ["--ir", ir, "-o", str(out / "landing-zone-spec.xlsx")]))
    jobs += [
        (tools / "gen_ipam.py", ["--envs-dir", envs, "--out", str(out / "ip-management.xlsx"),
                                 "--title", f"{title} - IP management"]),
        (tools / "gen_config_book.py", ["--envs-dir", envs, "--out", str(out / "config-book.xlsx"),
                                        "--customer", title]
         + (["--states-dir", args.states_dir] if args.states_dir else [])),
    ]
    if args.states_dir:
        jobs.append((tools / "gen_checklist.py",
                     ["--envs-dir", envs, "--states-dir", args.states_dir,
                      "--out", str(out / "resource-checklist.xlsx"),
                      "--title", f"{title} - Resource Checklist"]))
    rc = 0
    print("== document generation ==")
    for script, extra in jobs:
        r = subprocess.run([sys.executable, "-X", "utf8", str(script)] + extra,
                           capture_output=True, text=True)
        tail = (r.stdout or r.stderr).strip().splitlines()
        print(f"  {'PASS' if r.returncode == 0 else 'FAIL'} {script.name}"
              + (f" - {tail[-1]}" if tail else ""))
        rc = rc or r.returncode
    if rc == 0:
        print(f"\n== RESULT: {len(jobs)} DOCUMENT(S) GENERATED -> {out} ==")
    else:
        print(f"\n== RESULT: FAILED (see the FAIL line(s) above) ==")
    return rc


def _pipeline_delegate(what, extra):
    import importlib.util
    if importlib.util.find_spec("lz_spec") is None:
        print(f"'{what}' needs the build pipeline, which this runtime-only "
              "installation does not include.")
        return 2
    if what == "check":
        return subprocess.run([sys.executable, "-m", "lz_spec.verify_pipeline"] + extra).returncode
    if what == "export":
        return subprocess.run([sys.executable, "-m", "lz_pipeline.export_v2"] + extra).returncode
    if what == "validate":
        what = "spec-validate"
    # cwd stays the CALLER's cwd so relative --ir/--envs-dir paths resolve
    # exactly as typed (the old pipeline-dir cwd silently re-anchored them)
    return subprocess.run([sys.executable, "-m", "lz_pipeline", what] + extra).returncode


def cmd_intake(args):
    """Filled questionnaire xlsx -> mechanical answers dump (no interpretation)."""
    import importlib.util
    if importlib.util.find_spec("lz_pipeline.tools.dump_questionnaire") is None:
        print("'intake' needs the build pipeline (dump_questionnaire).")
        return 2
    argv = [sys.executable, "-X", "utf8", "-m", "lz_pipeline.tools.dump_questionnaire",
            args.xlsx]
    if args.out:
        argv += ["-o", args.out]
    return subprocess.run(argv).returncode


def _decision_set_sha256(items):
    """Hash of the IMMUTABLE decision set - ref/state/question/targets/
    default_if_silent, never `resolution` (resolutions must stay editable).
    Stored in the spec's provenance at assess time and recomputed by the
    build gate, so deleting or altering any decision - not just leaving one
    unresolved - blocks the build."""
    import hashlib
    basis = [{k: i.get(k) for k in
              ("ref", "state", "question", "targets", "default_if_silent")
              if k in i}
             for i in items]
    return hashlib.sha256(json.dumps(basis, sort_keys=True, ensure_ascii=False)
                          .encode("utf-8")).hexdigest()


def _neutral(v):
    """Schema-shaped skeleton: keep structure, unset every value.

    Tables empty, scalars blank. A draft built from this fails validation
    until real answers are interpreted in - which is the point: nothing
    deployable exists that wasn't decided by someone."""
    if isinstance(v, dict):
        return {k: _neutral(x) for k, x in v.items()}
    if isinstance(v, list):
        return []
    return ""


def cmd_assess(args):
    """Deterministic assessment pre-pass: neutral draft + decisions files.

    The draft is a schema-shaped skeleton with every value UNSET (it fails
    `lzctl validate` until interpreted - by design). The decisions files
    (.md for humans, .json for the build gate) bucket every question:
    ANSWERED / DEFAULTED (silent with a documented default) / OPEN (required,
    no default). Interpreting prose answers into spec fields is the agent's
    or engineer's job - this command never guesses, and `build` refuses to
    run while OPEN items lack a recorded resolution."""
    import hashlib
    dump_bytes = Path(args.dump).read_bytes()
    dump = json.loads(dump_bytes.decode("utf-8"))
    # lineage id: hash of the answers dump. Stable across resolution edits
    # (those touch the decisions file, not the dump), so a copied/renamed
    # spec still carries — and the gate still demands — its decisions file.
    assessment_id = hashlib.sha256(dump_bytes).hexdigest()
    ws = Path(args.workspace or ".").resolve()
    specs = ws / "specs"
    specs.mkdir(parents=True, exist_ok=True)
    slug = args.customer.lower()
    draft = specs / f"lz.spec.{slug}.json"
    decisions = specs / f"lz.spec.{slug}.decisions.md"
    decisions_json = specs / f"lz.spec.{slug}.decisions.json"
    if draft.exists() and not args.force:
        print(f"refusing to overwrite {draft} (use --force)")
        return 1
    fixture = Path(__file__).resolve().parent / "fixtures" / "example.spec.json"
    spec = json.loads(fixture.read_text(encoding="utf-8"))
    spec["sheets"] = _neutral(spec["sheets"])
    spec["customer"] = slug
    meta = dump.get("meta", {})
    spec["source"] = (f"assessment questionnaire v{meta.get('questionnaire_version', '?')} "
                      f"({dump.get('source_file', '?')}) - NEUTRAL DRAFT: every value "
                      "unset until interpreted from the answers; validate fails until then")
    answered, defaulted, gaps = [], [], []
    for a in dump.get("answers", []):
        ref, q = a.get("ref", "?"), (a.get("question") or "").strip()
        ans = (a.get("answer") or "").strip()
        if ans:
            answered.append((ref, q, ans))
        elif (a.get("default_if_silent") or "").strip():
            defaulted.append((ref, q, a["default_if_silent"].strip()))
        else:
            gaps.append((ref, q, ", ".join(a.get("targets") or []) or "-"))
    apx = dump.get("appendices", {})

    # the immutable decision set, hashed into the spec's provenance: build
    # verifies the manifest still holds EXACTLY this set (resolutions aside),
    # so truncating or altering decisions blocks just like leaving them open
    items = (
        [{"ref": r, "state": "OPEN", "question": q, "targets": t,
          "resolution": None} for r, q, t in gaps]
        + [{"ref": r, "state": "DEFAULTED", "question": q, "default_if_silent": d,
            "resolution": None} for r, q, d in defaulted]
        + [{"ref": r, "state": "ANSWERED", "question": q,
            "resolution": None} for r, q, _ in answered])
    spec["provenance"] = {"source_type": "questionnaire",
                          "decisions_file": decisions_json.name,
                          "assessment_id": assessment_id,
                          "decision_set_sha256": _decision_set_sha256(items),
                          "decision_count": len(items),
                          "customer": slug}
    draft.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [f"# Decisions needed - {slug}", "",
             f"Generated by `lzctl assess` from {dump.get('source_file', '?')}.",
             "Every question lands in exactly one state - ANSWERED, DEFAULTED",
             "(silent with a documented default), or OPEN (required, no default).",
             "Nothing below was guessed.", "",
             f"## OPEN ({len(gaps)}) - resolve before build", ""]
    lines += [f"- **{r}** {q}  \n  targets: `{t}`" for r, q, t in gaps] or ["(none)"]
    lines += ["", f"## DEFAULTED ({len(defaulted)}) - documented defaults apply; review", ""]
    lines += [f"- **{r}** {q}  \n  default: {d}" for r, q, d in defaulted] or ["(none)"]
    lines += ["", f"## ANSWERED ({len(answered)}) - interpret into the draft spec", ""]
    lines += [f"- **{r}** {q}" for r, q, _ in answered] or ["(none)"]
    lines += ["", "## Appendices (copy VERBATIM - never retype)", ""]
    lines += [f"- Appendix {k}: {len(v.get('rows', []))} row(s) -> `{', '.join(v.get('targets') or [])}`"
              for k, v in sorted(apx.items())] or ["(none)"]
    decisions.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # machine-readable twin: the build gate reads this. OPEN items block
    # `build` until a resolution is recorded; DEFAULTED/ANSWERED never block.
    decisions_json.write_text(json.dumps({
        "customer": slug, "source_file": dump.get("source_file", "?"),
        "assessment_id": assessment_id,
        "resolution_contract": {
            "blocking": "state=OPEN with resolution=null blocks `lzctl build`",
            "resolve_by": 'set resolution to {"status": "ANSWERED"|"ACCEPTED_DEFAULT",'
                          ' "approved_by": "<person>", "reason": "<why>"} - all three'
                          ' fields required; see schemas/decisions.schema.json'},
        "items": items}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"draft spec (neutral) -> {draft}")
    print(f"decisions (human)    -> {decisions}")
    print(f"decisions (gate)     -> {decisions_json}")
    print(f"\n== RESULT: ASSESSED ({len(answered)} ANSWERED, {len(defaulted)} DEFAULTED, "
          f"{len(gaps)} OPEN) ==")
    print("next: interpret answered questions into the draft (questionnaire-to-spec"
          " skill or by hand), resolve OPEN items in the decisions .json, then"
          " `lzctl validate`")
    return 0


def cmd_verify(args):
    """Post-apply verification: every env must be clean or known-benign."""
    print("== post-apply verification (re-plan + triage every env) ==")
    ns = argparse.Namespace(envs_dir=args.envs_dir, env=args.env, report=args.report)
    rc = cmd_drift(ns)
    if rc == 0:
        print("== VERIFY: PASS (estate matches the configuration) ==")
        return 0
    print("== VERIFY: FAIL (unexplained differences above - the apply chain "
          "left the estate inconsistent; investigate before further changes) ==")
    return rc


def cmd_report(args):
    """Evidence bundle: logs, deps, drift report, versions -> evidence/<ts>/."""
    import hashlib
    envs = Path(args.envs_dir)
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = Path(args.out or (envs / "evidence" / ts))
    out.mkdir(parents=True, exist_ok=True)
    collected = []
    logs = sorted((envs / "lzctl-logs").glob("*.log"))[-int(args.last_logs):] \
        if (envs / "lzctl-logs").exists() else []
    for src in logs + [envs / "deps.json"]:
        if Path(src).exists():
            shutil.copy2(src, out / Path(src).name)
            collected.append(Path(src).name)
    vers = [f"python {sys.version.split()[0]}"]
    if shutil.which("terraform"):
        r = subprocess.run(["terraform", "version"], capture_output=True, text=True)
        vers.append((r.stdout or "").splitlines()[0] if r.stdout else "terraform ?")
    (out / "versions.txt").write_text("\n".join(vers) + "\n", encoding="utf-8")
    drift_report = out / "drift-report.md"
    ns = argparse.Namespace(envs_dir=str(envs), env=None, report=str(drift_report))
    drift_rc = cmd_drift(ns)
    manifest = []
    for p in sorted(out.iterdir()):
        if p.name == "MANIFEST.txt":
            continue
        manifest.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}")
    (out / "MANIFEST.txt").write_text("\n".join(manifest) + "\n", encoding="utf-8")
    print(f"\n== RESULT: EVIDENCE BUNDLE -> {out} ({len(manifest)} file(s); "
          f"drift {'clean/benign' if drift_rc == 0 else 'HAS FINDINGS'}) ==")
    return 0 if drift_rc == 0 else 2


DELEGATES = ("build", "validate", "spec-validate", "check", "export")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    # Delegated verbs pass their entire argv through untouched - argparse's
    # remainder handling cannot preserve leading --options, so dispatch first.
    # `lzctl <verb> --help` reaches the delegated parser's own help.
    if argv and argv[0] in DELEGATES:
        return _pipeline_delegate(argv[0], argv[1:])
    ap = argparse.ArgumentParser(prog="lzctl", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--envs-dir", required=True)
        p.add_argument("--pricing", help="rate card JSON for the monthly cost estimate")
        p.add_argument("env", nargs="?")
        p.add_argument("--all", action="store_true")
        p.add_argument("--dry-run", action="store_true")

    p = sub.add_parser("preflight");  p.add_argument("--envs-dir", required=True); p.set_defaults(fn=cmd_preflight)
    p = sub.add_parser("order");      p.add_argument("--envs-dir", required=True); p.set_defaults(fn=cmd_order)
    p = sub.add_parser("plan");       common(p); p.set_defaults(fn=cmd_plan)
    p = sub.add_parser("apply");      common(p)
    p.add_argument("--allow-destroy", action="store_true")
    p.add_argument("--yes", action="store_true",
                   help="skip the per-env confirm; NEVER skips the destructive confirm")
    p.add_argument("--destroy-confirm", action="append", metavar="ENV",
                   help="pre-authorize a destructive apply for this exact env (CI)")
    p.set_defaults(fn=cmd_apply)
    p = sub.add_parser("drift");      p.add_argument("--envs-dir", required=True)
    p.add_argument("env", nargs="?", help="ENV[,ENV...] subset (default: all)")
    p.add_argument("--report"); p.set_defaults(fn=cmd_drift)
    p = sub.add_parser("state-backup"); common(p); p.set_defaults(fn=cmd_state_backup)
    p = sub.add_parser("adopt");      p.add_argument("--envs-dir", required=True)
    p.add_argument("env"); p.add_argument("address"); p.add_argument("cloud_id")
    p.add_argument("--dry-run", action="store_true"); p.set_defaults(fn=cmd_adopt)
    p = sub.add_parser("who-changed"); p.add_argument("resource"); p.set_defaults(fn=cmd_who_changed)
    p = sub.add_parser("triage");     p.add_argument("plans", nargs="+"); p.set_defaults(fn=cmd_triage)
    p = sub.add_parser("docs");       p.add_argument("--envs-dir", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--states-dir")
    p.add_argument("--customer", default="")
    p.add_argument("--ir", help="json spec IR - also regenerate the Excel LLD workbook artifact")
    p.set_defaults(fn=cmd_docs)
    p = sub.add_parser("intake", help="filled questionnaire xlsx -> answers dump (mechanical)")
    p.add_argument("xlsx")
    p.add_argument("-o", "--out", help="output json path (default: stdout)")
    p.set_defaults(fn=cmd_intake)
    p = sub.add_parser("assess", help="answers dump -> draft spec + decisions file (no guessing)")
    p.add_argument("dump", help="json produced by `lzctl intake`")
    p.add_argument("--customer", required=True, help="customer slug (lowercase)")
    p.add_argument("--workspace", help="workspace dir (default: cwd); writes specs/ inside it")
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_assess)
    p = sub.add_parser("verify", help="post-apply gate: every env clean or known-benign")
    p.add_argument("--envs-dir", required=True)
    p.add_argument("env", nargs="?", help="ENV[,ENV...] subset (default: all)")
    p.add_argument("--report", help="write the verification table to this markdown file")
    p.set_defaults(fn=cmd_verify)
    p = sub.add_parser("report", help="evidence bundle: logs + deps + drift + versions")
    p.add_argument("--envs-dir", required=True)
    p.add_argument("--out", help="bundle dir (default: <envs>/evidence/<ts>)")
    p.add_argument("--last-logs", default="10", help="how many recent logs to include")
    p.set_defaults(fn=cmd_report)
    for verb in DELEGATES:
        hint = {"build": "generate tfvars + HCL from the spec",
                "validate": "spec validation (structural + semantic + platform rules)",
                "spec-validate": "alias of validate",
                "check": "the pipeline regression harness (7 checks)",
                "export": "handover artifact export"}[verb]
        # registered for --help only; real dispatch happens in main() before
        # argparse so the delegated argv passes through completely untouched
        p = sub.add_parser(verb, help=f"pipeline-side: {hint}")
        p.add_argument("extra", nargs=argparse.REMAINDER)

    args = ap.parse_args(argv)
    global PRICING_PATH
    if getattr(args, "pricing", None):
        PRICING_PATH = args.pricing
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
