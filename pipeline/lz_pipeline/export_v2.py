"""Profile-driven customer artifact export (release v2).

Extends the legacy exporter with:
  - customer PROFILES: feature flags applied at GENERATION time (a feature
    disabled in the profile is stripped from the staged artifact) - so exports
    are always re-runnable and in-place artifact surgery is never needed again;
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
        [--version 1.1.0] [--compat] [--no-workbook]

Profile (relative paths resolve against the profile file's directory):
    {"customer": "acme-corp",
     "features": {"secmaster": false},
     "envs_dir": "../envs",
     "docs_dir": "../handover-docs",
     "ir": "../lz_spec/lz.spec.acme.json",
     "skip_envs": ["99-sandbox"],     # env dirs not shipped (default: none)
     "ship_markdown": true}           # README/notes under modules/ and envs/

Library modules no shipped env uses are pruned from the artifact. State is
never shipped (the 00-bootstrap local state is handed over out of band).
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
from .core.features import strip_secmaster

# Invoking directory: the fallback for profile paths that do not exist
# relative to the profile file (see resolve_profile_paths).
ROOT = Path.cwd()
PKG = Path(__file__).resolve().parent
REPO = PKG.parent.parent                    # pipeline/lz_pipeline -> repo root
# The module tree to SHIP. Default: the repo's vendored snapshot. Override when
# the exported envs were deployed from a different module tree (a workspace
# whose env `source` paths point elsewhere): the artifact must carry the
# modules the estate actually runs, or the customer's first plan shows drift.
import os as _os
MODULES = Path(_os.environ.get("LZ_EXPORT_MODULES_DIR") or (REPO / "terraform" / "modules"))


# ────────────────────────────────────────────────────────────────────────────
# Artifact copy/rewrite: module paths, generated-file renames, and
# the exclusion sets (secrets, plan/backup litter, runner residue).
# ────────────────────────────────────────────────────────────────────────────

# generated fan-outs become ordinary files in the artifact; names that would
# collide with existing static files get an -accounts suffix
GENERATED_RENAMES = {
    "providers.generated.tf":     "providers-accounts.tf",
    "outputs.generated.tf":       "outputs-accounts.tf",
    "spokes.generated.tf":        "spokes.tf",
    "tagging.generated.tf":       "tagging.tf",
    "config.generated.tf":        "config.tf",
    "iam-baseline.generated.tf":  "iam-baseline.tf",
    "app-permission-sets.generated.tf": "app-permission-sets.tf",
    "cost-centers.generated.tf":  "cost-centers.tf",
    "observability.generated.tf": "observability.tf",
    "logconverge.generated.tf":   "logconverge.tf",
    "vpn.generated.tf":           "vpn.tf",
    "sgacl.generated.tf":         "sgacl.tf",
}

# .lz-customer is a BUILD GUARD (a spec for another customer refuses to build
# against this tree); it is meaningless to the recipient, so it stays in the
# working tree and never ships.
EXCLUDE_NAMES = {"secrets.auto.tfvars.json", "errored.tfstate",
                 ".lzctl.lock", ".gitignore", ".gitattributes", ".lz-customer"}
# .txt: stray plan/log captures
EXCLUDE_SUFFIXES = (".bak", ".backup", ".ps1", ".py", ".xlsx", ".txt", ".log")

# A PLAN FILE IN ANY SPELLING IS A SECRET. Every rendering embeds each
# variable value - the master AK/SK included - and the binary form is a zip
# container carrying `tfplan` PLUS a full copy of `tfstate`/`tfstate-prev`.
# Two real handover exports leaked this way before the rule was general:
# plan.json (2026-09-08) and tfplan.bin (2026-09-09). Match the class, not
# the filenames someone happened to use.
_PLAN_FILE = re.compile(
    r"""^(?:tf[.\-_]?plan|plan)          # tfplan / tf.plan / tf-plan / plan
         (?:[.\-_].*)?                   # any suffix chain (.bin/.json/.out/…)
         $|
         \.(?:tfplan|plan\.json)$        # <name>.tfplan / <name>.plan.json
      """, re.I | re.X)
# .git: an env tree kept under version control would otherwise ship its whole
# history - internal commit messages, and every earlier revision of files that
# are deliberately filtered here.
EXCLUDE_DIRS = {".terraform", "__pycache__", "lzctl-logs", "state-backups", ".git"}


def path_rewrite() -> tuple:
    """(source-tree module root, artifact module root) as quoted source
    prefixes: whatever root the envs were built against (LZ_MODULE_SOURCE_ROOT)
    becomes modules/ beside envs/ in the artifact."""
    from .core import helpers
    root = str(helpers.MODULE_SOURCE_ROOT).replace("\\", "/").rstrip("/")
    return (f'"{root}/', '"../../modules/')


# An envs tree may carry its own modules in <envs>/modules (customer-only code the
# product library does not ship). In the artifact they sit in modules/ with the
# library, one level further from the envs.
OWN_MODULES_REWRITE = ('"../modules/', '"../../modules/')


def excluded(p: Path, exclude_names: set) -> bool:
    if p.name in exclude_names:
        return True
    if _PLAN_FILE.search(p.name):
        return True
    if any(p.name.endswith(s) for s in EXCLUDE_SUFFIXES):
        return True
    # State never ships, in any spelling - not even the 00-bootstrap local
    # state: it is handed over out of band (see the artifact-handover notes).
    # state-*.json covers the runbooks' `terraform state pull > state-...json`
    # backup convention in every spelling.
    if ".tfstate" in p.name:
        return True
    if p.name.startswith("state-") and p.name.endswith(".json"):
        return True
    # Questionnaire dumps are raw customer answers VERBATIM - including any
    # secret a customer pasted into one (lzctl intake copies, never filters;
    # the round-3 benchmark's planted PSK survived only in the dump). They
    # are working material, never a deliverable.
    if p.name.endswith("dump.json"):
        return True
    if p.name.endswith(".pre-rename.backup"):
        return True
    return False


def copy_tree(src: Path, dst: Path, rewrite: bool, exclude_names: set = EXCLUDE_NAMES,
              skip_top: tuple = (), extra_rewrites: tuple = ()):
    n = 0
    for p in sorted(src.rglob("*")):
        if p.is_dir() or any(d in p.parts for d in EXCLUDE_DIRS) or excluded(p, exclude_names):
            continue
        rel = p.relative_to(src)
        if rel.parts[0] in skip_top:
            continue
        name = GENERATED_RENAMES.get(rel.name, rel.name)
        out = dst / rel.parent / name
        out.parent.mkdir(parents=True, exist_ok=True)
        # .example too: the tfvars examples name the generated files, and a
        # recipient never sees the ".generated" spelling.
        if rewrite and p.suffix in (".tf", ".md", ".example"):
            text = p.read_text(encoding="utf-8")
            # quote-anchored, so neither rewrite matches the other's output
            for old_txt, new_txt in extra_rewrites:
                text = text.replace(old_txt, new_txt)
            text = text.replace(*path_rewrite())
            # generated filenames mentioned in comments -> artifact names
            for gname, plain in GENERATED_RENAMES.items():
                text = text.replace(gname, plain)
            # newline is forced: write_text translates to CRLF on Windows, which
            # would make the artifact ship mixed line endings by build host
            out.write_text(text, encoding="utf-8", newline=chr(10))
        else:
            shutil.copy2(p, out)
        n += 1
    return n


def copy_customer_modules(envs: Path, dst: Path, library: Path,
                          exclude_names: set = EXCLUDE_NAMES) -> int:
    """Copy <envs>/modules into the artifact's modules/; refuse to shadow a library module."""
    own = envs / "modules"
    if not own.is_dir():
        return 0
    names = {p.name for p in own.iterdir() if p.is_dir()}
    clash = sorted(names & {p.name for p in library.iterdir() if p.is_dir()}) if library.is_dir() else []
    if clash:
        raise SystemExit(f"export refused: customer module(s) {clash} would shadow library modules of "
                         "the same name - rename them in the envs tree")
    return copy_tree(own, dst, rewrite=True, exclude_names=exclude_names)


_ENV_SOURCE = re.compile(r'^\s*source\s*=\s*"(\.\.?/[^"]*)"', re.M)
_SIBLING_SOURCE = re.compile(r'^\s*source\s*=\s*"\.\./([^/".]+)', re.M)


def prune_modules(target: Path) -> list:
    """Delete artifact modules no shipped env (or module they call) uses.

    Every local env source must already point at ../../modules/<name>; one
    that does not would break in the artifact, and would make its module look
    unused - refuse rather than ship it."""
    mods, envs = target / "modules", target / "envs"
    if not mods.is_dir() or not envs.is_dir():
        return []
    used, bad = set(), []
    for p in envs.rglob("*.tf"):
        for src in _ENV_SOURCE.findall(p.read_text(encoding="utf-8")):
            if src.startswith("../../modules/"):
                used.add(src.split("/")[3])
            else:
                bad.append(f"{p.relative_to(target).as_posix()}: {src}")
    if bad:
        raise SystemExit("export refused: module sources outside the artifact's modules/ "
                         "(set LZ_MODULE_SOURCE_ROOT to the root the envs were built "
                         "against):\n  " + "\n  ".join(bad[:20]))
    queue = list(used)
    while queue:
        for p in (mods / queue.pop()).rglob("*.tf"):
            for name in _SIBLING_SOURCE.findall(p.read_text(encoding="utf-8")):
                if name not in used:
                    used.add(name)
                    queue.append(name)
    dropped = sorted(d.name for d in mods.iterdir() if d.is_dir() and d.name not in used)
    for name in dropped:
        shutil.rmtree(mods / name)
    return dropped


def drop_envs_from_deps(deps_path: Path, skipped: set):
    """Remove skipped envs from a shipped deps.json (order and graph)."""
    if not skipped or not deps_path.exists():
        return
    doc = json.loads(deps_path.read_text(encoding="utf-8"))
    doc["apply_order"] = [e for e in doc.get("apply_order", []) if e not in skipped]
    envs = doc.get("envs") or {}
    for name in skipped:
        envs.pop(name, None)
    for name, node in envs.items():
        lost = sorted(set(node.get("consumes", [])) & skipped)
        if lost:
            print(f"  WARNING: shipped env {name} consumes skipped env(s) {lost}")
    deps_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8", newline="\n")


def resolve_profile_paths(profile: dict, profile_dir: Path) -> dict:
    """Relative envs_dir/docs_dir/ir resolve against the profile file's own
    directory. A path that only exists relative to the invoking directory
    (the older convention) still resolves there, with a note."""
    out = dict(profile)
    for key in ("envs_dir", "docs_dir", "ir"):
        val = profile.get(key)
        if not val or Path(val).is_absolute():
            continue
        here = (profile_dir / val).resolve()
        legacy = (ROOT / val).resolve()
        if not here.exists() and legacy.exists():
            print(f"  note: profile {key} {val!r} resolved against the current directory; "
                  "write it relative to the profile file", file=sys.stderr)
            here = legacy
        out[key] = str(here)
    return out


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

def _assert_no_source_secrets(envs: Path, target: Path) -> None:
    """Abort if any value from the source tree's secrets files reached the
    artifact. The exclusion lists say what NOT to copy; this says what must
    not be present however it got there - the check that would have caught
    both the plan.json and tfplan.bin leaks on its own."""
    secrets = set()
    for sf in envs.rglob("secrets.auto.tfvars.json"):
        try:
            for v in json.loads(sf.read_text(encoding="utf-8")).values():
                if isinstance(v, str) and len(v) >= 12:
                    secrets.add(v.encode())
        except (OSError, ValueError):
            continue
    if not secrets:
        return
    hits = []
    for p in target.rglob("*"):
        if not p.is_file():
            continue
        blob = p.read_bytes()
        if any(s in blob for s in secrets):
            hits.append(p.relative_to(target).as_posix())
    if hits:
        sep = "\n  "
        raise SystemExit(
            "ABORT: artifact contains value(s) from the source secrets files - "
            "refusing to ship a credential leak. Offending files:" + sep
            + sep.join(hits[:20]))


def export(profile: dict, target: Path, version: str, compat: bool,
           releases_dir: Path, no_workbook: bool = False) -> int:
    # main() makes profile paths absolute; ROOT only anchors direct callers
    envs = ROOT / profile["envs_dir"]
    docs_rel = profile.get("docs_dir")
    docs = (ROOT / docs_rel) if docs_rel else None
    ir_path = ROOT / profile["ir"] if profile.get("ir") else None

    # deps.json ships except in compat mode
    exclude_names = EXCLUDE_NAMES | {"deps.json"} if compat else EXCLUDE_NAMES

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

    n_mod = copy_tree(MODULES, target / "modules", rewrite=True, exclude_names=exclude_names)
    n_mod += copy_customer_modules(envs, target / "modules", MODULES, exclude_names)
    # skip_envs: env dirs the profile does not ship (they stay in the tree)
    skip_envs = set(profile.get("skip_envs") or ())
    unknown = sorted(skip_envs - {p.name for p in envs.iterdir() if p.is_dir()})
    if unknown:
        print(f"  WARNING: skip_envs names no env dir: {unknown}")
    n_env = copy_tree(envs, target / "envs", rewrite=True, exclude_names=exclude_names,
                      skip_top=("modules", *sorted(skip_envs)),
                      extra_rewrites=(OWN_MODULES_REWRITE,))
    if not profile.get("ship_markdown", True):
        for md in [*(target / "modules").rglob("*.md"), *(target / "envs").rglob("*.md")]:
            md.unlink()

    # The artifact is read by someone with no access to our history or
    # tooling. Refuse to ship one whose comments say otherwise.
    from .comment_lint import run as _comment_lint
    if _comment_lint([str(target / "modules"), str(target / "envs")]):
        print("export refused: the tree breaks the comment convention",
              file=sys.stderr)
        sys.exit(1)
    n_doc = 0
    wb_copied = False
    if docs is not None and docs.exists():
        n_doc = copy_tree(docs, target, rewrite=False, exclude_names=exclude_names)
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
    # the envs tree's root .gitignore when the docs bring none (lock files tracked)
    if not (target / ".gitignore").exists() and (envs / ".gitignore").exists():
        shutil.copy2(envs / ".gitignore", target / ".gitignore")

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

    # feature strip
    feats = profile.get("features") or {}
    if "secmaster" in feats and not feats["secmaster"]:
        strip_secmaster(target / "envs" / "07-security")
        print("  feature secmaster=off: stripped from envs/07-security")

    # curation: only the modules the shipped envs use, and a deps.json
    # without the envs that were not shipped
    dropped = prune_modules(target)
    if dropped:
        print(f"  pruned unused modules: {', '.join(dropped)}")
    drop_envs_from_deps(target / "envs" / "deps.json", skip_envs)

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
    import os
    ap = argparse.ArgumentParser(prog=os.environ.get("LZ_INVOKED_AS") or None)
    ap.add_argument("--profile", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--version", default="1.0.0")
    ap.add_argument("--compat", action="store_true",
                    help="legacy-identical output (no runner/release files)")
    ap.add_argument("--no-workbook", action="store_true",
                    help="skip generating landing-zone-spec.xlsx into the artifact")
    ap.add_argument("--releases-dir", default=str(ROOT / "releases"))
    args = ap.parse_args(argv)
    profile_path = Path(args.profile).resolve()
    profile = resolve_profile_paths(json.loads(profile_path.read_text(encoding="utf-8")),
                                    profile_path.parent)
    return export(profile, Path(args.target), args.version, args.compat,
                  Path(args.releases_dir), args.no_workbook)


if __name__ == "__main__":
    sys.exit(main())
