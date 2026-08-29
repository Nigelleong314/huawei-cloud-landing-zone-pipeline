"""Dump a filled LZ Assessment Questionnaire to JSON for conversion.

Mechanical extraction only - no interpretation. The /questionnaire-to-spec
skill consumes this dump: prose answers are interpreted by the agent, appendix
rows are copied VERBATIM into the draft spec (never retyped).

Usage: py tools/dump_questionnaire.py <filled.xlsx> [-o out.json]
"""

import argparse
import json
import re
import sys
from pathlib import Path

SURVEY_SHEETS = ["Core Questions", "Deep-Dive Questions"]


def dump(path: Path) -> dict:
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True)

    wiring = {}
    meta = {}
    if "_wiring" in wb.sheetnames:
        for row in wb["_wiring"].iter_rows(min_row=2, values_only=True):
            ref, tier, cat, targets, default = (list(row) + [None] * 5)[:5]
            if ref == "_meta":
                for part in (targets or "").split(";"):
                    if "=" in part:
                        k, v = part.split("=", 1)
                        meta[k.strip()] = v.strip()
            elif ref:
                wiring[str(ref)] = {
                    "targets": [t.strip() for t in (targets or "").split(";") if t.strip()],
                    "default_if_silent": default or "",
                }

    answers = []
    for sheet in SURVEY_SHEETS:
        if sheet not in wb.sheetnames:
            continue
        for row in wb[sheet].iter_rows(min_row=3):
            ref, question, guidance, response = [row[i].value if i < len(row) else None
                                                 for i in range(4)]
            ref = str(ref).strip() if ref else ""
            if not re.fullmatch(r"[CD]\d+", ref):   # category band / blank row
                continue
            w = wiring.get(ref, {})
            answers.append({
                "ref": ref,
                "question": (question or "").strip(),
                "answer": (str(response).strip() if response is not None else ""),
                "targets": w.get("targets", []),
                "default_if_silent": w.get("default_if_silent", ""),
            })

    appendices = {}
    for sheet in wb.sheetnames:
        if not sheet.startswith("Appendix"):
            continue
        ws = wb[sheet]
        headers = [c.value for c in ws[3] if c.value is not None]
        rows = []
        for row in ws.iter_rows(min_row=4, values_only=True):
            vals = [("" if v is None else str(v).strip()) for v in row[:len(headers)]]
            if not any(vals):
                continue
            if vals[0].startswith("(example)"):
                continue
            rows.append(dict(zip(headers, vals)))
        ref = sheet.split(" ")[1]     # "Appendix A - Accounts" -> "A"
        w = wiring.get(ref, {})
        appendices[ref] = {"sheet": sheet, "targets": w.get("targets", []), "rows": rows}

    return {"source_file": path.name, "meta": meta,
            "answers": answers, "appendices": appendices}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("xlsx", help="filled questionnaire")
    ap.add_argument("-o", "--out", help="output JSON path (default: stdout)")
    args = ap.parse_args(argv)

    data = dump(Path(args.xlsx))
    answered = sum(1 for a in data["answers"] if a["answer"])
    text = json.dumps(data, indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}: {answered}/{len(data['answers'])} answered, "
              f"{sum(len(a['rows']) for a in data['appendices'].values())} appendix rows")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
