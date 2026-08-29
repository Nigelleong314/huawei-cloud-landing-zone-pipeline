"""Spec IR: the canonical JSON form of a parsed landing-zone workbook.

The IR is what downstream stages consume; the workbook is one way to produce
it. Shape:

{
  "format": "lz-spec-ir/1",
  "schema_version": "<workbook format version, from _meta or '1.0'>",
  "customer": "<customer_name from _meta, or ''>",
  "source": { "workbook": "...", "exported": "YYYY-MM-DD" },   # informational
  "sheets": { <exactly parse_workbook() output, incl. the _meta sheet> }
}

"sheets" preserves parse order (dict insertion order survives JSON), so a
build from the IR is byte-identical to a build from the workbook.
"""

import datetime
import json
from pathlib import Path


FORMAT = "lz-spec-ir/1"


def _sanitize(o, warnings, path="$"):
    """Make parse output JSON-native; datetimes become ISO strings (warned)."""
    if isinstance(o, dict):
        return {k: _sanitize(v, warnings, f"{path}.{k}") for k, v in o.items()}
    if isinstance(o, list):
        return [_sanitize(v, warnings, f"{path}[{i}]") for i, v in enumerate(o)]
    if isinstance(o, (datetime.datetime, datetime.date)):
        warnings.append(f"{path}: datetime cell converted to ISO string")
        return o.isoformat()
    return o


def from_workbook(workbook: Path) -> tuple:
    """(ir_dict, warnings) from a workbook file."""
    from lz_spec.build_envs import parse_workbook
    from lz_spec.schema import get_meta
    spec = parse_workbook(Path(workbook))
    warnings = []
    sheets = _sanitize(spec, warnings)
    meta = get_meta(sheets)
    ir = {
        "format": FORMAT,
        "schema_version": meta.get("schema_version", "1.0"),
        "customer": meta.get("customer_name") or "",
        "source": {"workbook": Path(workbook).name,
                   "exported": datetime.date.today().isoformat()},
        "sheets": sheets,
    }
    return ir, warnings


def save(ir: dict, path: Path):
    Path(path).write_text(json.dumps(ir, indent=2, ensure_ascii=False) + "\n",
                          encoding="utf-8")


def load(path: Path) -> dict:
    ir = json.loads(Path(path).read_text(encoding="utf-8"))
    fmt = str(ir.get("format", ""))
    if not fmt.startswith("lz-spec-ir/"):
        raise ValueError(f"{path}: not a spec IR file (format={fmt!r})")
    major = str(ir.get("schema_version", "1.0")).split(".")[0]
    if major not in ("1", "2"):
        raise ValueError(f"{path}: unsupported schema_version {ir.get('schema_version')!r}")
    return ir


def sheets(ir: dict) -> dict:
    """The spec dict the builders consume."""
    return ir["sheets"]
