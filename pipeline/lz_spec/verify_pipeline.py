"""Pipeline regression harness. Run between any pipeline/module change.

Usage:
  python -m lz_spec.verify_pipeline                 # all seven checks
  python -m lz_spec.verify_pipeline regen-diff      # spec IR -> envs is a no-op
  python -m lz_spec.verify_pipeline validate        # terraform validate (init'ed envs)
  python -m lz_spec.verify_pipeline template-check  # template structure matches schema.py

The CANONICAL config store is the json spec IR; the Excel workbook is a
GENERATED artifact, not an input.

Targets default to the repo's example spec + example tree; point the harness
at a customer workspace with --envs-dir / --spec (or LZ_VERIFY_ENVS /
LZ_VERIFY_IR), e.g.

  lzctl check all --envs-dir <envs> --spec <lz.spec.json>

A pip-installed runtime has no repo-relative default tree, so the flags are
the only way to target one there; a missing target exits 2 with a message.

Exit code 0 = all requested checks passed.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
REPO = HERE.parent.parent                       # pipeline/lz_spec -> repo root
SPEC_IR = Path(os.environ.get(
    "LZ_VERIFY_IR", HERE.parent / "lz_pipeline" / "fixtures" / "example.spec.json"))
TEMPLATE = HERE / "landing_zone_spec.xlsx"  # blank human template (generated artifact)
ENVS = Path(os.environ.get("LZ_VERIFY_ENVS", REPO / "terraform" / "envs-example"))

GENERATED = ("terraform.tfvars.json",)  # plus any *.generated.tf
SKIP_DIRS = {".terraform"}


def _generated_files(env_dir: Path):
    for p in sorted(env_dir.iterdir()):
        if p.name in GENERATED or p.name.endswith(".generated.tf"):
            yield p


def check_regen_diff() -> bool:
    print("== regen-diff ==")
    ok = True
    total = bad = 0
    with tempfile.TemporaryDirectory(prefix="lz-regen-") as td:
        tmp = Path(td) / "envs"
        shutil.copytree(
            ENVS, tmp,
            ignore=shutil.ignore_patterns(".terraform", "*.backup", "errored.tfstate"),
        )
        env = dict(os.environ)
        env.pop("HW_ACCESS_KEY", None)  # never (re)write secrets during verify
        env.pop("HW_SECRET_KEY", None)
        r = subprocess.run(
            [sys.executable, "-X", "utf8", "-m", "lz_pipeline", "build",
             "--ir", str(SPEC_IR), "--envs-dir", str(tmp)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, cwd=str(HERE.parent),
        )
        if r.returncode != 0:
            print(r.stdout[-2000:])
            print(r.stderr[-2000:])
            print("FAIL: build_envs exited", r.returncode)
            return False
        for env_dir in sorted(ENVS.iterdir()):
            if not env_dir.is_dir():
                continue
            for live in _generated_files(env_dir):
                total += 1
                regen = tmp / env_dir.name / live.name
                if not regen.exists():
                    print(f"  DIFF {env_dir.name}/{live.name}: missing from regeneration")
                    ok = False; bad += 1
                elif regen.read_bytes() != live.read_bytes():
                    print(f"  DIFF {env_dir.name}/{live.name}")
                    ok = False; bad += 1
            live_names = {p.name for p in _generated_files(env_dir)}
            regen_dir = tmp / env_dir.name
            if regen_dir.exists():
                for p in _generated_files(regen_dir):
                    if p.name not in live_names:
                        print(f"  DIFF {env_dir.name}/{p.name}: new file appeared")
                        ok = False
    print("regen-diff:", f"PASS ({total}/{total} generated files unchanged - regeneration is a no-op)"
          if ok else f"FAILED ({bad}/{total} files differ)")
    return ok


def check_validate() -> bool:
    print("== validate modules ==")
    if shutil.which("terraform") is None:
        print("validate: SKIPPED (terraform not on PATH)")
        return "skip"
    ok = True
    total = passed = skipped = 0
    for env_dir in sorted(ENVS.iterdir()):
        if not env_dir.is_dir():
            continue
        if not (env_dir / ".terraform").exists():
            skipped += 1
            continue
        total += 1
        r = subprocess.run(["terraform", "validate", "-no-color"],
                           cwd=env_dir, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            ok = False
            print(f"  {env_dir.name}: FAIL\n{r.stdout}\n{r.stderr}")
        else:
            passed += 1
            print(f"  {env_dir.name}: PASS")
    if total == 0:
        print(f"validate: SKIPPED ({skipped} env(s) not init'ed - run terraform "
              "init to make this check meaningful)")
        return "skip"
    print("validate:", f"PASS ({passed}/{total} envs valid, {skipped} skipped)" if ok
          else f"FAILED ({passed}/{total} envs valid)")
    return ok


def _workbook_structure(path: Path) -> dict:
    """{sheet: {table: [headers]}} walked via the '### ' sentinels."""
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True)
    out = {}
    for ws in wb.worksheets:
        if ws.title == "Index":
            continue
        tables = {}
        rows = list(ws.iter_rows(values_only=True))
        i = 0
        while i < len(rows):
            v = rows[i][0]
            if isinstance(v, str) and v.startswith("### "):
                name = v[4:].strip()
                j = i + 1
                while j < len(rows):
                    nonblank = [c for c in rows[j] if c is not None and str(c).strip()]
                    if len(nonblank) > 1:
                        tables[name] = [str(c).strip() for c in rows[j] if c is not None and str(c).strip()]
                        break
                    j += 1
                i = j
            i += 1
        out[ws.title] = tables
    return out


def check_template() -> bool:
    print("== template-check ==")
    with tempfile.TemporaryDirectory(prefix="lz-tpl-") as td:
        fresh = Path(td) / "template.xlsx"
        r = subprocess.run([sys.executable, "-m", "lz_spec.gen_template", str(fresh)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            print(r.stdout[-1500:], r.stderr[-1500:])
            print("FAIL: gen_template exited", r.returncode)
            return False
        want = _workbook_structure(fresh)
        have = _workbook_structure(TEMPLATE)
    ok = True
    for sheet, tables in want.items():
        if sheet not in have:
            print(f"  template MISSING sheet {sheet}")
            ok = False
            continue
        for t, cols in tables.items():
            if t not in have[sheet]:
                print(f"  template {sheet}: MISSING table {t}")
                ok = False
            elif have[sheet][t] != cols:
                print(f"  template {sheet}.{t}: columns differ")
                print(f"    schema:   {cols}")
                print(f"    template: {have[sheet][t]}")
                ok = False
    for sheet in have:
        if sheet not in want:
            print(f"  template has EXTRA sheet {sheet}")
            ok = False
    n = len(want)
    print("template-check:", f"PASS ({n}/{n} sheets match the schema)" if ok
          else "STALE (regenerate landing_zone_spec.xlsx)")
    return ok


def check_rules() -> bool:
    """LZR rule registry: spec rules on the IR + tree rules on the envs."""
    print("== platform rules check ==")
    sys.path.insert(0, str(HERE))
    sys.path.insert(0, str(HERE.parent))
    from lz_pipeline import rules, model
    spec = model.load(SPEC_IR)["sheets"]
    modules = REPO / "terraform" / "modules"
    findings = rules.run_spec_rules(spec) + rules.run_tree_rules(ENVS, modules)
    errors = [f for f in findings if f.severity == "error"]
    for f in findings:
        print(f"  {f}")
    print("rules:", f"PASS ({len(findings)} finding(s), 0 errors)" if not errors
          else f"FAILED ({len(errors)} error(s), {len(findings)} finding(s))")
    return not errors


def check_deps() -> bool:
    """deps.json ordering (LZR-008), ownership registry, freshness."""
    print("== dependencies check ==")
    sys.path.insert(0, str(HERE.parent))
    import json
    from lz_pipeline import depsgraph
    doc = depsgraph.build(ENVS)
    errs = depsgraph.check(doc["envs"])
    from lz_pipeline.core import ownership
    errs += ownership.check()
    for e in errs:
        print(f"  ERROR {e}")
    on_disk = ENVS / "deps.json"
    stale = False
    if on_disk.exists():
        current = json.loads(on_disk.read_text(encoding="utf-8"))
        if current.get("envs") != doc["envs"]:
            stale = True
            print(f"  deps.json is STALE - re-run: python -m lz_pipeline deps --envs-dir {ENVS}")
    else:
        stale = True
        print("  deps.json missing - run python -m lz_pipeline deps --envs-dir <envs>")
    n = len(doc["envs"])
    print("deps:", f"PASS ({n}/{n} envs ordered, registry clean, deps.json fresh)"
          if not errs and not stale else "FAILED")
    return not errs and not stale


UNIT_DESCRIPTIONS = {
    "test_converge.py": "Validate log auto-derivation",
    "test_cost.py":     "Validate cost estimation",
    "test_phase0.py":   "Validate platform rules",
    "test_phase1.py":   "Validate workbook round-trip",
    "test_phase4.py":   "Validate runner workflow",
    "test_phase5.py":   "Validate artifact export",
}


def check_unit() -> bool:
    """Phase unit tests (rules/depsgraph/triage fixtures) + the app suite."""
    print("== unit tests ==")
    ok = True
    total = passed = 0
    suites = sorted((HERE.parent / "lz_pipeline" / "tests").glob("test_*.py"))
    suites += sorted((REPO / "app" / "tests").glob("test_*.py"))
    for t in suites:
        total += 1
        r = subprocess.run([sys.executable, "-X", "utf8", str(t)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        label = UNIT_DESCRIPTIONS.get(t.name, t.name)
        if r.returncode == 0:
            passed += 1
            print(f"  {label}: PASS")
        else:
            print(f"  {label}: FAIL")
            print(r.stdout[-1500:])
            ok = False
    print("unit tests:", f"PASS ({passed}/{total} suites, all cases green)" if ok
          else f"FAILED ({passed}/{total} suites)")
    return ok


def check_fmt() -> bool:
    """terraform fmt -check on hand-written HCL: modules + scaffold.

    Generated files and customer trees are deliberately out of scope:
    generated bytes are governed by the golden tests, and static copies only
    change on a scaffold refresh."""
    print("== formatting check ==")
    if shutil.which("terraform") is None:
        print("fmt: SKIPPED (terraform not on PATH)")
        return "skip"
    ok = True
    roots = (REPO / "terraform" / "modules",
             REPO / "terraform" / "scaffold")
    clean = 0
    for root in roots:
        r = subprocess.run(["terraform", "fmt", "-check", "-recursive", str(root)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            ok = False
            for line in (r.stdout or "").splitlines()[:20]:
                print(f"  needs fmt: {line}")
        else:
            clean += 1
    print("fmt:", f"PASS ({clean}/{len(roots)} trees canonically formatted)" if ok
          else "FAILED (run terraform fmt -recursive on the paths above)")
    return ok


CHECKS = {
    "regen-diff": check_regen_diff,
    "validate": check_validate,
    "template-check": check_template,
    "rules": check_rules,
    "deps": check_deps,
    "fmt": check_fmt,
    "unit": check_unit,
}


def main():
    global ENVS, SPEC_IR
    ap = argparse.ArgumentParser(
        prog=os.environ.get("LZ_INVOKED_AS") or "lz_spec.verify_pipeline",
        description="Pipeline regression harness. Targets default to the repo's "
                    "example spec + example tree; point it at a customer "
                    "workspace with --envs-dir / --spec (or LZ_VERIFY_ENVS / "
                    "LZ_VERIFY_IR).")
    ap.add_argument("check", nargs="?", default="all",
                    choices=["all", *CHECKS], help="which check to run (default: all)")
    ap.add_argument("--envs-dir", help="env tree to check (overrides LZ_VERIFY_ENVS)")
    ap.add_argument("--spec", "--ir", dest="spec",
                    help="spec IR to regenerate from (overrides LZ_VERIFY_IR)")
    args = ap.parse_args()
    if args.envs_dir:
        ENVS = Path(args.envs_dir).resolve()
    if args.spec:
        SPEC_IR = Path(args.spec).resolve()

    # Fail with a sentence, not a traceback from inside shutil.copytree: a
    # pip-installed runtime has no repo-relative default tree, so the default
    # targets simply do not exist there.
    for label, path, flag in (("env tree", ENVS, "--envs-dir"), ("spec", SPEC_IR, "--spec")):
        if not path.exists():
            print(f"harness {label} not found: {path}\n"
                  f"  pass {flag} <path> (or set the matching LZ_VERIFY_* env var)")
            sys.exit(2)

    which = args.check
    if which == "all":
        results = [fn() for fn in CHECKS.values()]
    else:
        results = [CHECKS[which]()]
    print()
    # tri-state: True / False / "skip" ("skip" is truthy on purpose - a skip
    # is not a failure). NEVER sum(results): it TypeErrors on the strings.
    n_skip = sum(1 for r in results if r == "skip")
    n_pass = sum(1 for r in results if r is True)
    n_fail = sum(1 for r in results if r is False)
    if n_fail == 0:
        if n_skip:
            print(f"== RESULT: PASSED ({n_pass} passed, "
                  f"{n_skip} skipped of {len(results)} checks) ==")
        else:
            print(f"== RESULT: ALL PASSED ({n_pass}/{len(results)} checks) ==")
    else:
        failed = [name for name, r in zip(
            [which] if which != "all" else list(CHECKS), results) if r is False]
        print(f"== RESULT: FAILED ({n_pass} passed, {n_skip} skipped, "
              f"{n_fail} failed; failed: {', '.join(failed)}) ==")
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
