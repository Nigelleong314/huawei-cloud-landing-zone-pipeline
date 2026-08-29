"""Phase 1 gate: the GENERATED workbook artifact builds byte-identical to the IR.

The json IR is the canonical config store; the Excel workbook is generated
from it (tools/gen_workbook.py -> handover-docs/landing-zone-spec.xlsx).
This gate proves the artifact parses back to the same spec and builds the
same bytes - i.e. a customer can still hand-edit the workbook and re-import.

Also: IR round-trip fidelity and schema_check behaviour on good/adversarial
synthetic IRs (non-customer data - generic-behaviour proof).

Run: py tests/test_phase1.py
"""

import filecmp
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PKG = Path(__file__).parent.parent           # lz_pipeline
PIPE = PKG.parent                             # pipeline/
ROOT = PIPE.parent                            # repo root
HERE = PIPE / "lz_spec"
ENVS = ROOT / "terraform" / "envs-example"    # static-file donor for scaffold copies

sys.path.insert(0, str(PIPE))
sys.path.insert(0, str(ROOT / "app"))

# The filled-workbook fixture is generated from the example IR at test start,
# so the round-trip needs no customer artifact.
import subprocess as _sp
_WB_TMP = tempfile.mkdtemp(prefix="lz-p1-wb-")
WORKBOOK = Path(_WB_TMP) / "landing-zone-spec.xlsx"
_r = _sp.run([sys.executable, "-X", "utf8", "-m", "lz_pipeline.tools.gen_workbook",
              "--ir", str(PKG / "fixtures" / "example.spec.json"),
              "-o", str(WORKBOOK)],
             capture_output=True, text=True, encoding="utf-8", errors="replace")
if _r.returncode != 0:
    print(_r.stdout[-800:], _r.stderr[-800:])
    raise SystemExit("could not generate the workbook fixture")

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}  {str(detail)[:400]}")
        FAILED.append(name)


def run(args, **kw):
    env = dict(os.environ)
    env.pop("HW_ACCESS_KEY", None)
    env.pop("HW_SECRET_KEY", None)
    return subprocess.run([sys.executable, "-X", "utf8"] + args,
                          capture_output=True, text=True, env=env, cwd=str(ROOT), **kw)


def gen_files(root: Path):
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file() and (p.name in ("terraform.tfvars.json", "backend.hcl")
                            or p.name.endswith(".generated.tf")):
            out[str(p.relative_to(root))] = p
    return out


print("== IR round-trip fidelity ==")
from lz_spec.build_envs import parse_workbook
from lz_pipeline import model
spec_direct = parse_workbook(WORKBOOK)
ir, warns = model.from_workbook(WORKBOOK)
check("sanitize is identity for this workbook", ir["sheets"] == spec_direct)
with tempfile.TemporaryDirectory() as td:
    p = Path(td) / "ir.json"
    model.save(ir, p)
    reloaded = model.load(p)
    check("save/load round-trip exact", model.sheets(reloaded) == spec_direct)

print("== IR build == workbook build (byte-identical) ==")
with tempfile.TemporaryDirectory(prefix="lz-p1-") as td:
    a = Path(td) / "wb"
    b = Path(td) / "ir"
    import shutil
    ign = shutil.ignore_patterns(".terraform", "*.backup", "errored.tfstate",
                                 "secrets.auto.tfvars.json", "*.bak")
    shutil.copytree(ENVS, a, ignore=ign)
    shutil.copytree(ENVS, b, ignore=ign)

    r1 = run(["-m", "lz_spec.build_envs", str(WORKBOOK), "--envs-dir", str(a)])
    check("workbook build ok", r1.returncode == 0, r1.stderr[-300:])

    irp = Path(td) / "acme.ir.json"
    model.save(ir, irp)
    r2 = run(["-m", "lz_pipeline", "build", "--ir", str(irp), "--envs-dir", str(b)])
    check("IR build ok", r2.returncode == 0, r2.stderr[-300:])

    fa, fb = gen_files(a), gen_files(b)
    check("same file set", set(fa) == set(fb),
          set(fa).symmetric_difference(set(fb)))
    diffs = [rel for rel in fa if rel in fb and not filecmp.cmp(fa[rel], fb[rel], shallow=False)]
    check(f"all {len(fa)} generated files byte-identical", not diffs, diffs)

print("== schema_check on synthetic non-customer IRs ==")
from lz_pipeline import schema_check

good_ir = {"format": "lz-spec-ir/1", "schema_version": "1.1", "customer": "example",
           "sheets": {
               "Global": {"Settings": {"home_region": "ap-southeast-1",
                                       "state_bucket_name": "example-lz-tfstate"}},
               "01_Foundation": {"CoreAccounts": [
                   {"Enabled": "TRUE", "Name": "EXAMPLE-Log-Archive", "Email": "log@example.com"}]},
               "09_CFW": {"ACLRules": [
                   {"Enabled": True, "Name": "r1", "Kind": "vpc", "Action": "allow"}]},
           }}
errs, warns = schema_check.check(good_ir)
check("good synthetic IR: no errors", not errs, errs)

bad_ir = json.loads(json.dumps(good_ir))
bad_ir["sheets"]["01_Foundation"]["CoreAccounts"] = {"not": "a list"}
bad_ir["sheets"]["Global"]["Settings"] = ["not", "a", "dict"]
bad_ir["sheets"]["09_CFW"]["ACLRules"][0]["Enabled"] = "MAYBE"
errs, warns = schema_check.check(bad_ir)
check("adversarial IR: container-shape errors", sum("must be" in e for e in errs) >= 2, errs)
check("adversarial IR: uncoercible bool", any("MAYBE" in e for e in errs), errs)

nonsense = {"format": "not-an-ir"}
try:
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "x.json"
        p.write_text(json.dumps(nonsense), encoding="utf-8")
        model.load(p)
    check("model.load rejects non-IR", False)
except ValueError:
    check("model.load rejects non-IR", True)

print()
if FAILED:
    print(f"FAILED: {len(FAILED)} -> {FAILED}")
    sys.exit(1)
print("all phase-1 tests passed")
