"""lz_app - a local web application over the landing-zone pipeline.

Schema-driven UI to fill the spec (the "Excel" content), run validation and
derivation, build the Terraform envs, operate them (via the untouched
lz_pipeline/lzctl.py), and export customer artifacts.

The app is a TOOL; it operates on a WORKSPACE (the checkout containing
lz_pipeline/, lz_spec/, huawei-lz/). Discovery order: --workspace flag,
LZ_WORKSPACE env var, walk-up from CWD, walk-up from this file (covers the
in-repo layout ldz/lz_app/lz_app/).
"""

import os
import sys
from pathlib import Path

__version__ = "1.0.0"


def find_workspace(explicit: str = None) -> Path:
    """The workspace is a DATA directory (spec files + envs trees), not a
    code checkout: code comes from the installed packages. Resolution:
    --workspace flag, LZ_WORKSPACE, then a walk-up looking for something
    workspace-shaped, else the current directory (specs/ created on use)."""
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    if os.environ.get("LZ_WORKSPACE"):
        candidates.append(Path(os.environ["LZ_WORKSPACE"]))
    if candidates:
        c = candidates[0]
        if not c.is_dir():
            raise SystemExit(f"workspace not found: {c}")
        return c.resolve()
    p = Path.cwd()
    for _ in range(6):
        if ((p / "specs").is_dir() or (p / "lz_spec").is_dir()
                or (p / "envs").is_dir() or list(p.glob("lz.spec.*.json"))):
            return p.resolve()
        p = p.parent
    return Path.cwd().resolve()


def wire(workspace: Path):
    """Kept for compatibility; packages are installed, nothing to inject."""
    return None
