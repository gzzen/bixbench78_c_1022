# Path: conditions/c/c_minimal/pipeline.py
# Purpose: c_minimal (C-v6) question-local repair over a frozen B parent; base class of c_single and c_blind.
from __future__ import annotations

import copy
import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from common.benchmark.a84_contract import (environment_manifest, load_rows, materialize_common_native_inputs,
                                          public_question, sha256_file, write_json)
from common.integrity.capsule_workspace import validate_native_result
from common.integrity.codex_capture import command_metrics
from common.integrity.isolation_audit import audit_events_v121
from common.integrity.opencode_capture import generation_failure, write_result
from conditions.b import runner as b_runner
from conditions.c.c_minimal import agent_call
from conditions.c.c_minimal.prompts import MINIMAL_REPAIR_PROMPT
from conditions.c.c_minimal.repair.repair_policy import audit_repair_execution, finalize_repair

ROOT = Path(__file__).resolve().parents[3]
REPAIR_SCHEMA = ROOT / "conditions/c/c_minimal/repair_result.schema.json"


def question_workspace(stage_root: Path, row: Mapping[str, Any]) -> Path:
    """One flat workspace per question, named like B's: <stage>/<question_id>__<capsule_uuid>."""
    workspace = stage_root / f"{row['question_id']}__{row['capsule_uuid']}"
    if workspace.exists():
        raise FileExistsError(f"refusing existing workspace: {workspace}")
    materialize_common_native_inputs(workspace, [dict(row)], environment_manifest()["values"])
    return workspace


def rows_by_capsule() -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in load_rows():
        public = public_question(row)
        grouped.setdefault(public["capsule_uuid"], []).append(public)
    return grouped


def freeze_artifacts(
    records: Sequence[Mapping[str, Any]], names: Sequence[str], scripts: bool = False
) -> list[dict[str, str]]:
    artifacts: list[dict[str, str]] = []
    for record in records:
        workspace = Path(record["workspace"])
        paths = [workspace / name for name in names]
        if scripts and (workspace / "analysis/scripts").is_dir():
            paths.extend(path for path in (workspace / "analysis/scripts").rglob("*") if path.is_file())
        for path in paths:
            if path.is_file():
                artifacts.append({"path": str(path.relative_to(ROOT)), "sha256": sha256_file(path)})
    return artifacts


def primary_payload(record: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads((Path(record["workspace"]) / "primary_canonical.json").read_text(encoding="utf-8"))


def localize_repair_paths(value: Any) -> Any:
    """Normalize imported evidence paths before presenting them to C repair.

    B candidates sometimes quote their original absolute script path.  Passing
    that string through makes a question-local repair attempt to escape its
    workspace.  This helper changes only the repair input copy; frozen B
    primary/final artifacts remain byte-for-byte unchanged.
    """
    if isinstance(value, str):
        value = re.sub(r"(?:/[^\s'\"]+/)+analysis/scripts/", "analysis/scripts/", value)
        value = re.sub(r"(?:/[^\s'\"]+/)+analysis/grounding\.json", "analysis/grounding.json", value)
        return value
    if isinstance(value, list):
        return [localize_repair_paths(item) for item in value]
    if isinstance(value, dict):
        return {key: localize_repair_paths(item) for key, item in value.items()}
    return value


def preserve_primary_on_unresolved(
    primary: Mapping[str, Any], final: Mapping[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """Keep an imported B candidate when a C repair abstains or is incomplete.

    C is additive: a repair may replace a B result only with a resolved,
    controller-valid result.  An unresolved repair therefore falls back to the
    corresponding frozen primary question instead of reducing coverage.
    """
    primary_by_id = {item["question_id"]: item for item in primary.get("results", [])}
    merged = copy.deepcopy(dict(final))
    fallback_ids: list[str] = []
    output: list[dict[str, Any]] = []
    for item in final.get("results", []):
        old = primary_by_id.get(item.get("question_id"))
        if (
            old is not None
            and old.get("candidates")
            and (item.get("status") != "resolved" or not item.get("candidates"))
        ):
            output.append(copy.deepcopy(old))
            fallback_ids.append(item["question_id"])
        else:
            output.append(copy.deepcopy(item))
    merged["results"] = output
    return merged, fallback_ids


def normalize_question_repair_proposal(
    proposed: dict[str, Any], qid: str, *, missing_primary: bool = False,
) -> dict[str, Any]:
    """Turn an unsupported no-op proposal into an explicit safe abstention."""
    records = proposed.get("repair_records")
    results = proposed.get("results")
    if not isinstance(records, list) or not isinstance(results, list) or len(records) != 1 or len(results) != 1:
        return proposed
    record = records[0]
    if record.get("question_id") != qid or record.get("changed_dimensions"):
        return proposed
    result = results[0]
    if result.get("status") == "resolved" and result.get("candidates") and not missing_primary:
        normalized = copy.deepcopy(proposed)
        normalized["results"] = [{
            "question_id": qid,
            "status": "unresolved",
            "candidates": [],
            "summary": "No independently defensible one-dimension repair was identified.",
        }]
        return normalized
    return proposed


def validate_question_repair_grounding(
    workspace: Path, primary_workspace: Path, rows: list[dict[str, Any]],
    feedback: Sequence[Mapping[str, str]],
) -> dict[str, str]:
    """Accept either a one-question or full-capsule grounding artifact.

    Question-local repair prompts naturally produce a compact one-question
    grounding, while some solvers copy the frozen capsule grounding and edit
    only the target record.  Both are safe when the target record is valid and
    all untouched records remain byte-equivalent to the primary grounding.
    """
    path = workspace / "analysis/grounding.json"
    if not path.is_file():
        raise ValueError("missing analysis/grounding.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    # A single-question solver sometimes emits the grounding record directly
    # rather than wrapping it in the B capsule object.  Canonicalize that
    # harmless shape drift before applying semantic checks.
    if "questions" not in payload and isinstance(payload.get("question_id"), str):
        payload = {"capsule_uuid": rows[0]["capsule_uuid"], "questions": [payload]}
        write_json(path, payload)
    expected = [row["question_id"] for row in rows]
    actual = [item.get("question_id") for item in payload.get("questions", [])]
    if actual == expected:
        return b_runner.grounding_record(workspace, rows)
    primary_path = primary_workspace / "analysis/grounding.json"
    if not primary_path.is_file():
        raise ValueError("question-local grounding has unexpected coverage")
    primary = json.loads(primary_path.read_text(encoding="utf-8"))
    primary_ids = [item.get("question_id") for item in primary.get("questions", [])]
    if actual != primary_ids:
        raise ValueError("question-local grounding has unexpected coverage")
    # Validate the full artifact using the original capsule rows, then require
    # every non-target record to remain exactly unchanged.
    full_rows = rows_by_capsule()[rows[0]["capsule_uuid"]]
    artifact = b_runner.grounding_record(workspace, full_rows)
    before = {item["question_id"]: item for item in primary["questions"]}
    after = {item["question_id"]: item for item in payload["questions"]}
    target = {item["question_id"] for item in rows}
    for qid in primary_ids:
        if qid not in target and after[qid] != before[qid]:
            raise ValueError(f"question-local repair changed non-target grounding: {qid}")
    return artifact


def _minimal_primary_provenance(record: Mapping[str, Any], primary: Mapping[str, Any]) -> dict[str, Any]:
    metrics = record.get("event_metrics", {})
    return {
        "capsule_uuid": primary["capsule_uuid"],
        "primary_controller_accepted": bool(record.get("accepted")),
        "implementation": record.get("implementation", "conditions.b.runner.run_capsule"),
        "question_ids": [item["question_id"] for item in primary["results"]],
        # Controller-produced diagnostics are safe local evidence for a
        # question repair.  They contain no private answer or evaluator text;
        # they only identify execution/grounding inconsistencies already
        # observed in the imported B run.
        "controller_diagnostics": {
            "question_local_failures": record.get("b_question_local_failures", {}),
            "grounding_failures": record.get("b_grounding_failures", {}),
            "consistency_failures": record.get("b_consistency_failures", {}),
        },
        "execution_summary": {
            "command_count": metrics.get("command_count", 0),
            "scientific_computation_command_count": metrics.get("scientific_computation_command_count", 0),
            "task_inspection_and_planning_command_count": metrics.get("task_inspection_and_planning_command_count", 0),
        },
    }


def copy_parent_evidence(primary_workspace: Path, workspace: Path) -> list[dict[str, Any]] | None:
    """Give a question-local repair the frozen B computation as an auditable starting point.

    The files are copied, never executed outside this workspace, and the repair
    still has to declare/rerun any source it uses.
    """
    source_scripts = primary_workspace / "analysis/scripts"
    target_scripts = workspace / "analysis/scripts"
    if source_scripts.is_dir():
        target_scripts.mkdir(parents=True, exist_ok=True)
        for source in source_scripts.rglob("*"):
            if source.is_file() and source.suffix != ".pyc":
                destination = target_scripts / source.relative_to(source_scripts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
    imported = primary_workspace / "imported_artifacts.json"
    if not imported.is_file():
        return None
    inventory = json.loads(imported.read_text())
    for artifact in inventory:
        source = primary_workspace / artifact["path"]
        destination = workspace / artifact["path"]
        if source.is_file() and not source.is_symlink():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
    return inventory


@dataclass
class PreRepairOutcome:
    """Result of an optional phase that runs before the parent-visible repair call."""

    payload: Optional[Mapping[str, Any]]
    workspace: Optional[Path]
    runtime_seconds: float
    events: list = field(default_factory=list)
    failure: Optional[str] = None      # set -> the repair is skipped and frozen B is kept
    agent_calls: int = 0


class MinimalRepair:
    """c_minimal: frozen-B packet -> one repair call -> validation -> fallback to B.

    Higher levels subclass this and add steps through two hooks:
    ``pre_repair`` (c_blind's parent-blind contract) and ``post_validate``
    (c_single's semantic audit).  Each level also supplies its own prompt.
    """

    name = "c_minimal"
    revision = "C-v6 minimal evidence-backed repair"
    policy = "minimal"
    repair_prompt = MINIMAL_REPAIR_PROMPT
    max_calls_per_question = 1
    pre_repair_output: Optional[str] = None
    package_dir = Path(__file__).resolve().parent

    @classmethod
    def lineage(cls) -> list[tuple[str, Path]]:
        """(name, directory) for this level and every ancestor level, most specific first."""
        return [(klass.__dict__["name"], klass.__dict__["package_dir"])
                for klass in cls.__mro__ if "name" in klass.__dict__ and "package_dir" in klass.__dict__]

    def pre_repair(self, row: Mapping[str, Any], run_root: Path, timeout: int) -> Optional[PreRepairOutcome]:
        return None

    def post_validate(self, workspace: Path, qid: str) -> dict[str, Any]:
        """Extra acceptance checks after the shared validation; returned fields join the record."""
        return {}

    def run_question(
        self, record: Mapping[str, Any], row: Mapping[str, Any], feedback: Mapping[str, str],
        run_root: Path, timeout: int,
    ) -> dict[str, Any]:
        """Repair one No question without coupling it to sibling questions."""
        primary = primary_payload(record)
        qid = str(row["question_id"])
        primary_by_id = {item["question_id"]: item for item in primary["results"]}
        one_primary = {
            "capsule_uuid": primary["capsule_uuid"], "short_id": primary["short_id"],
            "workflow_summary": primary.get("workflow_summary", "imported B primary"),
            "results": [localize_repair_paths(copy.deepcopy(primary_by_id[qid]))],
        }
        workspace = question_workspace(run_root / "repair_questions", row)
        write_json(workspace / "question_only.json", dict(row))
        pre = self.pre_repair(row, run_root, timeout)
        if pre is not None and pre.failure:
            failed = {"question_id": qid, "workspace": str(workspace),
                      "blind_workspace": str(pre.workspace) if pre.workspace else None,
                      "capsule_uuid": row["capsule_uuid"], "short_id": row["short_id"],
                      "level": self.name, "policy": self.policy,
                      "accepted": False, "total_agent_calls": pre.agent_calls, "retry_attempted": False,
                      "controller_status": "failed", "failure_reason": pre.failure,
                      "runtime_seconds": pre.runtime_seconds, "final_result": one_primary,
                      "usage": agent_call.captured_usage(pre.events)}
            write_json(workspace / "final_result.json", one_primary)
            write_json(workspace / "run_manifest.json", {k: v for k, v in failed.items() if k != "final_result"})
            return failed
        if pre is not None:
            write_json(workspace / self.pre_repair_output, pre.payload)
        return self._repair_with_parent(record, row, feedback, primary_by_id, one_primary, workspace, timeout, pre)

    def _repair_with_parent(self, record, row, feedback, primary_by_id, one_primary, workspace, timeout, pre):
        qid = row["question_id"]
        primary_workspace = Path(record["workspace"])
        write_json(workspace / "primary_result.json", one_primary)
        write_json(workspace / "primary_provenance.json", _minimal_primary_provenance(record, one_primary))
        write_json(workspace / "feedback.json", {"items": [dict(feedback)]})
        packet = {
            "packet_version": "c-frozen-parent-v1",
            "question": dict(row),
            "b3_final_result": copy.deepcopy(primary_by_id[qid]),
            "b3_capsule_uuid": one_primary["capsule_uuid"],
            "b3_short_id": one_primary["short_id"],
            "evaluator_verdict": "no",
            "controller_diagnostics": _minimal_primary_provenance(record, one_primary)["controller_diagnostics"],
            "allowed_artifacts": ["primary_result.json", "primary_provenance.json", "primary_grounding.json"],
        }
        source_grounding = primary_workspace / "analysis/grounding.json"
        if source_grounding.is_file():
            source_payload = json.loads(source_grounding.read_text())
            write_json(workspace / "primary_grounding.json", {
                "capsule_uuid": row["capsule_uuid"],
                "questions": [g for g in source_payload.get("questions", []) if g.get("question_id") == qid],
            })
        inventory = copy_parent_evidence(primary_workspace, workspace)
        if inventory is not None:
            packet["imported_artifacts"] = inventory
        write_json(workspace / "repair_packet.json", packet)

        call = agent_call.run_agent(self.repair_prompt, REPAIR_SCHEMA, workspace, f"C/{self.name}/{qid}/repair", timeout)
        repair: dict[str, Any] = {
            "question_id": qid, "capsule_uuid": row["capsule_uuid"], "short_id": row["short_id"],
            "level": self.name, "policy": self.policy,
            "workspace": str(workspace), "attempt_count": 1, "retry_attempted": False,
            "total_agent_calls": (pre.agent_calls if pre else 0) + 1, "return_code": call.return_code,
            "runtime_seconds": call.runtime_seconds + (pre.runtime_seconds if pre else 0.0),
            "blind_workspace": str(pre.workspace) if pre and pre.workspace else None,
            "usage": agent_call.captured_usage((pre.events if pre else []) + call.events),
            "accepted": False, "event_metrics": command_metrics(call.events),
        }
        if call.policy_violation is not None:
            # One call per question: a live policy interruption is a failed repair, never retried.
            repair.update({
                "controller_status": "interrupted_policy_violation",
                "policy_violation": call.policy_violation,
                "failure_reason": "generation safety policy violation: " + str(call.policy_violation.get("reason")),
                "final_result": one_primary,
            })
        else:
            try:
                if call.return_code != 0:
                    raise RuntimeError(generation_failure(call.return_code, call.events))
                evidence = audit_events_v121(call.events, workspace)
                proposed = write_result(call.events, REPAIR_SCHEMA, workspace / "repair_result.json")
                # The workspace and the single question are controller-owned identity;
                # normalize harmless model drift before applying the ordinary policy.
                if [item.get("question_id") for item in proposed.get("results", [])] == [qid]:
                    proposed["capsule_uuid"] = one_primary["capsule_uuid"]
                    proposed["short_id"] = one_primary["short_id"]
                proposed = normalize_question_repair_proposal(proposed, qid,
                    missing_primary=not one_primary["results"][0].get("candidates"))
                final, provenance = finalize_repair(one_primary, proposed, [dict(feedback)], workspace)
                final, fallback_ids = preserve_primary_on_unresolved(one_primary, final)
                validate_native_result(final, [dict(row)])
                grounding = validate_question_repair_grounding(workspace, primary_workspace, [dict(row)], [dict(feedback)])
                audit_repair_execution(call.events, provenance, allow_persisted_inline=True)
                extra = self.post_validate(workspace, qid)
                write_json(workspace / "analysis/path_audit.json", {"policy": "semantic resolved-path isolation", "evidence": evidence})
                write_json(workspace / "analysis/repair_provenance.json", {"repairs": provenance})
                repair.update({
                    "accepted": True, "controller_status": "passed", "repair_provenance": provenance,
                    "grounding": grounding, "path_audit_evidence_count": len(evidence),
                    "fallback_to_primary": bool(fallback_ids), "fallback_to_primary_question_ids": fallback_ids,
                    "final_result": final, **extra,
                })
            except Exception as exc:
                repair.update({"controller_status": "failed", "failure_reason": f"{type(exc).__name__}: {exc}"})
                repair["final_result"] = one_primary
        write_json(workspace / "final_result.json", repair["final_result"])
        write_json(workspace / "run_manifest.json", {key: value for key, value in repair.items() if key != "final_result"})
        return repair
