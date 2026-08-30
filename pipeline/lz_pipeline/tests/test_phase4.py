"""Phase 4 gates: lzctl runner logic without any credentialed operation.

Covers: apply ordering from deps.json, preflight diagnostics, the advisory
lock lifecycle, dry-run command sequencing, triage delegation exit codes, and
runtime-standalone operation (lzctl imported from a tree without lz_spec).

Run: py tests/test_phase4.py
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PKG = Path(__file__).parent.parent           # lz_pipeline
PIPE = PKG.parent                             # pipeline/
ROOT = PIPE.parent                            # repo root
HERE = PIPE / "lz_spec"
LZCTL = PKG / "lzctl.py"
ENVS = ROOT / "terraform" / "envs-example"

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}  {str(detail)[:300]}")
        FAILED.append(name)


def run(args, env_extra=None, scrub=False):
    env = dict(os.environ)
    if scrub:
        for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
                  "AWS_REQUEST_CHECKSUM_CALCULATION", "AWS_RESPONSE_CHECKSUM_VALIDATION"):
            env.pop(k, None)
    env.update(env_extra or {})
    return subprocess.run([sys.executable, "-X", "utf8", str(LZCTL)] + args,
                          capture_output=True, text=True, env=env)


print("== order: deps.json drives the sequence ==")
# The invariant is that dependency order equals the env numbering, for whatever
# envs the tree actually holds - not a fixed list, so a tree that gains or drops
# an env (or a different customer's tree) still asserts something meaningful.
r = run(["order", "--envs-dir", str(ENVS)])
order = r.stdout.split()
expect = sorted(p.name for p in ENVS.iterdir() if p.is_dir() and re.match(r"\d\d-", p.name))
check(f"{len(expect)} envs in numeric dependency order", order == expect, order)

print("== preflight diagnostics ==")
r = run(["preflight", "--envs-dir", str(ENVS)], scrub=True)
check("missing env vars flagged", r.returncode == 1 and "AWS_ACCESS_KEY_ID" in r.stdout,
      r.stdout[-200:])
check("checksum fix text present", "when_required" in r.stdout, "")
r = run(["preflight", "--envs-dir", str(ENVS)], scrub=True, env_extra={
    "AWS_ACCESS_KEY_ID": "x", "AWS_SECRET_ACCESS_KEY": "y",
    "AWS_REQUEST_CHECKSUM_CALCULATION": "when_required",
    "AWS_RESPONSE_CHECKSUM_VALIDATION": "when_required"})
if shutil.which("terraform"):
    check("preflight passes with vars set", r.returncode == 0, r.stdout[-300:])
else:
    # no terraform on PATH: preflight rightly fails on the binary check;
    # assert the env-var half passed (its complaints are gone) and move on
    check("preflight env-var checks pass (terraform absent -> binary check skipped)",
          "AWS_ACCESS_KEY_ID" not in r.stdout, r.stdout[-300:])
r = run(["preflight", "--envs-dir", str(ENVS)], scrub=True, env_extra={
    "AWS_ACCESS_KEY_ID": "x", "AWS_SECRET_ACCESS_KEY": "y",
    "AWS_REQUEST_CHECKSUM_CALCULATION": "always",
    "AWS_RESPONSE_CHECKSUM_VALIDATION": "when_required"})
check("wrong checksum value flagged", r.returncode == 1 and "must be" in r.stdout, r.stdout[-200:])

print("== lock lifecycle ==")
sys.path.insert(0, str(LZCTL.parent))
import lzctl
with tempfile.TemporaryDirectory() as td:
    envs = Path(td)
    lock = lzctl.Lock(envs)
    lock.acquire()
    check("lock file created", (envs / ".lzctl.lock").exists())
    try:
        lzctl.Lock(envs).acquire()
        check("second acquire blocked", False)
    except SystemExit as e:
        check("second acquire blocked", "lock held" in str(e), str(e))
    lock.release()
    check("release removes lock", not (envs / ".lzctl.lock").exists())
    # stale lock is broken
    (envs / ".lzctl.lock").write_text(json.dumps(
        {"user": "old", "host": "gone", "pid": 1, "time": time.time() - 3 * 3600}), encoding="utf-8")
    lzctl.Lock(envs).acquire()
    check("stale lock broken and re-acquired", (envs / ".lzctl.lock").exists())

print("== dry-run sequencing (no terraform executed) ==")
r = run(["apply", "--envs-dir", str(ENVS), "--all", "--dry-run", "--yes"])
out = r.stdout
first = out.find("== 00-bootstrap ==")
last = out.find("== 07-security ==")
check("dry-run walks all envs in order", 0 <= first < last, (first, last))
check("state backup precedes plan", out.find("state pull", first) < out.find("terraform plan", first))
check("no lock file left behind", not (ENVS / ".lzctl.lock").exists())
check("plan uses saved plan file", "-out tf.plan" in out)

print("== triage delegation ==")
with tempfile.TemporaryDirectory() as td:
    benign = Path(td) / "benign.json"
    benign.write_text(json.dumps({"resource_changes": [
        {"address": "m.huaweicloud_lts_transfer.t", "type": "huaweicloud_lts_transfer",
         "change": {"actions": ["update"],
                    "before": {"log_transfer_info": [{"log_transfer_detail": [{"obs_dir_prefix_name": "a/"}]}]},
                    "after": {"log_transfer_info": [{"log_transfer_detail": [{"obs_dir_prefix_name": "a"}]}]},
                    "after_unknown": {}}}]}), encoding="utf-8")
    destr = Path(td) / "destr.json"
    destr.write_text(json.dumps({"resource_changes": [
        {"address": "m.huaweicloud_vpn_gateway.g", "type": "huaweicloud_vpn_gateway",
         "change": {"actions": ["delete", "create"], "before": {}, "after": {}, "after_unknown": {}}}]}),
        encoding="utf-8")
    r = run(["triage", str(benign)])
    check("benign plan exit 2 with benign label", r.returncode == 2 and "benign (known)" in r.stdout, r.stdout)
    r = run(["triage", str(destr)])
    check("destructive plan exit 3 + protected", r.returncode == 3 and "PROTECTED" in r.stdout, r.stdout)

print("== runtime-standalone (no lz_spec present) ==")
with tempfile.TemporaryDirectory() as td:
    rt = Path(td) / "runner"
    rt.mkdir()
    shutil.copy2(LZCTL, rt / "lzctl.py")
    shutil.copy2(PKG / "tools" / "plan_triage.py", rt / "plan_triage.py")
    fake_envs = Path(td) / "envs"
    for n in ("01-a", "02-b"):
        (fake_envs / n).mkdir(parents=True)
    (fake_envs / "deps.json").write_text(json.dumps(
        {"apply_order": ["01-a", "02-b"], "envs": {}}), encoding="utf-8")
    r = subprocess.run([sys.executable, "-X", "utf8", str(rt / "lzctl.py"),
                        "order", "--envs-dir", str(fake_envs)],
                       capture_output=True, text=True)
    check("standalone order works", r.stdout.split() == ["01-a", "02-b"], r.stdout)
    # a runtime-only install has no lz_spec package: scrub the path vars the
    # dev checkout (or pytest) injects so the degrade path is actually taken
    bare_env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    r = subprocess.run([sys.executable, "-X", "utf8", "-E", str(rt / "lzctl.py"),
                        "build", "--envs-dir-ignored"],
                       capture_output=True, text=True, env=bare_env, cwd=str(rt))
    check("pipeline verbs degrade gracefully", "does not include" in r.stdout, r.stdout)

print()
if FAILED:
    print(f"FAILED: {len(FAILED)} -> {FAILED}")
    sys.exit(1)
print("all phase-4 tests passed")
