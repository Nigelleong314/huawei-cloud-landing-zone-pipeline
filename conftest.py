"""Dev-checkout path setup: one file instead of per-module sys.path hacks.

An installed distribution (`pip install -e .`) needs none of this. For a
plain checkout, pytest loads this file and both the in-process imports AND
every subprocess the tests spawn (they run `python -m lz_pipeline ...`)
must resolve the packages — so the paths go into os.environ["PYTHONPATH"]
as well as sys.path.
"""
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_PKG_DIRS = [str(_ROOT / "pipeline"), str(_ROOT / "app")]

for s in _PKG_DIRS:
    if s not in sys.path:
        sys.path.insert(0, s)

_existing = os.environ.get("PYTHONPATH", "")
_parts = [p for p in _existing.split(os.pathsep) if p]
for s in _PKG_DIRS:
    if s not in _parts:
        _parts.insert(0, s)
os.environ["PYTHONPATH"] = os.pathsep.join(_parts)
