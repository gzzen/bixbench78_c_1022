# Path: conditions/c/c_single/semantic_audit.py
# Purpose: Validate the post-repair semantic audit (the step c_single adds; c_blind inherits it).
import json
from pathlib import Path

FIELDS = ("data_object", "observation_unit", "comparison", "metric_or_outcome",
          "unit_or_scale", "denominator_or_population", "method_or_estimator")
STATUSES = {"matched", "unsupported", "contradicted", "ambiguous"}


def validate_audit(workspace: Path, qid: str):
    audit = json.loads((workspace / "analysis/semantic_audit.json").read_text())
    if audit.get("question_id") != qid:
        raise ValueError("semantic audit question identity mismatch")
    rows = audit.get("fields", [])
    if len(rows) != len(FIELDS) or {r.get("field") for r in rows} != set(FIELDS):
        raise ValueError("semantic audit must cover all seven fields exactly once")
    for row in rows:
        if row.get("status") not in STATUSES or not str(row.get("evidence", "")).strip():
            raise ValueError("semantic audit needs valid status and evidence")
    if not str(audit.get("answer_contract_check", "")).strip():
        raise ValueError("semantic audit missing answer contract check")
    return audit
