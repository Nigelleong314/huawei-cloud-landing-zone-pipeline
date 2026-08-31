"""Emit a JSON Schema for the spec from lz_spec.schema (single source).

The python schema stays authoritative; this artifact exists so validation is
tool- and model-agnostic: any JSON Schema validator - or an agent harness -
can check a draft spec without importing the pipeline.

Usage: python -m lz_pipeline.tools.gen_jsonschema [-o schemas/lz.spec.schema.json]
"""

import argparse
import json
import sys
from pathlib import Path

TYPE_MAP = {
    "str": {"type": "string"},
    "bool": {"type": ["boolean", "string"]},   # sheets carry TRUE/FALSE strings too
    "int": {"type": ["integer", "string"]},
    "cidr": {"type": "string"},
    "email": {"type": "string"},
    "list": {"type": "string"},                # comma-separated by convention
}


def _field(kv) -> dict:
    out = dict(TYPE_MAP.get(getattr(kv, "type", "str"), {"type": "string"}))
    desc = (getattr(kv, "description", "") or "").strip()
    if desc:
        out["description"] = desc
    return out


def build_schema() -> dict:
    from lz_spec import schema as wb
    sheets_props = {}
    for s in wb.SHEETS:
        if s.name in wb.INFO_SHEETS or s.name == "_meta":
            continue
        tables = {}
        for t in s.tables:
            if t.kind == "scalar":
                tables[t.name] = {
                    "type": "object",
                    "description": (t.description or "").strip(),
                    "properties": {kv.name: _field(kv) for kv in t.rows},
                    "additionalProperties": True,
                }
            else:
                cols = {}
                for c in (t.columns or []):
                    # columns are (name, type, description) tuples
                    name, ctype, cdesc = (list(c) + ["", ""])[:3] if isinstance(c, (tuple, list)) else (c, "", "")
                    entry = dict(TYPE_MAP.get(ctype, {}))
                    if cdesc:
                        entry["description"] = str(cdesc).strip()
                    cols[str(name)] = entry
                tables[t.name] = {
                    "type": "array",
                    "description": (t.description or "").strip(),
                    "items": {
                        "type": "object",
                        "properties": cols,
                        "additionalProperties": True,
                    },
                }
        sheets_props[s.name] = {
            "type": "object",
            "description": (s.description or "").strip(),
            "properties": tables,
            "additionalProperties": True,
        }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://example.invalid/lz.spec.schema.json",
        "title": "Landing Zone spec",
        "description": f"Generated from lz_spec.schema v{wb.SCHEMA_VERSION}. "
                       "The python schema is authoritative; regenerate after "
                       "any schema change (python -m lz_pipeline.tools.gen_jsonschema).",
        "type": "object",
        "required": ["format", "schema_version", "customer", "sheets"],
        "properties": {
            "format": {"type": "string", "pattern": "^lz-spec-ir/"},
            "schema_version": {"type": "string"},
            "customer": {"type": "string"},
            "source": {"type": "string"},
            "provenance": {
                "type": "object",
                "description": "Questionnaire lineage stamped by `lzctl assess`. "
                               "When source_type is 'questionnaire', `lzctl build` "
                               "requires the named decisions file to exist beside "
                               "the spec with matching customer and assessment_id.",
                "properties": {
                    "source_type": {"type": "string", "enum": ["questionnaire"]},
                    "decisions_file": {"type": "string"},
                    "assessment_id": {"type": "string",
                                      "pattern": "^[0-9a-f]{64}$"},
                    "decision_set_sha256": {
                        "type": "string", "pattern": "^[0-9a-f]{64}$",
                        "description": "Hash of the immutable decision set "
                                       "(ref/state/question/targets/"
                                       "default_if_silent - never resolution). "
                                       "build exits 3 when the manifest no "
                                       "longer matches."},
                    "decision_count": {"type": "integer",
                                       "description": "diagnostic; the hash "
                                                      "is authoritative"},
                    "customer": {"type": "string"},
                },
                "required": ["source_type", "decisions_file", "assessment_id",
                             "decision_set_sha256", "customer"],
            },
            "sheets": {"type": "object", "properties": sheets_props,
                       "additionalProperties": True},
        },
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out",
                    default=str(Path(__file__).resolve().parents[3]
                                / "schemas" / "lz.spec.schema.json"))
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(build_schema(), indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
