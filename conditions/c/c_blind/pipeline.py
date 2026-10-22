# Path: conditions/c/c_blind/pipeline.py
# Purpose: c_blind (C-v4.1) = c_single + a parent-blind contract phase before the repair, with its own prompt.
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from conditions.c.c_minimal.pipeline import PreRepairOutcome
from conditions.c.c_single.pipeline import SingleRepair
from conditions.c.c_blind.blind_contract import run_blind_contract
from conditions.c.c_blind.prompts import QUESTION_REPAIR_PROMPT


class BlindRepair(SingleRepair):
    """Everything c_single does, preceded by a separate parent-blind contract call."""

    name = "c_blind"
    revision = "C-v4.1 two-stage"
    policy = "blind"
    repair_prompt = QUESTION_REPAIR_PROMPT
    max_calls_per_question = 2
    pre_repair_output = "blind_contract.json"
    package_dir = Path(__file__).resolve().parent

    def pre_repair(self, row: Mapping[str, Any], run_root: Path, timeout: int) -> PreRepairOutcome:
        return run_blind_contract(row, run_root, timeout)
