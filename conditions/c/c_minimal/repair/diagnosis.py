# Path: conditions/c/c_minimal/repair/diagnosis.py
# Purpose: Validate and normalize C-only single-dimension repair diagnoses.
from __future__ import annotations

from typing import Any, Mapping

REPAIR_DIMENSIONS = frozenset({
    "scope_filter",
    "entity_mapping",
    "aggregation_denominator",
    "statistical_method",
    "unit_precision_type",
    "external_resource_version",
})


def validate_diagnosis(record: Mapping[str, Any]) -> str | None:
    """Return the one changed dimension, or None for a defensible abstention."""
    if record.get("primary_feedback") != "no":
        raise ValueError("repair records are permitted only for No feedback")
    diagnosis = record.get("diagnosis")
    rationale = record.get("rationale")
    if not isinstance(diagnosis, str) or not diagnosis.strip():
        raise ValueError("repair diagnosis must be nonempty")
    if not isinstance(rationale, str) or not rationale.strip():
        raise ValueError("repair rationale must be nonempty")
    dimensions = record.get("changed_dimensions")
    if not isinstance(dimensions, list) or not all(isinstance(item, str) for item in dimensions):
        raise ValueError("changed_dimensions must be a list of dimension names")
    if len(dimensions) > 3 or len(set(dimensions)) != len(dimensions):
        raise ValueError("evidence-backed repair may change at most three distinct dimensions")
    if not dimensions:
        return None
    dimension = dimensions[0]
    for value in dimensions:
        if value not in REPAIR_DIMENSIONS:
            raise ValueError(f"unknown repair dimension: {value!r}")
    return str(dimension)
