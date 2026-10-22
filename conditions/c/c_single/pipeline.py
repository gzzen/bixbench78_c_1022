# Path: conditions/c/c_single/pipeline.py
# Purpose: c_single (C-v5) = c_minimal + a required post-repair semantic audit, with its own prompt.
from __future__ import annotations

from pathlib import Path
from typing import Any

from conditions.c.c_minimal.pipeline import MinimalRepair
from conditions.c.c_single.prompts import SINGLE_REPAIR_PROMPT
from conditions.c.c_single.semantic_audit import validate_audit


class SingleRepair(MinimalRepair):
    """Everything c_minimal does, then analysis/semantic_audit.json must pass validate_audit."""

    name = "c_single"
    revision = "C-v5 single-call semantic audit"
    policy = "single"
    repair_prompt = SINGLE_REPAIR_PROMPT
    package_dir = Path(__file__).resolve().parent

    def post_validate(self, workspace: Path, qid: str) -> dict[str, Any]:
        return {**super().post_validate(workspace, qid), "semantic_audit": validate_audit(workspace, qid)}
