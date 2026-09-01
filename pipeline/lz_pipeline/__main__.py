"""lz_pipeline CLI.

    py -m lz_pipeline spec-export <workbook.xlsx> -o lz.spec.json
    py -m lz_pipeline spec-validate <lz.spec.json | workbook.xlsx>
    py -m lz_pipeline build --spec lz.spec.json --envs-dir <dir> [--scaffold-dir <dir>] [--only 05,06]

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
    errors += check_spec(ir["sheets"])
    for w in warnings:
        print(f"  warn: {w}")
    for e in errors:
        print(f"  error: {e}")
    from lz_pipeline.rules import REGISTRY as _reg
    n_exec = sum(1 for r in _reg if r.fn is not None)
    print(f"spec-validate: {len(errors)} error(s), {len(warnings)} warning(s) "
          f"(rule registry: {n_exec} machine-enforced, {len(_reg) - n_exec} documented)")
    return 1 if errors else 0


def _decisions_gate(ir_path: Path, ir: dict):
    """Problems (message strings) that must block build, or [].

    The gate is bound to the spec's `provenance` block (stamped by
    `lzctl assess`), not to filename convention: a questionnaire-derived
    spec demands its decisions file wherever the spec is copied or renamed,
    with matching customer and assessment_id. Detaching the lineage means
    deleting `provenance` from the spec — a deliberate, reviewable diff.

    An OPEN item blocks until its resolution is COMPLETE:
    status ANSWERED|ACCEPTED_DEFAULT + non-empty approved_by + reason
    (contract: schemas/decisions.schema.json). ANSWERED/DEFAULTED items
    never block. The manifest must also be COMPLETE: provenance carries a
    hash of the immutable decision set, so truncating or altering decisions
    blocks just like leaving them unresolved. A spec with no provenance and
    no sibling decisions file has no questionnaire lineage — no gate
    (e.g. workbook exports).
    """
    import json
    prov = ir.get("provenance") or {}
    from_questionnaire = prov.get("source_type") == "questionnaire"
    dec = ir_path.with_name(prov.get("decisions_file")
                            or (ir_path.stem + ".decisions.json"))
    if not dec.exists():
        if from_questionnaire:
            return [f"decisions file missing: {dec.name} (this spec's provenance "
                    "says it derives from a questionnaire; keep the decisions "
                    "file next to the spec, or deliberately remove the "
                    "'provenance' block to detach the lineage)"]
        return []
    doc = json.loads(dec.read_text(encoding="utf-8"))
    problems = []
    if from_questionnaire:
        for field in ("customer", "assessment_id"):
            if doc.get(field) != prov.get(field):
                problems.append(f"decisions file {dec.name}: {field} mismatch "
                                f"(spec provenance {prov.get(field)!r} != "
                                f"decisions {doc.get(field)!r}) - this decisions "
                                "file does not belong to this spec")
        # completeness: the manifest must hold EXACTLY the immutable decision
        # set from assessment. Deleting, adding, or altering a decision (not
        # its resolution - those are the editable part) blocks the build.
        from .lzctl import _decision_set_sha256
        expected = prov.get("decision_set_sha256")
        if not expected:
            problems.append("spec provenance lacks decision_set_sha256 - "
                            "re-run `lzctl assess` (a provenance block without "
                            "the decision-set hash cannot prove the manifest "
                            "is complete)")
        elif _decision_set_sha256(doc.get("items", [])) != expected:
            problems.append(
                f"decision set altered: {dec.name} no longer matches the set "
                f"generated at assessment ({len(doc.get('items', []))} item(s) "
                f"present, {prov.get('decision_count', '?')} expected). Only "
                "`resolution` fields may be edited; a decision was deleted, "
                "added, or changed - re-run `lzctl assess` if the "
                "questionnaire itself changed")
    for i in doc.get("items", []):
        if i.get("state") != "OPEN":
            continue
        ref = i.get("ref", "?")
        res = i.get("resolution")
        if not isinstance(res, dict):
            problems.append(f"OPEN {ref}: unresolved - {i.get('question', '')[:90]}")
            continue
        status = res.get("status")
        if status not in ("ANSWERED", "ACCEPTED_DEFAULT"):
            problems.append(f"OPEN {ref}: resolution.status {status!r} is not "
                            "ANSWERED or ACCEPTED_DEFAULT")
            continue
        missing = [f for f in ("approved_by", "reason")
                   if not str(res.get(f) or "").strip()]
        if missing:
            problems.append(f"OPEN {ref}: status {status} but no "
                            f"{' / '.join(missing)} - resolutions must record "
                            "who decided and why")
    return problems


def cmd_build(args):
    from .core import cli as be
    ir = model.load(Path(args.ir))
    problems = _decisions_gate(Path(args.ir).resolve(), ir)
    if problems:
        print("build blocked by the decisions gate (never guess - fix these in "
              "the .decisions.json, then re-run):", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 3
    spec = ir["sheets"]

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
    dep_errs = write_deps(envs_dir)
    print(f"\n== RESULT: BUILT {len(selected)} env(s) from {Path(args.ir).name} ==")
    return 1 if dep_errs else 0


def write_deps(envs_dir: Path) -> list:
    """(Re)write <envs-dir>/deps.json from the tree's remote-state references.

    build's exit artifact is "generated envs + FRESH deps.json": preflight
    fails without it and the apply order comes from it, so a built tree that
    lacks one is not deployable. Written here (not only by depsgraph's own
    CLI) so nobody has to reach around lzctl to finish a build.
    """
    import json
    from . import depsgraph
    doc = depsgraph.build(envs_dir)
    errs = depsgraph.check(doc["envs"])
    (envs_dir / "deps.json").write_text(json.dumps(doc, indent=2) + "\n",
                                        encoding="utf-8", newline="\n")
    print(f"wrote {envs_dir / 'deps.json'} ({len(doc['apply_order'])} envs in order)")
    for e in errs:
        print(f"  ERROR deps: {e}", file=sys.stderr)
    return errs


def cmd_deps(args):
    envs_dir = Path(args.envs_dir).resolve()
    if not envs_dir.exists():
        print(f"envs dir not found: {envs_dir}", file=sys.stderr)
        return 2
    return 1 if write_deps(envs_dir) else 0


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
    p.add_argument("--spec", "--ir", dest="ir", required=True,
                   help="the JSON spec (--ir is an accepted alias)")
    p.add_argument("--envs-dir", required=True)
    p.add_argument("--scaffold-dir")
    p.add_argument("--only")
    p.set_defaults(fn=cmd_build)

    p = sub.add_parser("deps", help="regenerate <envs-dir>/deps.json (build writes it too)")
    p.add_argument("--envs-dir", required=True)
    p.set_defaults(fn=cmd_deps)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
