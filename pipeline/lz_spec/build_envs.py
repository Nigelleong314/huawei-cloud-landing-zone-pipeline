"""Legacy workbook-path CLI - the pipeline engine lives in lz_pipeline.core.

    py build_envs.py <workbook> [--envs-dir ...] [--scaffold-dir ...] [--only ...]

Kept for the workbook->envs entry point (exercised by test_phase1's
byte-identity gate). The JSON-spec path is `py -m lz_pipeline build --ir ...`.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lz_pipeline.core.parsing import parse_workbook  # noqa: F401
from lz_pipeline.core.cli import main

if __name__ == "__main__":
    main()
