# Path: conditions/c/c_minimal/test_support.py
# Purpose: Offline fixtures for C tests at every level: fake frozen B packets and fake OpenCode agent calls.
from __future__ import annotations

import contextlib
import json
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

from conditions.c.c_minimal import agent_call, pipeline

ROW = {"question_id": "bix-1-q2", "short_id": "bix-1", "capsule_uuid": "cap-1",
       "question": "What is the median expression across all samples?"}
FEEDBACK = {"question_id": ROW["question_id"], "feedback": "no"}
SCRIPT = "analysis/scripts/repair.py"
FIELDS = ("data_object", "observation_unit", "comparison", "metric_or_outcome",
          "unit_or_scale", "denominator_or_population", "method_or_estimator")


def result(qid: str, answer: str) -> dict:
    return {"question_id": qid, "status": "resolved",
            "candidates": [{"answer": answer, "method": "method", "evidence": "evidence"}], "summary": "summary"}


def make_record(root: Path) -> dict:
    """A frozen B packet as produced by c_minimal.parent.make_packet_records."""
    packet = root / "frozen_parent_packets" / ROW["question_id"]
    (packet / "analysis/scripts").mkdir(parents=True)
    (packet / "primary_canonical.json").write_text(json.dumps({
        "capsule_uuid": "cap-1", "short_id": "bix-1", "workflow_summary": "B",
        "results": [result("bix-1-q1", "kept"), result("bix-1-q2", "old")]}))
    (packet / "analysis/grounding.json").write_text(json.dumps({"capsule_uuid": "cap-1", "questions": []}))
    (packet / "analysis/scripts/b.py").write_text("print('b')\n")
    return {"short_id": "bix-1", "capsule_uuid": "cap-1", "question_ids": ["bix-1-q1", "bix-1-q2"],
            "workspace": str(packet), "accepted": True, "event_metrics": {}}


def text(payload: Any) -> dict:
    return {"event": {"type": "text", "part": {"type": "text", "text": json.dumps(payload), "messageID": "m1"}},
            "elapsed_seconds": 2.0}


def command(cmd: str) -> dict:
    return {"event": {"type": "item.completed", "item": {"type": "command_execution", "command": cmd}},
            "elapsed_seconds": 1.0}


def proposal(*, dimensions=("statistical_method",), answer="new", resolved=True) -> dict:
    return {
        "capsule_uuid": "cap-1", "short_id": "bix-1", "workflow_summary": "repair",
        "results": [result("bix-1-q2", answer) if resolved else
                    {"question_id": "bix-1-q2", "status": "unresolved", "candidates": [], "summary": "abstain"}],
        "repair_records": [{
            "question_id": "bix-1-q2", "primary_feedback": "no", "diagnosis": "estimator mismatch",
            "changed_dimensions": list(dimensions), "rationale": "question asks for the median",
            "interpretations": [{"interpretation": "mean", "evidence": "B"},
                                {"interpretation": "median", "evidence": "question wording"}],
            "execution": {"reran_analysis": bool(dimensions), "computation_required": bool(dimensions),
                          "source_files": [SCRIPT] if dimensions else []},
        }],
    }


def contract(**overrides) -> dict:
    return {"question_id": "bix-1-q2", "fields": dict.fromkeys(FIELDS, "specified"),
            "explicit_constraints": ["median expression"], "ambiguities": [], **overrides}


def semantic_audit() -> dict:
    return {"question_id": "bix-1-q2", "fields": [{"field": f, "status": "matched", "evidence": "e"} for f in FIELDS],
            "answer_contract_check": "answers the median"}


class FakeAgent:
    """Stands in for agent_call.run_agent; each scripted step may write workspace files."""

    def __init__(self, steps):
        self.steps = list(steps)
        self.calls: list[dict] = []

    def __call__(self, prompt, schema, workspace, label, timeout):
        step = self.steps.pop(0)
        self.calls.append({"prompt": prompt, "schema": Path(schema).name, "workspace": workspace, "label": label})
        for relative, content in step.get("files", {}).items():
            path = workspace / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content if isinstance(content, str) else json.dumps(content))
        return agent_call.AgentCall(workspace, step.get("code", 0), step.get("events", []), "", 1.5,
                                    step.get("violation"))


def repair_step(payload=None, *, audit=False, grounding=True, events=None, **extra) -> dict:
    files = {SCRIPT: "print('median')\n"}
    if grounding:
        files["analysis/grounding.json"] = {"capsule_uuid": "cap-1", "questions": [{"question_id": "bix-1-q2"}]}
    if audit:
        files["analysis/semantic_audit.json"] = semantic_audit()
    default_events = [command(f"python {SCRIPT}")] + ([text(payload)] if payload is not None else [])
    return {"files": files, "events": default_events if events is None else events, **extra}


def contract_step(payload, **extra) -> dict:
    return {"events": [text(payload)], **extra}


def fake_prepare(arm, run_root, rows):
    workspace = run_root / arm / f"{rows[0]['short_id']}__{rows[0]['capsule_uuid']}"
    workspace.mkdir(parents=True)
    return workspace, None


@contextlib.contextmanager
def offline(agent: FakeAgent, *extra_modules):
    """Patch the Docker/OpenCode call, workspace materialization and B grounding schema check.

    ``extra_modules`` are higher-level modules that import ``prepare_workspace`` themselves.
    """
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch.object(agent_call, "run_agent", agent))
        stack.enter_context(patch.object(pipeline, "prepare_workspace", fake_prepare))
        stack.enter_context(patch.object(pipeline.b_runner, "grounding_record", lambda ws, rows: {"checked": "yes"}))
        for module in extra_modules:
            stack.enter_context(patch.object(module, "prepare_workspace", fake_prepare))
        yield


def run_repair(condition, steps, *extra_modules) -> tuple[dict, FakeAgent, dict]:
    """Run one question through ``condition`` offline; returns (repair record, agent, saved workspace files)."""
    agent = FakeAgent(steps)
    with tempfile.TemporaryDirectory() as value:
        root = Path(value)
        with offline(agent, *extra_modules):
            repair = condition.run_question(make_record(root), ROW, FEEDBACK, root, 60)
        workspace = Path(repair["workspace"])
        files = {path.relative_to(workspace).as_posix(): path.read_text()
                 for path in workspace.rglob("*") if path.is_file()}
        if repair.get("blind_workspace"):
            blind = Path(repair["blind_workspace"])
            files.update({"<blind>/" + p.relative_to(blind).as_posix(): p.read_text() for p in blind.rglob("*") if p.is_file()})
    return repair, agent, files
