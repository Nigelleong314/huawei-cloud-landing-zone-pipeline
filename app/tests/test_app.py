"""lz_app gates.

  1. Workbook round-trip: normalize(example IR) -> xlsx -> import == exact.
  2. API end-to-end against a live server (ephemeral port): meta/schema,
     load IR, validate (example clean), save (json-only; xlsx rejected),
     run a plan job (env subset, dry-run) to completion.

Run: py tests/test_app.py     (from lz_app/)
"""

import json
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent      # app/
REPO = HERE.parent                                  # repo root
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "pipeline"))

from lz_app import find_workspace
from lz_app import workbook_io

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}  {str(detail)[:300]}")
        FAILED.append(name)


# The app's workspace is a DATA directory now: build a throwaway one from
# the repo's example assets, exactly as a new user would get after `assess`.
import shutil as _sh
_ws_tmp = Path(tempfile.mkdtemp(prefix="lz-app-ws-"))
(_ws_tmp / "specs").mkdir()
_FIXTURE = REPO / "pipeline/lz_pipeline/fixtures/example.spec.json"
_sh.copy2(_FIXTURE, _ws_tmp / "specs" / "lz.spec.example.json")
_sh.copytree(REPO / "terraform/envs-example", _ws_tmp / "envs",
             ignore=_sh.ignore_patterns(".terraform"))
WS = find_workspace(str(_ws_tmp))
ENVS_DIR = "envs"

print("== workbook round-trip ==")
example = json.loads(_FIXTURE.read_text(encoding="utf-8"))
norm = workbook_io.normalize_ir(example)
with tempfile.TemporaryDirectory() as td:
    x = Path(td) / "example.xlsx"
    notes = workbook_io.export_workbook(norm, x)
    check("example exports with no drops", not notes, notes)
    back = workbook_io.normalize_ir(workbook_io.import_workbook(x))
    check("example round-trip exact", back["sheets"] == norm["sheets"],
          [k for k in norm["sheets"] if back["sheets"].get(k) != norm["sheets"][k]])

print("== API end-to-end ==")
from lz_app import server


def req(path, method="GET", body=None, headers=None, _attempts=3):
    """One API call, retrying a TRANSPORT abort only.

    On Windows, a rapid series of loopback connections intermittently dies
    with WinError 10053 ("connection aborted by the software in your host
    machine") - a local socket/AV artefact, not the app answering wrongly.
    Retrying that is honest; retrying an HTTP error would hide real bugs, so
    urllib.HTTPError is deliberately NOT caught here.
    """
    data = json.dumps(body).encode() if body is not None else None
    h = {"Content-Type": "application/json", "X-LZ-Token": server.TOKEN}
    h.update(headers or {})
    last = None
    for attempt in range(_attempts):
        r = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", data=data,
                                   method=method, headers=h)
        try:
            with urllib.request.urlopen(r, timeout=30) as resp:
                return json.loads(resp.read())
        except (ConnectionError, urllib.error.URLError) as e:
            if isinstance(e, urllib.error.HTTPError):
                raise
            last = e
            time.sleep(0.2 * (attempt + 1))
    raise AssertionError(f"{method} {path}: transport failed {_attempts}x - {last}")


httpd = server.serve(str(WS), port=0)
PORT = httpd.server_address[1]
threading.Thread(target=httpd.serve_forever, daemon=True).start()

meta = req("/api/meta")
check("meta serves", meta["workspace"] == str(WS), meta)
sch = req("/api/schema")
check("schema has 13 sheets", len(sch["sheets"]) == 13, len(sch["sheets"]))
enum_ok = any(c.get("enum") == ["vpc", "nat", "eip"]
              for s in sch["sheets"] if s["name"] == "09_CFW"
              for t in s["tables"] if t["name"] == "ACLRules"
              for c in t.get("columns", []))
check("schema carries enums", enum_ok)
n5 = next(s for s in sch["sheets"] if s["name"] == "05_Network")
fk_ok = any(c.get("fk") == [["05_Network", "HubVPCs", "VPCName"]]
            for t in n5["tables"] if t["name"] == "HubERAttachments"
            for c in t.get("columns", []) if c["name"] == "VPC")
check("schema carries fk metadata", fk_ok)
check("EIPs badged optional",
      next(t for t in n5["tables"] if t["name"] == "EIPs").get("badge") == "optional")
check("05_Network ships fixed notes (ERRouteTables card)",
      any("ERRouteTables" in f["title"] for f in n5.get("fixed_notes", [])))
check("10_VPN sheet badged optional",
      next(s for s in sch["sheets"] if s["name"] == "10_VPN").get("badge") == "optional")
sfk_ok = any(f.get("fk") for t in n5["tables"] if t["name"] == "Settings"
             for f in t.get("fields", []) if f["name"] == "hub_account")
check("scalar fields carry fk metadata", sfk_ok)

r = req("/api/spec/load", "POST", {"name": "lz.spec.example.json"})
check("load example IR", r.get("ok") is True, r)
v = req("/api/spec/validate", "POST", {})
check("example validates clean via API", not v["errors"], v["errors"][:3])

try:
    req("/api/spec/save", "POST", {"path": "should-fail.xlsx"})
    check("xlsx save rejected (json-only store)", False, "expected HTTP 400")
except urllib.error.HTTPError as e:
    check("xlsx save rejected (json-only store)", e.code == 400, e.code)

# CSRF/token gate: mutating requests need the startup token and a local origin
try:
    req("/api/spec/validate", "POST", {}, headers={"X-LZ-Token": "wrong"})
    check("POST without valid token rejected", False, "expected HTTP 403")
except urllib.error.HTTPError as e:
    check("POST without valid token rejected", e.code == 403, e.code)
try:
    req("/api/spec/validate", "POST", {}, headers={"Origin": "https://evil.example"})
    check("cross-origin POST rejected", False, "expected HTTP 403")
except urllib.error.HTTPError as e:
    check("cross-origin POST rejected", e.code == 403, e.code)
try:
    req("/api/spec/save", "POST", {"path": str(Path(tempfile.gettempdir()) / "lz-escape.json")})
    check("save outside the workspace rejected", False, "expected HTTP 400")
except urllib.error.HTTPError as e:
    check("save outside the workspace rejected", e.code == 400, e.code)

e = req(f"/api/envs?dir={ENVS_DIR}")
check("/api/envs returns apply-ordered envs", e["envs"][0] == "00-bootstrap"
      and "07-security" in e["envs"] and len(e["envs"]) >= 11, e)

# dry-run plan over an env SUBSET: exercises the comma-list selection path,
# and the order in the output must be apply order (05 before 08).
r = req("/api/job", "POST", {"verb": "plan", "args": {
    "envs_dir": ENVS_DIR, "dry_run": True,
    "envs": ["09-network-cfw", "05-network"]}})
jid = r["job"]
# Budget generously: this waits on a real subprocess, so a loaded machine
# (a full suite running beside it) can take far longer than the work itself.
# A tight budget here fails as "the app is broken" when nothing is.
deadline = time.time() + 90
while time.time() < deadline:
    j = req(f"/api/jobs/{jid}")
    if j["status"] != "running":
        break
    time.sleep(0.3)
check("plan job (env subset, dry-run) completes", j["status"] == "done",
      f"status={j['status']} after {90}s - still running means the box was "
      f"loaded, not that the job failed: {j}")
out = j["output"]
check("subset runs in apply order", 0 <= out.find("[05-network]") < out.find("[09-network-cfw]"),
      out[:200])

httpd.shutdown()
print()
if FAILED:
    print(f"FAILED: {len(FAILED)} -> {FAILED}")
    sys.exit(1)
print("all lz_app tests passed")
