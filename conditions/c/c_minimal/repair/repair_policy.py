# Path: conditions/c/c_minimal/repair/repair_policy.py
# Purpose: Enforce standalone C-v2 Yes-freeze, one-dimension repair, and source-provenance rules.
from __future__ import annotations

import copy
import hashlib
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from .diagnosis import validate_diagnosis


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unresolved_result(question_id: str, reason: str) -> dict[str, Any]:
    return {
        "question_id": question_id,
        "status": "unresolved",
        "candidates": [],
        "summary": reason,
    }


def _source_provenance(workspace: Path, record: Mapping[str, Any]) -> list[dict[str, str]]:
    execution = record.get("execution")
    if not isinstance(execution, Mapping):
        raise ValueError("repair record missing execution contract")
    reran = execution.get("reran_analysis")
    computation_required = execution.get("computation_required")
    source_files = execution.get("source_files")
    if not isinstance(reran, bool) or not isinstance(computation_required, bool):
        raise ValueError("repair execution flags must be booleans")
    if not isinstance(source_files, list) or any(not isinstance(x, str) for x in source_files):
        raise ValueError("repair source_files must be a string list")
    if computation_required and not source_files:
        raise ValueError("a computational repair requires persisted source")
    root = workspace.resolve()
    provenance: list[dict[str, str]] = []
    persisted_program = False
    for value in source_files:
        relative = Path(value)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"repair source path is not workspace-relative: {value}")
        declared_path = workspace / relative
        path = declared_path.resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"repair source is outside the capsule workspace: {value}") from exc
        if declared_path.is_symlink() or not path.is_file():
            raise ValueError(f"repair source is not a regular persisted file: {value}")
        relative_path = path.relative_to(workspace).as_posix()
        if relative_path.startswith("analysis/scripts/"):
            persisted_program = True
        provenance.append({"path": relative_path, "sha256": sha256_file(path)})
    if computation_required and not persisted_program:
        raise ValueError("a computational repair requires a persisted analysis/scripts program")
    return provenance


def finalize_repair(
    primary: Mapping[str, Any],
    proposed: Mapping[str, Any],
    feedback: Sequence[Mapping[str, str]],
    workspace: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Create the controller-canonical result and validated repair provenance.

    C is allowed a small *coupled* repair: some failures are caused by a
    linked scope/denominator/method decision, and forcing one dimension made
    C preserve a known-invalid analysis contract.  The cap and interpretation
    requirement keep this evidence-driven rather than turning it into answer
    enumeration.
    """
    if proposed.get("capsule_uuid") != primary.get("capsule_uuid") or proposed.get("short_id") != primary.get("short_id"):
        raise ValueError("repair capsule identity mismatch")
    primary_results = list(primary.get("results", []))
    proposed_results = list(proposed.get("results", []))
    expected = [item.get("question_id") for item in primary_results]
    if [item.get("question_id") for item in proposed_results] != expected:
        raise ValueError("repair result question coverage/order mismatch")
    verdicts = {item.get("question_id"): item.get("feedback") for item in feedback}
    if list(verdicts) != expected or any(value not in {"yes", "no"} for value in verdicts.values()):
        raise ValueError("feedback coverage/order mismatch")
    records = proposed.get("repair_records")
    if not isinstance(records, list):
        raise ValueError("repair_records must be a list")
    record_ids = [item.get("question_id") for item in records if isinstance(item, Mapping)]
    expected_no = [qid for qid in expected if verdicts[qid] == "no"]
    if record_ids != expected_no:
        raise ValueError("repair_records must cover exactly the No questions in order")
    by_record = {item["question_id"]: item for item in records}
    final_results: list[dict[str, Any]] = []
    provenance: list[dict[str, Any]] = []
    for old, new in zip(primary_results, proposed_results):
        qid = old["question_id"]
        if verdicts[qid] == "yes":
            final_results.append(copy.deepcopy(old))
            continue
        record = by_record[qid]
        dimension = validate_diagnosis(record)
        execution = record["execution"]
        interpretations = record.get("interpretations", [])
        changed_dimensions = record.get("changed_dimensions", [])
        if dimension is not None and not 2 <= len(interpretations) <= 3:
            raise ValueError(f"changed repair requires 2-3 semantic interpretations: {qid}")
        if dimension is None:
            # If B supplied no candidate at all (for example a capsule-level
            # service failure), C may reconstruct this one question from the
            # capsule evidence.  This is not a semantic change to an existing
            # answer, so changed_dimensions remains empty; it is still held to
            # the same one-shot execution/provenance requirements.
            missing_primary = not old.get("candidates")
            reconstruction = (
                missing_primary
                and new.get("status") == "resolved"
                and bool(new.get("candidates"))
                and execution.get("reran_analysis") is True
            )
            if reconstruction:
                source = _source_provenance(workspace, record)
            else:
                if new.get("status") != "unresolved" or new.get("candidates"):
                    raise ValueError(f"No question without a defensible change must be unresolved: {qid}")
                execution_sources = [p for p in execution.get("source_files", []) if p != "analysis/grounding.json"]
                if execution_sources and not execution.get("reran_analysis"):
                    raise ValueError(f"abstaining repair lists sources without rerunning analysis: {qid}")
                source = _source_provenance(workspace, record) if execution.get("reran_analysis") else []
        else:
            if execution.get("reran_analysis") is not True:
                raise ValueError(f"changed repair must rerun relevant analysis: {qid}")
            source = _source_provenance(workspace, record)
        final_results.append(copy.deepcopy(new))
        provenance.append({
            "question_id": qid,
            "changed_dimension": dimension,
            "changed_dimensions": copy.deepcopy(record.get("changed_dimensions", [])),
            "diagnosis": record["diagnosis"],
            "rationale": record["rationale"],
            "interpretations": copy.deepcopy(record.get("interpretations", [])),
            "reran_analysis": execution["reran_analysis"],
            "computation_required": execution["computation_required"],
            "source_files": source,
        })
    final = {
        "capsule_uuid": primary.get("capsule_uuid"),
        "short_id": primary.get("short_id"),
        "workflow_summary": str(proposed.get("workflow_summary", "C-v2 conservative repair")),
        "results": final_results,
    }
    return final, provenance


def failed_repair_result(
    primary: Mapping[str, Any], feedback: Sequence[Mapping[str, str]], reason: str
) -> dict[str, Any]:
    """Fail closed without destroying the imported B answer.

    A repair is an additive opportunity, not a replacement population.  The
    previous implementation converted every No result to ``unresolved`` when
    the capsule-level repair failed validation.  That made a malformed repair
    for one question erase all of B's other answers.  C-v3 keeps the frozen B
    result for every question when no validated replacement is available.
    """
    results = [copy.deepcopy(item) for item in primary.get("results", [])]
    return {
        "capsule_uuid": primary.get("capsule_uuid"),
        "short_id": primary.get("short_id"),
        "workflow_summary": (
            "C-v3 repair failed closed; imported B results preserved exactly. "
            f"Reason: {reason}"
        ),
        "results": results,
    }


INLINE_TASK_CODE = re.compile(
    r"(?:\bpython(?:3)?\s+-c\b|\bR(?:script)?\s+-e\b|<<\s*['\"]?[A-Za-z_][A-Za-z0-9_]*|\bnode\s+-e\b)"
)


def audit_repair_execution(
    events: Sequence[Mapping[str, Any]], provenance: Sequence[Mapping[str, Any]],
    *, allow_persisted_inline: bool = False,
) -> None:
    """Audit repair execution and require declared sources in execution evidence.

    C-v3 may use short inline inspection commands, but only when the repair also
    declares and executes a persisted ``analysis/scripts`` program.  The final
    answer-producing computation therefore cannot exist only inline.
    """
    commands: list[str] = []
    for record in events:
        event = record.get("event", {}) if isinstance(record, Mapping) else {}
        item = event.get("item", {}) if isinstance(event, Mapping) else {}
        if event.get("type") == "item.completed" and item.get("type") == "command_execution":
            commands.append(str(item.get("command", "")))
    inline = [command for command in commands if INLINE_TASK_CODE.search(command)]
    persisted_sources = [
        str(source.get("path", ""))
        for item in provenance
        for source in item.get("source_files", [])
        if str(source.get("path", "")).startswith("analysis/scripts/")
    ]
    # An abstaining repair may perform read-only inline inspection and leave
    # no provenance at all.  That is not an answer-producing computation.  Any
    # resolved/changed repair still requires a persisted source and therefore
    # remains subject to the stricter branch below.
    read_only_abstention = all(
        item.get("changed_dimension") is None
        and item.get("reran_analysis") is False
        and item.get("computation_required") is False
        and not item.get("source_files")
        for item in provenance
    )
    if inline and not (read_only_abstention or (allow_persisted_inline and persisted_sources)):
        raise ValueError("inline task-specific program execution is forbidden in C repair")
    joined = "\n".join(commands)
    for item in provenance:
        for source in item.get("source_files", []):
            path = str(source["path"])
            if path.startswith("analysis/scripts/") and path not in joined and Path(path).name not in joined:
                raise ValueError(f"persisted repair source lacks execution evidence: {path}")
