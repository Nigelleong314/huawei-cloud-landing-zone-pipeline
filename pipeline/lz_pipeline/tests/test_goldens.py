"""Golden test: the pipeline reproduces the captured goldens byte-for-byte.
Any emitter change that alters output fails here, per-file.

The fixture is FROZEN synthetic input, never a live customer spec: goldens
answer "did the generator change?", which is only meaningful when the input is
held still. Customer trees are covered by verify_pipeline's regen-diff, which
compares a rebuild against the live tree and so tolerates legitimate spec
edits. Adding a fixture is fine; pointing one at a customer spec is not.

Run: py tests/test_goldens.py
"""

import filecmp
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
PKG = HERE.parent
ROOT = PKG.parent.parent
GOLD = HERE / "goldens"

FIXTURES = {
    "example": PKG / "fixtures" / "example.spec.json",
}
KEEP = ("terraform.tfvars.json", "backend.hcl")

failed = []
for name, ir in FIXTURES.items():
    gold = GOLD / name
    if not gold.exists():
        print(f"goldens missing for {name}; run tests/make_goldens.py first")
        sys.exit(2)
    env = dict(os.environ)
    env.pop("HW_ACCESS_KEY", None)
    env.pop("HW_SECRET_KEY", None)
    with tempfile.TemporaryDirectory(prefix=f"lz-gt-{name}-") as td:
        envs = Path(td) / "envs"
        r = subprocess.run([sys.executable, "-X", "utf8", "-m", "lz_pipeline", "build",
                            "--ir", str(ir), "--envs-dir", str(envs),
                            "--scaffold-dir", str(ROOT / "terraform" / "scaffold")],
                           capture_output=True, text=True, env=env, cwd=str(ROOT))
        if r.returncode != 0:
            print(r.stdout[-800:], r.stderr[-800:])
            print(f"FAIL {name}: build error")
            failed.append(name)
            continue
        got = {str(p.relative_to(envs)): p for p in envs.rglob("*")
               if p.is_file() and (p.name in KEEP or p.name.endswith(".generated.tf"))}
        want = {str(p.relative_to(gold)): p for p in gold.rglob("*") if p.is_file()}
        extra = set(got) - set(want)
        missing = set(want) - set(got)
        diffs = [rel for rel in set(got) & set(want)
                 if not filecmp.cmp(got[rel], want[rel], shallow=False)]
        if extra or missing or diffs:
            for x in sorted(extra):
                print(f"  {name}: EXTRA {x}")
            for x in sorted(missing):
                print(f"  {name}: MISSING {x}")
            for x in sorted(diffs):
                print(f"  {name}: DIFF {x}")
            failed.append(name)
        else:
            print(f"  ok   {name}: {len(want)} files byte-identical")

if failed:
    print(f"golden test FAILED: {failed}")
    sys.exit(1)
print("golden test passed")
