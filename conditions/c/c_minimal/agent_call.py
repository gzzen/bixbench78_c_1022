# Path: conditions/c/c_minimal/agent_call.py
# Purpose: One isolated OpenCode agent call for C (replaces the source's `codex exec` invocations).
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from common.benchmark.a84_contract import MODEL as DEFAULT_MODEL, controlled_env, write_json
from common.integrity.attempt_container import isolated_attempt
from common.integrity.evaluator_access_policy import (
    POLICY_EXIT_CODE,
    answer_blind_env,
    generation_event_guard,
    policy_violation,
)
from common.integrity.opencode_capture import capture_opencode, opencode_command

# The source C repair used its own effort setting (C_REPAIR_REASONING_EFFORT); rescue_main sets
# both from the frozen parent's manifest unless explicitly overridden.
MODEL = DEFAULT_MODEL
REASONING_EFFORT = "medium"


@dataclass
class AgentCall:
    workspace: Path
    return_code: Optional[int]
    events: list[dict[str, Any]]
    stderr: str
    runtime_seconds: float
    policy_violation: Optional[dict[str, Any]] = field(default=None)


def save_capture(workspace: Path, events: list[dict[str, Any]], stderr: str) -> None:
    write_json(workspace / "event_timeline.json", events)
    (workspace / "events.jsonl").write_text(
        "".join(json.dumps(item["event"], ensure_ascii=False) + "\n" for item in events), encoding="utf-8"
    )
    (workspace / "stderr.log").write_text(stderr, encoding="utf-8")


def run_agent(prompt: str, schema: Path, workspace: Path, label: str, timeout: int) -> AgentCall:
    """Run exactly one answer-blind OpenCode session behind the per-attempt Docker boundary.

    The caller extracts the final JSON with ``write_result``.  There is no retry,
    including after a live policy interruption.
    """
    command = opencode_command(prompt, schema, MODEL)
    with isolated_attempt(command, answer_blind_env(controlled_env(workspace)), workspace,
                          schema=schema, reasoning_effort=REASONING_EFFORT) as (argv, env):
        return_code, events, stderr, runtime = capture_opencode(
            argv, env, timeout, event_guard=generation_event_guard(workspace),
            policy_exit_code=POLICY_EXIT_CODE, progress_label=label,
        )
    save_capture(workspace, events, stderr)
    return AgentCall(workspace, return_code, events, stderr, runtime, policy_violation(events))


def captured_usage(events: list[dict[str, Any]]) -> dict[str, float]:
    """Sum token usage from OpenCode step-finish parts (or Codex turn.completed events)."""
    totals: dict[str, float] = {}

    def add(prefix: str, values: Any) -> None:
        if not isinstance(values, dict):
            return
        for key, value in values.items():
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                totals[prefix + key] = totals.get(prefix + key, 0) + value
            elif isinstance(value, dict):
                add(f"{prefix}{key}_", value)

    for record in events:
        event = record.get("event", record) if isinstance(record, dict) else {}
        if not isinstance(event, dict):
            continue
        raw = event.get("opencode_event", event)
        if not isinstance(raw, dict):
            continue
        part = raw.get("part")
        if isinstance(part, dict) and (raw.get("type") == "step_finish" or part.get("type") == "step-finish"):
            add("", part.get("tokens"))
        elif raw.get("type") == "turn.completed":
            add("", raw.get("usage"))
    return totals
