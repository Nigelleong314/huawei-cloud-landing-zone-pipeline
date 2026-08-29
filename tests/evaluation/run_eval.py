"""Model-matrix evaluation runner with deterministic scoring.

Usage:
  python tests/evaluation/run_eval.py [--models a,b,c] [--trials 2] [--only id1,id2]

Models default to the three capability tiers; every fixture is scored by
mechanical checks only (json shape, regex presence/absence, exact match) -
no judge model. Full transcripts and a scores.json land under
tests/evaluation/results/<timestamp>/ as committed evidence.
"""

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from adapter import run_model, AdapterError  # noqa: E402

DEFAULT_MODELS = ["claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5-20251001"]


def _strip_fences(text: str) -> str:
    t = text.strip()
    m = re.match(r"^```[a-zA-Z]*\n(.*)\n```$", t, re.S)
    return m.group(1).strip() if m else t


def _try_json(text: str):
    """Tolerant extraction, mirroring how the pipeline would consume model
    output: strict parse first, then the first fenced block, then the first
    balanced {...} / [...] span. A model that wraps correct JSON in prose
    fails the format instruction but not the schema check - the deterministic
    layer compensates, which is the architecture under test."""
    for candidate in (text.strip(), _strip_fences(text)):
        try:
            return json.loads(candidate)
        except Exception:
            pass
    m = re.search(r"```[a-zA-Z]*\n(.*?)\n```", text, re.S)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except Exception:
            pass
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        if start == -1:
            continue
        depth = 0
        for i in range(start, len(text)):
            if text[i] == opener:
                depth += 1
            elif text[i] == closer:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except Exception:
                        break
    return None


def score(fx: dict, text: str) -> dict:
    s = fx["scoring"]
    checks = {}
    body = text.strip()
    data = _try_json(body)

    if "json_keys" in s:
        checks["json_parses"] = data is not None and isinstance(data, dict)
        checks["json_keys"] = bool(checks["json_parses"]) and \
            all(k in data for k in s["json_keys"])
    if "json_equals" in s and isinstance(data, dict):
        for k, v in s["json_equals"].items():
            checks[f"json_equals:{k}"] = data.get(k) == v
    elif "json_equals" in s:
        checks["json_parses"] = False
    if "json_checks" in s and isinstance(data, dict):
        jc = s["json_checks"]
        if "open_questions_min_len" in jc:
            checks["open_questions_min"] = isinstance(data.get("open_questions"), list) \
                and len(data["open_questions"]) >= jc["open_questions_min_len"]
        if "workload_accounts_len" in jc:
            checks["accounts_len"] = isinstance(data.get("workload_accounts"), list) \
                and len(data["workload_accounts"]) == jc["workload_accounts_len"]
    if "json_array_min_len" in s:
        checks["json_array"] = isinstance(data, list) and \
            len(data) >= s["json_array_min_len"]
    if "json_expect_array" in s:
        want = [w.lower() for w in s["json_expect_array"]]
        got = [str(x).strip().lower() for x in data] if isinstance(data, list) else None
        checks["array_order"] = got == want
    if "expect_exact" in s:
        checks["exact"] = body.strip().strip("`\"'.").lower() == s["expect_exact"].lower()
    for pat in s.get("must_contain", []):
        checks[f"has:{pat[:24]}"] = re.search(pat, body, re.I) is not None
    if "must_contain_any" in s:
        groups = s["must_contain_any"]
        if groups and isinstance(groups[0], list):
            for gi, group in enumerate(groups):
                checks[f"has_any:{gi}"] = any(re.search(p, body, re.I) for p in group)
        else:
            checks["has_any"] = any(re.search(p, body, re.I) for p in groups)
    for pat in s.get("must_not_contain", []):
        checks[f"absent:{pat[:24]}"] = re.search(pat, body, re.I) is None

    return {"pass": all(checks.values()) and bool(checks), "checks": checks}


def rescore(results_dir: Path) -> int:
    """Re-score saved transcripts with the current fixtures/scorer.
    No model calls: responses are immutable evidence; scoring is versioned."""
    doc = json.loads((HERE / "fixtures" / "fixtures.json").read_text(encoding="utf-8"))
    fxmap = {f["id"]: f for f in doc["fixtures"]}
    rows = []
    for tf in sorted((results_dir / "transcripts").glob("*.json")):
        t = json.loads(tf.read_text(encoding="utf-8"))
        fx = fxmap.get(t["fixture"])
        if fx is None:
            continue
        verdict = score(fx, t["response"])
        rows.append({"model": t["model"], "fixture": t["fixture"],
                     "category": fx["category"], "trial": t["trial"],
                     "pass": verdict["pass"],
                     "failed_checks": [k for k, v in verdict["checks"].items() if not v]})
    agg = {}
    for r in rows:
        a = agg.setdefault((r["model"], r["category"]), {"pass": 0, "total": 0})
        a["total"] += 1
        a["pass"] += 1 if r["pass"] else 0
    out = results_dir / "scores-rescored.json"
    out.write_text(json.dumps({
        "note": "re-scored from saved transcripts after scorer fixes; "
                "responses unchanged",
        "summary": [{"model": m, "category": c, "passed": v["pass"], "total": v["total"]}
                    for (m, c), v in sorted(agg.items())],
        "rows": rows}, indent=2), encoding="utf-8")
    passed = sum(r["pass"] for r in rows)
    for (m, c), v in sorted(agg.items()):
        if v["pass"] != v["total"]:
            print(f"  still failing: {m} / {c}: {v['pass']}/{v['total']}")
    print(f"rescore: {passed}/{len(rows)} passed -> {out}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default=",".join(DEFAULT_MODELS))
    ap.add_argument("--trials", type=int, default=2)
    ap.add_argument("--only", help="comma list of fixture ids")
    ap.add_argument("--adapter", default=None)
    ap.add_argument("--rescore", metavar="RESULTS_DIR",
                    help="re-score saved transcripts; no model calls")
    args = ap.parse_args(argv)
    if args.rescore:
        return rescore(Path(args.rescore))

    doc = json.loads((HERE / "fixtures" / "fixtures.json").read_text(encoding="utf-8"))
    fixtures = doc["fixtures"]
    if args.only:
        keep = set(args.only.split(","))
        fixtures = [f for f in fixtures if f["id"] in keep]
    models = [m for m in args.models.split(",") if m]

    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = HERE / "results" / ts
    (out / "transcripts").mkdir(parents=True)

    rows, total_cost = [], 0.0
    for model in models:
        for fx in fixtures:
            for trial in range(1, args.trials + 1):
                prompt = doc["shared_context"] + "\n\n---\nTASK:\n" + fx["task"]
                tag = f"{model}--{fx['id']}--t{trial}"
                try:
                    r = run_model(model, prompt, adapter=args.adapter)
                    verdict = score(fx, r["text"])
                    cost = r.get("cost_usd") or 0.0
                    total_cost += cost
                    (out / "transcripts" / f"{tag}.json").write_text(json.dumps({
                        "model": model, "fixture": fx["id"], "trial": trial,
                        "prompt": prompt, "response": r["text"],
                        "cost_usd": cost, "session_id": r.get("session_id"),
                        "verdict": verdict}, indent=2, ensure_ascii=False),
                        encoding="utf-8")
                    rows.append({"model": model, "fixture": fx["id"],
                                 "category": fx["category"], "trial": trial,
                                 "pass": verdict["pass"], "cost_usd": cost})
                    print(f"{'PASS' if verdict['pass'] else 'FAIL'}  {tag}"
                          + ("" if verdict["pass"] else
                             f"  failed: {[k for k, v in verdict['checks'].items() if not v]}"))
                except AdapterError as e:
                    rows.append({"model": model, "fixture": fx["id"],
                                 "category": fx["category"], "trial": trial,
                                 "pass": False, "error": str(e)[:200]})
                    print(f"ERROR {tag}: {e}")

    # aggregate: per model x category
    agg = {}
    for r in rows:
        key = (r["model"], r["category"])
        a = agg.setdefault(key, {"pass": 0, "total": 0})
        a["total"] += 1
        a["pass"] += 1 if r["pass"] else 0
    summary = [{"model": m, "category": c, "passed": v["pass"], "total": v["total"]}
               for (m, c), v in sorted(agg.items())]
    (out / "scores.json").write_text(json.dumps({
        "run": ts, "models": models, "trials": args.trials,
        "total_runs": len(rows), "total_cost_usd": round(total_cost, 4),
        "summary": summary, "rows": rows}, indent=2), encoding="utf-8")

    print(f"\n== matrix: {len(rows)} runs, ${total_cost:.2f} ==")
    width = max(len(m) for m in models) + 2
    cats = sorted({r['category'] for r in rows})
    print(" " * width + "  ".join(f"{c[:14]:>14}" for c in cats))
    for m in models:
        cells = []
        for c in cats:
            v = agg.get((m, c), {"pass": 0, "total": 0})
            cells.append(f"{v['pass']}/{v['total']:>2}".rjust(14))
        print(m.ljust(width) + "  ".join(cells))
    print(f"\nresults -> {out}")
    overall = sum(r["pass"] for r in rows)
    print(f"overall: {overall}/{len(rows)} passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
