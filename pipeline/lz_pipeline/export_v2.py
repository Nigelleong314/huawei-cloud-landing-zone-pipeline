"""Profile-driven customer artifact export (release v2).

Extends the legacy exporter with:
  - customer PROFILES: feature flags applied at GENERATION time (a feature
    disabled in the profile is stripped from the staged artifact by the
    data-driven registry below) - so exports are always re-runnable and
    in-place artifact surgery is never needed again;
  - a RUNNER: lzctl.py + plan_triage.py + deps.json ship in the artifact;
  - RELEASE metadata: VERSION, CHANGELOG.md generated from the spec-IR diff
    against the previous release snapshot, and a MANIFEST carrying the
    pipeline/schema coordinates.

--compat reproduces the legacy artifact byte-for-byte (no runner, no release
files) and exists for the oracle test against the shipped tree.

The Excel LLD workbook is generated from the profile's own spec IR into the
artifact root, so every profile ships one and it always matches the spec that
produced the envs (--no-workbook opts out).

Usage:
    py -m lz_pipeline.export_v2 --profile profiles/acme.json --target <dir>
        [--version 1.1.0] [--compat] [--no-docs] [--no-workbook]

Profile:
    {"customer": "acme-corp",
     "features": {"secmaster": false},
     "envs_dir": "envs",       # relative to workspace root
     "docs_dir": "handover-docs",
     "ir": "lz_spec/lz.spec.acme.json"}
"""

import argparse
import datetime
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from . import model
from lz_spec import export_handover as legacy

# Workspace root: profile paths (envs_dir/docs_dir/ir) resolve against the
# invoking workspace, not the package location.
ROOT = Path.cwd()
PKG = Path(__file__).resolve().parent


# ────────────────────────────────────────────────────────────────────────────
# Feature strips (data, not code): what disabling a feature removes.
# Spans were derived from - and are oracle-tested against - the reviewed
# removal in the shipped artifact.
# ────────────────────────────────────────────────────────────────────────────

FEATURES = {
    "secmaster": {
        "env": "07-security",
        "ops": [
            {"file": "main.tf", "op": "remove_block",
             "header": r'data "terraform_remote_state" "observability" \{', "eat_blank_before": True},
            {"file": "main.tf", "op": "remove_lines",
             "match": r'^  observability = data\.terraform_remote_state\.observability\.outputs$'},
            {"file": "main.tf", "op": "remove_span",
             "start": r'^\n  # Wire SecMaster cloud_log_resources',
             "end": r'^  \]$'},
            {"file": "main.tf", "op": "remove_span",
             "start": r'^\n# Warn \(not fail\) when SecMaster deploys',
             "end": r'^\}$'},
            {"file": "main.tf", "op": "remove_block",
             "header": r'module "security" \{', "eat_blank_before": True},
            {"file": "variables.tf", "op": "remove_variables",
             "names": ["observability_state_bucket", "observability_state_key",
                       "security_account", "enable_secmaster", "secmaster_workspace_name",
                       "secmaster_modules", "alert_rules", "enable_hss", "enable_dbss",
                       "enable_member_workspaces", "member_workspace_bindings"]},
            {"file": "outputs.tf", "op": "replace",
             "old": 'output "secmaster_workspace_id" { value = module.security.secmaster_workspace_id }',
             "new": "# No outputs: edge protection exposes nothing downstream."},
            {"file": "providers.tf", "op": "remove_block",
             "header": r'provider "huaweicloud" \{\n  alias              = "lz_security"',
             "eat_blank_before": True},
            {"file": "terraform.tfvars.json", "op": "remove_tfvars_keys",
             "keys": ["observability_state_bucket", "secmaster_modules", "security_account"]},
            {"file": "terraform.tfvars.example", "op": "remove_lines",
             "match": r'^(observability_state_bucket|# enable_secmaster|# enable_hss|# enable_dbss'
                      r'|# enable_member_workspaces|# member_workspace_bindings)'},
            # the reviewed artifact keeps a separating blank line in locals
            {"file": "main.tf", "op": "replace",
             "old": "network       = data.terraform_remote_state.network.outputs\n}",
             "new": "network       = data.terraform_remote_state.network.outputs\n\n}"},
        ],
    },
}


def _find_block(text: str, header_re: str):
    """(start, end) of the block whose opening line matches header_re; the
    span runs to the matching closing brace, inclusive of the trailing \\n."""
    m = re.search(header_re, text)
    if not m:
        return None
    i = text.index("{", m.start())
    depth = 0
    for j in range(i, len(text)):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                end = j + 1
                if end < len(text) and text[end] == "\n":
                    end += 1
                return m.start(), end
    return None


def apply_strip(env_dir: Path, ops: list) -> list:
    notes = []
    for op in ops:
        p = env_dir / op["file"]
        if not p.exists():
            notes.append(f"skip {op['file']}: not present")
            continue
        text = p.read_text(encoding="utf-8")
        kind = op["op"]
        if kind == "remove_block":
            span = _find_block(text, op["header"])
            if span is None:
                notes.append(f"{op['file']}: block {op['header']!r} not found")
                continue
            s, e = span
            if op.get("eat_blank_before") and s >= 1 and text[s - 1] == "\n" and (s < 2 or text[s - 2] == "\n"):
                s -= 1
            text = text[:s] + text[e:]
        elif kind == "remove_lines":
            lines = text.split("\n")
            text = "\n".join(l for l in lines if not re.match(op["match"], l))
        elif kind == "remove_span":
            ms = re.search(op["start"], text, re.M)
            if not ms:
                notes.append(f"{op['file']}: span start not found")
                continue
            me = re.search(op["end"], text[ms.start():], re.M)
            if not me:
                notes.append(f"{op['file']}: span end not found")
                continue
            end = ms.start() + me.end()
            if end < len(text) and text[end] == "\n":
                end += 1
            text = text[:ms.start()] + text[end:]
        elif kind == "remove_variables":
            for name in op["names"]:
                span = _find_block(text, rf'variable "{name}" \{{')
                if span:
                    s, e = span
                    text = text[:s] + text[e:]
            text = re.sub(r"\n{4,}", "\n\n\n", text)
        elif kind == "replace":
            text = text.replace(op["old"], op["new"])
        elif kind == "remove_tfvars_keys":
            data = json.loads(text)
            for k in op["keys"]:
                data.pop(k, None)
            text = json.dumps(data, indent=2, sort_keys=False) + "\n"
        p.write_text(text, encoding="utf-8")
    return notes


# ────────────────────────────────────────────────────────────────────────────
# Release metadata
# ────────────────────────────────────────────────────────────────────────────

def _row_key(row: dict):
    for k in ("Name", "VPCName", "Policy", "UserName", "Package", "Domain", "Namespace",
              "Account", "Key", "Zone", "Endpoint"):
        if row.get(k):
            return str(row[k])
    return json.dumps(row, sort_keys=True)[:60]


def spec_changelog(prev: dict, cur: dict) -> list:
    lines = []
    ps, cs = prev.get("sheets", {}), cur.get("sheets", {})
    for sheet in sorted(set(ps) | set(cs)):
        pt, ct = ps.get(sheet) or {}, cs.get(sheet) or {}
        for table in sorted(set(pt) | set(ct)):
            a, b = pt.get(table), ct.get(table)
            if a == b:
                continue
            if isinstance(a, dict) or isinstance(b, dict):
                a, b = a or {}, b or {}
                for k in sorted(set(a) | set(b)):
                    if a.get(k) != b.get(k):
                        lines.append(f"- {sheet}.{table}.{k}: {a.get(k)!r} -> {b.get(k)!r}")
            elif isinstance(a, list) or isinstance(b, list):
                if a and isinstance(a[0], dict) or b and isinstance(b[0], dict):
                    ka = {_row_key(r): r for r in (a or [])}
                    kb = {_row_key(r): r for r in (b or [])}
                    for k in sorted(set(kb) - set(ka)):
                        lines.append(f"- {sheet}.{table}: added {k!r}")
                    for k in sorted(set(ka) - set(kb)):
                        lines.append(f"- {sheet}.{table}: removed {k!r}")
                    for k in sorted(set(ka) & set(kb)):
                        if ka[k] != kb[k]:
                            lines.append(f"- {sheet}.{table}: changed {k!r}")
                else:
                    lines.append(f"- {sheet}.{table}: list changed "
                                 f"({len(a or [])} -> {len(b or [])} entries)")
    return lines


# ────────────────────────────────────────────────────────────────────────────
# Export
# ────────────────────────────────────────────────────────────────────────────

def export(profile: dict, target: Path, version: str, compat: bool,
           no_docs: bool, releases_dir: Path, no_workbook: bool = False) -> int:
    envs = ROOT / profile["envs_dir"]
    docs_rel = profile.get("docs_dir")
    docs = (ROOT / docs_rel) if docs_rel else None
    if docs is None:
        no_docs = True
    ir_path = ROOT / profile["ir"] if profile.get("ir") else None

    # runner residue never ships; deps.json ships except in compat mode
    legacy.EXCLUDE_DIRS = set(legacy.EXCLUDE_DIRS) | {"lzctl-logs", "state-backups"}
    legacy.EXCLUDE_NAMES = set(legacy.EXCLUDE_NAMES) | {".lzctl.lock", "tf.plan"}
    # plan files embed variable values (incl. secrets) - never ship any of them
    legacy.EXCLUDE_SUFFIXES = tuple(set(legacy.EXCLUDE_SUFFIXES) | {".tfplan", ".log"})
    if compat:
        legacy.EXCLUDE_NAMES |= {"deps.json"}

    # Clear CONTENTS but keep the target directory itself: removing the root
    # fails with PermissionError when any process holds the folder open, and
    # rmtree deletes children before dying - a half-gutted artifact. Deleting
    # per-child leaves the root handle untouched.
    if target.exists():
        children = list(target.iterdir())
        # Data-loss guard: only clear a directory that is empty or provably a
        # previous export (carries our marker files). Refuses --target ., the
        # repo root, a source envs tree, or any other populated directory.
        if children and not any((target / m).exists()
                                for m in ("MANIFEST.txt", "VERSION")):
            raise SystemExit(
                f"refusing to clear {target}: it contains files but no previous "
                "export (MANIFEST.txt/VERSION) - use an empty or dedicated "
                "artifact directory")
        for child in children:
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    else:
        target.mkdir(parents=True)

    n_mod = legacy.copy_tree(legacy.MODULES, target / "modules", rewrite=True)
    n_env = legacy.copy_tree(envs, target / "envs", rewrite=True)
    n_doc = 0
    wb_copied = False
    if not no_docs and docs.exists():
        n_doc = legacy.copy_tree(docs, target, rewrite=False)
        if (docs / ".gitignore").exists():
            shutil.copy2(docs / ".gitignore", target / ".gitignore")
            n_doc += 1
        # A workbook already sitting in docs_dir is superseded by the generated
        # one below; copy it only as a fallback for profiles that carry no IR.
        wb = docs / "landing-zone-spec.xlsx"
        if wb.exists():
            shutil.copy2(wb, target / wb.name)
            n_doc += 1
            wb_copied = True

    # The Excel LLD workbook is a first-class artifact, GENERATED from this
    # profile's own spec IR - so every profile ships one, always matching the
    # spec that produced the envs (a docs_dir copy could be stale or another
    # customer's).
    if not no_workbook and ir_path and ir_path.exists():
        out_wb = target / "landing-zone-spec.xlsx"
        r = subprocess.run([sys.executable, "-X", "utf8", "-m", "lz_pipeline.tools.gen_workbook",
                            "--ir", str(ir_path), "-o", str(out_wb)],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", cwd=str(ROOT))
        if r.returncode != 0:
            print(r.stdout[-600:], r.stderr[-600:])
            print("FAIL: workbook generation failed")
            return 1
        if not out_wb.exists():
            print("FAIL: workbook was not written")
            return 1
        if not wb_copied:
            n_doc += 1
        print(f"  workbook: generated from {ir_path.name}")

    # feature strips
    for feature, enabled in (profile.get("features") or {}).items():
        if enabled or feature not in FEATURES:
            continue
        spec = FEATURES[feature]
        notes = apply_strip(target / "envs" / spec["env"], spec["ops"])
        for n in notes:
            print(f"  strip[{feature}]: {n}")
        print(f"  feature {feature}=off: stripped from envs/{spec['env']}")

    # runner + release metadata (not in compat mode)
    if not compat:
        runner = target / "runner"
        runner.mkdir()
        shutil.copy2(PKG / "lzctl.py", runner / "lzctl.py")
        shutil.copy2(PKG / "tools" / "plan_triage.py", runner / "plan_triage.py")
        pricing_src = PKG / "tools" / "pricing"
        if pricing_src.exists():
            shutil.copytree(pricing_src, runner / "pricing")
        (runner / "README.md").write_text(
            "# lzctl - the landing-zone runner\n\n"
            "Requires Python 3.10+ and terraform on PATH. Start with:\n\n"
            "    py lzctl.py preflight --envs-dir ..\\envs\n"
            "    py lzctl.py plan --envs-dir ..\\envs --all\n\n"
            "See the root README and cookbooks for the operating procedures.\n",
            encoding="utf-8")

        (target / "VERSION").write_text(version + "\n", encoding="utf-8")

        changelog = [f"# Release {version} - {datetime.date.today().isoformat()}", ""]
        if ir_path and ir_path.exists():
            cur = model.load(ir_path)
            prev_release = None
            rels = releases_dir / profile["customer"]
            if rels.exists():
                versions = sorted((d.name for d in rels.iterdir() if d.is_dir()),
                                  key=lambda v: [int(x) for x in re.findall(r"\d+", v)] or [0])
                if versions:
                    prev_release = versions[-1]
            if prev_release:
                prev = model.load(rels / prev_release / "lz.spec.json")
                delta = spec_changelog(prev, cur)
                changelog += [f"Changes against release {prev_release}:", ""]
                changelog += delta if delta else ["- no specification changes (pipeline/module release)"]
            else:
                changelog += ["Initial release."]
            snap = rels / version
            snap.mkdir(parents=True, exist_ok=True)
            model.save(cur, snap / "lz.spec.json")
        else:
            changelog += ["(no spec IR referenced in the profile - changelog not derived)"]
        (target / "CHANGELOG.md").write_text("\n".join(changelog) + "\n", encoding="utf-8")

    # manifest
    from lz_spec import schema as wb_schema
    header = [f"# Handover artifact - exported {datetime.date.today().isoformat()} by export_v2",
              "# Regenerate with: py -m lz_pipeline.export_v2 --profile <profile> --target <dir>"]
    if not compat:
        header += [f"# customer: {profile['customer']}  version: {version}  "
                   f"schema: {wb_schema.SCHEMA_VERSION}",
                   "# features: " + json.dumps(profile.get("features") or {})]
    manifest = header + [""]
    for p in sorted(target.rglob("*")):
        if p.is_file() and p.name != "MANIFEST.txt":
            digest = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
            manifest.append(f"{digest}  {p.relative_to(target).as_posix()}")
    (target / "MANIFEST.txt").write_text("\n".join(manifest) + "\n", encoding="utf-8")

    print(f"exported: {n_mod} module files, {n_env} env files, {n_doc} doc files -> {target}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--version", default="1.0.0")
    ap.add_argument("--compat", action="store_true",
                    help="legacy-identical output (no runner/release files)")
    ap.add_argument("--no-docs", action="store_true")
    ap.add_argument("--no-workbook", action="store_true",
                    help="skip generating landing-zone-spec.xlsx into the artifact")
    ap.add_argument("--releases-dir", default=str(ROOT / "releases"))
    args = ap.parse_args(argv)
    profile = json.loads(Path(args.profile).read_text(encoding="utf-8"))
    return export(profile, Path(args.target), args.version, args.compat,
                  args.no_docs, Path(args.releases_dir), args.no_workbook)


if __name__ == "__main__":
    sys.exit(main())
