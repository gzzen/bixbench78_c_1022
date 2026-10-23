# Path: conditions/c/c_minimal/rescue_main.py
# Purpose: CLI, orchestration, protocol snapshot, freeze and report for every C level (c_minimal and subclasses).
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import re
import shutil
import time
from pathlib import Path

from common.benchmark.a84_contract import write_json
from common.integrity.opencode_capture import agent_manifest
from common.integrity.progress import progress_log
from conditions.c.c_minimal import agent_call
from conditions.c.c_minimal.parent import digest, load_parent, make_packet_records
from conditions.c.c_minimal.pipeline import MinimalRepair, freeze_artifacts

ROOT = Path(__file__).resolve().parents[3]
CONTROLLER_SOURCES = [ROOT / "common/integrity" / name for name in ("opencode_capture.py", "attempt_container.py")]


def parent_tag(generation: Path) -> str:
    """`analysis/<tag>_generation.json` -> `<tag>` (used for default output names)."""
    name = generation.name
    return re.sub(r"_generation\.json$", "", name) if name.endswith("_generation.json") else generation.stem


def protocol_sources(condition: MinimalRepair) -> list[Path]:
    """Every file whose bytes define this level: its directory and all ancestor level directories."""
    files: list[Path] = []
    for _, directory in condition.lineage():
        files += [path for path in sorted(directory.rglob("*")) if path.is_file() and path.suffix in {".py", ".json"}
                  and not path.name.startswith("test_") and "__pycache__" not in path.parts]
    return files + CONTROLLER_SOURCES


def finished_repair(run_root: Path, qid: str) -> dict | None:
    """The saved record of a question an earlier, interrupted run finished; None if it did not finish.

    ``run_manifest.json`` is written last, after ``final_result.json``, so a readable manifest
    marks a finished question.
    """
    for manifest in sorted((run_root / "repair_questions" / qid).glob("*/run_manifest.json")):
        try:
            record = json.loads(manifest.read_text(encoding="utf-8"))
            record["final_result"] = json.loads((manifest.parent / "final_result.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return record
    return None


def main(condition: MinimalRepair) -> None:
    parser = argparse.ArgumentParser(description=f"{condition.revision}: question-local rescue over a frozen B parent")
    parser.add_argument("--parent-generation", type=Path, required=True,
                        help="frozen B generation JSON (freeze.status=frozen_before_private_scoring)")
    parser.add_argument("--parent-scoring", type=Path, required=True,
                        help="post-freeze private scoring of that B generation (status=completed_posthoc_after_freeze)")
    parser.add_argument("--parent-registry", type=Path,
                        help="locked/rescue registry shared by all levels; default analysis/<parent-tag>_c_parent.json")
    parser.add_argument("--model", help="default: the frozen B parent's model")
    parser.add_argument("--repair-reasoning-effort", help="default: the frozen B parent's reasoning effort")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--resume", action="store_true",
                        help="continue an interrupted run in --run-root: keep finished questions, redo unfinished ones")
    parser.add_argument("--allow-no-locked", action="store_true",
                        help="execute even when the B scoring locks no question (normally a broken B export)")
    parser.add_argument("--limit", type=int, help="answer-blind pilot: first N B-No IDs in frozen order")
    parser.add_argument("--retry-failed-from", type=Path, help="new diagnostic revision, only prior controller failures; never reuse C answers")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=3600, help="seconds per agent call")
    parser.add_argument("--run-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    generation_path = args.parent_generation.resolve()
    scoring_path = args.parent_scoring.resolve()
    tag = parent_tag(generation_path)
    registry_path = (args.parent_registry or ROOT / f"analysis/{tag}_c_parent.json").resolve()
    run_root = (args.run_root or ROOT / f"runs/{tag}_{condition.name}").resolve()
    output = (args.output or ROOT / f"analysis/{tag}_{condition.name}_generation.json").resolve()
    report = (args.report or ROOT / f"reports/{tag}_{condition.name.upper()}_GENERATION.md").resolve()

    generation, scoring, parent = load_parent(generation_path, scoring_path, registry_path)
    manifest = generation.get("manifest", {})
    agent_call.MODEL = args.model or manifest.get("model") or agent_call.MODEL
    agent_call.REASONING_EFFORT = args.repair_reasoning_effort or manifest.get("reasoning_effort") or agent_call.REASONING_EFFORT
    agent = agent_manifest(agent_call.MODEL, agent_call.REASONING_EFFORT)  # validates model/effort before any call
    if not 1 <= args.workers <= 19:
        raise SystemExit("workers must be between 1 and 19")
    if args.execute and not args.resume and run_root.exists() and any(run_root.iterdir()):
        raise SystemExit("refusing nonempty C rescue run root (pass --resume to continue it)")
    if args.execute and output.exists():
        raise SystemExit("refusing to overwrite an existing C generation output")
    selected = None
    if args.retry_failed_from:
        previous = json.loads(args.retry_failed_from.read_text())
        if previous["parent"]["parent_generation_sha256"] != parent["parent_generation_sha256"]:
            raise RuntimeError("diagnostic retry parent mismatch")
        selected = {r["question_id"] for r in previous["rescue"] if not r.get("accepted")}
    if args.limit is not None and args.limit < 1:
        raise ValueError("pilot limit must be positive")
    b_answered = sum(bool(v.get("present", True)) for v in scoring["verdicts"])
    if args.execute and not parent["locked_yes_question_ids"] and not args.allow_no_locked:
        raise SystemExit(f"B scoring locks no question ({b_answered}/{len(scoring['verdicts'])} answered); "
                         "check the B export and scoring, or pass --allow-no-locked")
    lineage = [name for name, _ in condition.lineage()]
    if not args.execute:
        eligible = [qid for qid in parent["rescue_question_ids"] if selected is None or qid in selected]
        if args.limit is not None:
            eligible = eligible[:args.limit]
        print(json.dumps({
            "status": "frozen_parent_preflight_passed",
            "level": condition.name, "lineage": lineage, "revision": condition.revision,
            "b3_rerun": False,
            "b3_question_count": len(scoring["verdicts"]),
            "b_answered": b_answered,
            "locked_b3_yes": len(parent["locked_yes_question_ids"]),
            "c_rescue_targets": len(eligible),
            "max_agent_calls": len(eligible) * condition.max_calls_per_question,
            "finished_in_run_root": sum(finished_repair(run_root, qid) is not None for qid in eligible),
            "model": agent_call.MODEL, "reasoning_effort": agent_call.REASONING_EFFORT,
            "workers": args.workers,
            "run_root": str(run_root), "output": str(output),
        }, indent=2))
        return

    output.parent.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    records, targets = make_packet_records(generation, scoring, run_root, selected)
    if args.limit is not None:
        records, targets = records[:args.limit], targets[:args.limit]
    if not records:
        raise SystemExit("no eligible rescue questions")
    started = time.monotonic()
    # Freeze protocol and implementation before the first model call.
    sources = protocol_sources(condition)
    protocol = {
        "revision": condition.revision,
        "level": condition.name,
        "lineage": lineage,
        "policy": condition.policy,
        "parent_generation_sha256": parent["parent_generation_sha256"],
        "question_ids": [t["question_id"] for t in targets],
        "workers": args.workers, "timeout_per_phase": args.timeout,
        "model": agent_call.MODEL, "reasoning_effort": agent_call.REASONING_EFFORT,
        "agent": agent,
        "max_calls_per_question": condition.max_calls_per_question,
        "policy_retry": False,
        "evaluator": "unchanged offline surrogate",
        "feedback": "B3 No only; no C historical answers or private ideals",
        "interpretation": "developmental single revision, not causal superiority evidence",
        "repair_prompt_sha256": hashlib.sha256(condition.repair_prompt.encode()).hexdigest(),
        "sources": [{"path": str(p.relative_to(ROOT)), "sha256": digest(p)} for p in sources]}
    write_json(run_root / "protocol.json", protocol)
    write_json(run_root / "prompt_snapshot.json", {"prompt": condition.repair_prompt})
    for path in sources:
        destination = run_root / "code_snapshot" / path.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
    finished = {row["question_id"]: done for _, row, _ in records
                if (done := finished_repair(run_root, row["question_id"])) is not None}
    progress_log(f"C/{condition.name}", f"rescue targets={len(records)} finished={len(finished)} "
                 f"locked={len(parent['locked_yes_question_ids'])} workers={args.workers}")

    def repair(item):
        qid = item[1]["question_id"]
        if qid in finished:
            return finished[qid]
        # An unfinished question restarts from nothing; its partial workspaces are discarded.
        for stage in ("repair_questions", "blind_contracts"):
            shutil.rmtree(run_root / stage / qid, ignore_errors=True)
        return condition.run_question(item[0], item[1], item[2], run_root, args.timeout)

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(args.workers, len(records))) as pool:
        repairs = list(pool.map(repair, records))
    success = sum(bool(item.get("accepted")) and not item.get("fallback_to_primary") for item in repairs)
    final = {
        "level": condition.name,
        "protocol": protocol,
        "parent": parent,
        "locked_b3_success_question_ids": parent["locked_yes_question_ids"],
        "rescue": repairs,
        "rescue_question_ids": [item["question_id"] for item in repairs],
        "c_rescue_success_question_ids": [item["question_id"] for item in repairs if bool(item.get("accepted")) and not item.get("fallback_to_primary")],
        "generation_summary": {
            "b3_rerun": False,
            "b3_baseline_correct": len(parent["locked_yes_question_ids"]),
            "c_rescue_targets": len(repairs),
            "c_rescue_success": success,
            "policy_interrupted_repairs": sum(item.get("controller_status") == "interrupted_policy_violation" for item in repairs),
            "total_agent_calls": sum(item.get("total_agent_calls", 0) for item in repairs),
            "usage": {key: sum(r.get("usage", {}).get(key, 0) for r in repairs)
                      for key in {k for r in repairs for k in r.get("usage", {})}},
            "wall_runtime_seconds": time.monotonic() - started,
            "resumed_finished_questions": len(finished),
            "scorer_or_evaluator_used_during_generation": False,
        },
        "freeze": {"status": "frozen_before_private_scoring", "parent_generation_sha256": parent["parent_generation_sha256"], "parent_scoring_sha256": parent["parent_scoring_sha256"],
            "artifacts": freeze_artifacts(repairs, ("question_only.json", "repair_packet.json", "primary_result.json", "primary_grounding.json", "blind_contract.json", "analysis/semantic_audit.json", "analysis/grounding.json", "repair_result.json", "final_result.json", "events.jsonl", "run_manifest.json", "isolation_boundary.json"), scripts=True)},
    }
    for entry in protocol["sources"]:
        if digest(ROOT / entry["path"]) != entry["sha256"]:
            raise RuntimeError("protocol code changed during run")
    final["freeze"]["artifacts"].append({"path": str((run_root / "protocol.json").relative_to(ROOT)), "sha256": digest(run_root / "protocol.json")})
    for path in sorted((run_root / "code_snapshot").rglob("*")):
        if path.is_file():
            final["freeze"]["artifacts"].append({"path": str(path.relative_to(ROOT)), "sha256": digest(path)})
    final["freeze"]["artifacts"].append({"path": str((run_root / "prompt_snapshot.json").relative_to(ROOT)), "sha256": digest(run_root / "prompt_snapshot.json")})
    for path in sorted((run_root / "blind_contracts").rglob("*")):
        if path.is_file() and not path.is_symlink() and path.name in {"blind_contract.json", "question_only.json", "phase_freeze.json", "events.jsonl"}:
            final["freeze"]["artifacts"].append({"path": str(path.relative_to(ROOT)), "sha256": digest(path)})
    final["experiment_revision"] = protocol["revision"] + (" controller-failure retry" if selected is not None else " full rescue")
    final["prior_generation"] = str(args.retry_failed_from) if args.retry_failed_from else None
    write_json(output, final)
    report.write_text(
        f"# {condition.revision}: C rescue over frozen B\n\n"
        f"Level lineage: {' > '.join(reversed(lineage))}.\n\n"
        f"B baseline correct: {len(parent['locked_yes_question_ids'])}/{parent['question_count']}.\n\n"
        f"C rescue targets: {len(repairs)}; C rescue successes: {success}.\n\n"
        "B was not re-run. The final score is frozen B successes plus C-only rescue successes.\n",
        encoding="utf-8",
    )
    print(json.dumps(final["generation_summary"], indent=2))
