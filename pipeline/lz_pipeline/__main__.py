"""lz_pipeline CLI.

    py -m lz_pipeline spec-export <workbook.xlsx> -o lz.spec.json
    py -m lz_pipeline spec-validate <lz.spec.json | workbook.xlsx>
    py -m lz_pipeline build --ir lz.spec.json --envs-dir <dir> [--scaffold-dir <dir>] [--only 05,06]

Run from anywhere; lz_spec is located next to this package (override with
LZ_SPEC_DIR). The build path runs the lz_pipeline.core builders/emitters, so
its output is byte-identical to the workbook path.
"""

import argparse
import os
import sys
from pathlib import Path

from . import model, schema_check


def cmd_spec_export(args):
    ir, warnings = model.from_workbook(Path(args.workbook))
    for w in warnings:
        print(f"  note: {w}", file=sys.stderr)
    errors, warns = schema_check.check(ir)
    for w in warns:
        print(f"  warn: {w}", file=sys.stderr)
    if errors:
        for e in errors:
            print(f"  error: {e}", file=sys.stderr)
        return 1
    model.save(ir, Path(args.out))
    n = sum(1 for _ in ir["sheets"])
    print(f"wrote {args.out} (schema {ir['schema_version']}, {n} sheets, customer {ir['customer'] or '-'})")
    return 0


def cmd_spec_validate(args):
    p = Path(args.spec)
    if p.suffix.lower() == ".xlsx":
        ir, _ = model.from_workbook(p)
    else:
        ir = model.load(p)
    errors, warnings = schema_check.check(ir)
    from .core.cli import check_spec
    errors += check_spec(model.sheets(ir))
    for w in warnings:
        print(f"  warn: {w}")
    for e in errors:
        print(f"  error: {e}")
    print(f"spec-validate: {len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


def _open_decisions(ir_path: Path):
    """Unresolved OPEN items from the sibling decisions file, if one exists.

    `lzctl assess` writes lz.spec.<slug>.decisions.json next to the draft.
    An OPEN item blocks build until someone records a resolution
    ({"status": "ANSWERED"|"ACCEPTED_DEFAULT", "approved_by": ..., "reason": ...});
    ANSWERED/DEFAULTED items never block. No decisions file = no gate
    (specs exported straight from a workbook have no questionnaire lineage).
    """
    import json
    dec = ir_path.with_name(ir_path.stem + ".decisions.json")
    if not dec.exists():
        return []
    items = json.loads(dec.read_text(encoding="utf-8")).get("items", [])
    return [i for i in items
            if i.get("state") == "OPEN"
            and (i.get("resolution") or {}).get("status")
            not in ("ANSWERED", "ACCEPTED_DEFAULT")]


def cmd_build(args):
    from .core import cli as be
    unresolved = _open_decisions(Path(args.ir).resolve())
    if unresolved:
        print("build blocked: unresolved OPEN decisions (never guess - resolve "
              "them in the .decisions.json, then re-run):", file=sys.stderr)
        for i in unresolved:
            print(f"  - {i.get('ref', '?')}: {i.get('question', '')[:90]}",
                  file=sys.stderr)
        return 3
    ir = model.load(Path(args.ir))
    spec = model.sheets(ir)

    envs_dir = Path(args.envs_dir).resolve()
    scaffold = Path(args.scaffold_dir).resolve() if args.scaffold_dir else None
    selected = be._select_envs(args.only)

    errs = be.check_spec(spec, selected)
    if errs:
        print("Validation errors:", file=sys.stderr)
        for e in errs:
            print(f"  - {e}", file=sys.stderr)
        return 1

    if scaffold is None and not envs_dir.exists():
        print(f"envs dir not found: {envs_dir} (pass --scaffold-dir to create a new tree)",
              file=sys.stderr)
        return 2

    ak = os.environ.get("HW_ACCESS_KEY", "")
    sk = os.environ.get("HW_SECRET_KEY", "")
    if not ak or not sk:
        print("note: HW_ACCESS_KEY / HW_SECRET_KEY not set; secrets.auto.tfvars.json skipped.",
              file=sys.stderr)

    print(f"== build: {Path(args.ir).name} -> {envs_dir.name} ==")
    be.build_from_spec(spec, envs_dir, scaffold, selected, ak, sk,
                       customer=ir.get("customer") or "")
    print(f"\n== RESULT: BUILT {len(selected)} env(s) from {Path(args.ir).name} ==")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="lz_pipeline")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("spec-export", help="workbook -> lz.spec.json")
    p.add_argument("workbook")
    p.add_argument("-o", "--out", required=True)
    p.set_defaults(fn=cmd_spec_export)

    p = sub.add_parser("spec-validate", help="structural + semantic validation")
    p.add_argument("spec", help="lz.spec.json or workbook.xlsx")
    p.set_defaults(fn=cmd_spec_validate)

    p = sub.add_parser("build", help="IR -> envs (byte-identical to workbook path)")
    p.add_argument("--ir", required=True)
    p.add_argument("--envs-dir", required=True)
    p.add_argument("--scaffold-dir")
    p.add_argument("--only")
    p.set_defaults(fn=cmd_build)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
