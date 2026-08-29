"""Dev-checkout path setup: one file instead of per-module sys.path hacks.

An installed distribution (`pip install -e .`) needs none of this; pytest and
direct script runs from a plain checkout get the three packages on the path.
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
for p in (_ROOT / "pipeline", _ROOT / "app"):
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)
