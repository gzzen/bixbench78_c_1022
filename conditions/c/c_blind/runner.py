#!/usr/bin/env python3
# Path: conditions/c/c_blind/runner.py
# Purpose: Entry point for c_blind; see conditions/c/README.md for the level hierarchy.
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from conditions.c.c_minimal.rescue_main import main  # noqa: E402
from conditions.c.c_blind.pipeline import BlindRepair  # noqa: E402

if __name__ == "__main__":
    main(BlindRepair())
