"""Generate the customer Excel LLD workbook FROM the json spec IR.

The json IR (lz.spec.<customer>.json) is the canonical config store; the
workbook is a derived, human-facing ARTIFACT (full template: banners,
dropdowns, values filled in - still parseable by the classic pipeline).

Usage: py tools/gen_workbook.py --ir lz_spec/lz.spec.acme.json -o out.xlsx
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent   # workspace
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "lz_spec"))
sys.path.insert(0, str(ROOT / "lz_app"))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--ir", required=True, help="json spec IR (the canonical store)")
    ap.add_argument("-o", "--out", required=True, help="workbook path to write")
    args = ap.parse_args(argv)

    from lz_app import workbook_io
    from lz_pipeline import model

    ir = model.load(Path(args.ir))
    norm = workbook_io.normalize_ir(ir)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    notes = workbook_io.export_workbook(norm, out)
    for n in notes:
        print(f"  note: {n}", file=sys.stderr)

    # Round-trip check: the artifact must parse back to the exact same spec.
    back = workbook_io.normalize_ir(workbook_io.import_workbook(out))
    if back["sheets"] != norm["sheets"]:
        print("ERROR: workbook does not round-trip back to the IR", file=sys.stderr)
        return 1
    print(f"wrote {out} (round-trip verified against {Path(args.ir).name})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
