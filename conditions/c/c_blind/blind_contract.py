# Path: conditions/c/c_blind/blind_contract.py
# Purpose: c_blind phase 1: a parent-blind semantic contract derived only from the question and capsule data.
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from common.benchmark.a84_contract import sha256_file, write_json
from common.integrity.isolation_audit import audit_events_v121
from common.integrity.opencode_capture import generation_failure, write_result
from conditions.c.c_minimal import agent_call, pipeline
from conditions.c.c_minimal.pipeline import PreRepairOutcome
from conditions.c.c_single.semantic_audit import FIELDS
from conditions.c.c_blind.prompts import BLIND_CONTRACT_PROMPT

CONTRACT_SCHEMA = Path(__file__).resolve().with_name("semantic_contract.schema.json")


def validate_contract(payload, row):
    if payload.get("question_id") != row["question_id"]:
        raise ValueError("blind contract question identity mismatch")
    fields = payload.get("fields", {})
    if set(fields) != set(FIELDS) or any(not isinstance(fields[k], str) or not fields[k].strip() for k in FIELDS):
        raise ValueError("blind contract needs seven nonempty semantic fields")
    for quote in payload.get("explicit_constraints", []):
        if not isinstance(quote, str) or not quote.strip() or quote not in row["question"]:
            raise ValueError("explicit constraint is not a verbatim question span")
    return payload


def run_blind_contract(row: Mapping[str, Any], run_root: Path, timeout: int) -> PreRepairOutcome:
    """Truly blind first phase: no parent artifacts exist in this workspace."""
    qid = row["question_id"]
    blind_workspace = pipeline.question_workspace(run_root / "blind_contracts", row)
    write_json(blind_workspace / "question_only.json", dict(row))
    call = agent_call.run_agent(BLIND_CONTRACT_PROMPT, CONTRACT_SCHEMA, blind_workspace,
                                f"C/c_blind/{qid}/contract", timeout)
    try:
        if call.policy_violation is not None:
            raise ValueError("generation safety policy violation: " + str(call.policy_violation.get("reason")))
        if call.return_code != 0:
            raise ValueError(generation_failure(call.return_code, call.events))
        audit_events_v121(call.events, blind_workspace)
        blind_contract = validate_contract(
            write_result(call.events, CONTRACT_SCHEMA, blind_workspace / "blind_contract.json"), row)
    except Exception as exc:
        return PreRepairOutcome(None, blind_workspace, call.runtime_seconds, call.events,
                                f"blind contract failure: {exc}", agent_calls=1)
    write_json(blind_workspace / "phase_freeze.json", {
        "contract_sha256": sha256_file(blind_workspace / "blind_contract.json"),
        "parent_visible": False, "runtime_seconds": call.runtime_seconds})
    return PreRepairOutcome(blind_contract, blind_workspace, call.runtime_seconds, call.events, None, agent_calls=1)
