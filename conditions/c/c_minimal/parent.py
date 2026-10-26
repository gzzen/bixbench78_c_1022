# Path: conditions/c/c_minimal/parent.py
# Purpose: Load and verify the frozen B parent and its post-freeze scoring; build per-question repair packets.
"""Failure-triggered C rescue over an immutable B parent.

C never calls the B runner.  It reads the frozen B generation and post-freeze
scoring artifacts, locks every B Yes, and sends only B No or unresolved
questions to the question-local C repair.  Only the per-question
correct/accepted/resolved booleans are read from scoring; never answers.
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import shutil
from pathlib import Path

from common.benchmark.a84_contract import load_rows, public_question, write_json
from common.integrity.freeze import frozen_workspace

ROOT = Path(__file__).resolve().parents[3]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def is_locked(verdict: dict) -> bool:
    return bool(verdict["correct"] and verdict.get("accepted") and verdict.get("resolved"))


def load_parent(generation_path: Path, scoring_path: Path, registry_path: Path) -> tuple[dict, dict, dict]:
    generation = json.loads(generation_path.read_text(encoding="utf-8"))
    scoring = json.loads(scoring_path.read_text(encoding="utf-8"))
    if generation.get("freeze", {}).get("status") != "frozen_before_private_scoring":
        raise RuntimeError("B generation is not frozen")
    if scoring.get("status") != "completed_posthoc_after_freeze":
        raise RuntimeError("B scoring is not complete")
    if "source_generation_sha256" in scoring and scoring["source_generation_sha256"] != digest(generation_path):
        raise RuntimeError("B scoring was made for a different B generation")
    for artifact in generation["freeze"]["artifacts"]:
        path = ROOT / artifact["path"]
        if artifact.get("sha256") and (not path.is_file() or digest(path) != artifact["sha256"]):
            raise RuntimeError(f"B frozen artifact changed: {artifact['path']}")
    verdicts = {item["question_id"]: item for item in scoring["verdicts"]}
    for episode in generation["episodes"]:
        workspace = frozen_workspace(episode["workspace"], ROOT)
        if episode.get("accepted") and not (workspace / "capsule_result.json").is_file():
            raise RuntimeError(f"accepted B episode has no frozen capsule_result.json: {workspace}")
    generation_ids = [qid for episode in generation["episodes"] for qid in episode["question_ids"]]
    if len(verdicts) != len(scoring["verdicts"]) or sorted(verdicts) != sorted(generation_ids):
        raise RuntimeError("B scoring question IDs do not match the frozen B generation")
    locked = [qid for qid, verdict in verdicts.items() if is_locked(verdict)]
    rescue = [qid for qid in verdicts if qid not in locked]
    parent = {
        "status": "frozen_b3_parent",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "parent_generation": _relative(generation_path),
        "parent_generation_sha256": digest(generation_path),
        "parent_scoring": _relative(scoring_path),
        "parent_scoring_sha256": digest(scoring_path),
        "parent_freeze_manifest_sha256": generation["freeze"]["manifest_sha256"],
        "question_count": len(verdicts),
        "locked_yes_question_ids": locked,
        "rescue_question_ids": rescue,
        "locked_rule": "B3 evaluator Yes is immutable; C cannot rewrite it",
        "rescue_rule": "only B3 evaluator No or unresolved enters C",
    }
    if registry_path.exists():
        existing = json.loads(registry_path.read_text(encoding="utf-8"))
        comparable = copy.deepcopy(existing)
        comparable.pop("created_at", None)
        expected = copy.deepcopy(parent)
        expected.pop("created_at", None)
        if comparable != expected:
            raise RuntimeError("frozen B parent manifest mismatch")
        parent = existing
    else:
        write_json(registry_path, parent)
    return generation, scoring, parent


def make_packet_records(generation: dict, scoring: dict, run_root: Path, selected: set[str] | None = None) -> tuple[list, list[dict]]:
    verdicts = {item["question_id"]: item for item in scoring["verdicts"]}
    rows = {row["question_id"]: public_question(row) for row in load_rows()}
    episodes = {item["short_id"]: item for item in generation["episodes"]}
    packet_root = run_root / "frozen_parent_packets"
    records = []
    targets = []
    for qid, verdict in verdicts.items():
        if is_locked(verdict) or (selected is not None and qid not in selected):
            continue
        row = rows[qid]
        episode = episodes[row["short_id"]]
        source = frozen_workspace(episode["workspace"], ROOT)
        packet = packet_root / qid
        packet.mkdir(parents=True, exist_ok=True)
        primary_path = source / "capsule_result.json"
        grounding_path = source / "analysis/grounding.json"
        if primary_path.is_file():
            shutil.copy2(primary_path, packet / "primary_canonical.json")
        elif episode.get("accepted"):
            raise RuntimeError(f"accepted B episode has no frozen capsule_result.json: {source}")
        else:
            # A failed B episode may have no result; keep the capsule identity so the
            # missing-result reconstruction path can run.
            write_json(packet / "primary_canonical.json", {
                "capsule_uuid": episode["capsule_uuid"], "short_id": episode["short_id"],
                "results": [{"question_id": item, "status": "unresolved", "candidates": []}
                            for item in episode["question_ids"]]})
        if grounding_path.is_file():
            (packet / "analysis").mkdir(exist_ok=True)
            shutil.copy2(grounding_path, packet / "analysis/grounding.json")
        # Carry frozen executable evidence; never import the B conversation.
        inventory = []
        used_bytes = 0
        frozen = {a["path"]: a["sha256"] for a in generation["freeze"]["artifacts"] if a.get("sha256")}
        for path in sorted((source / "analysis/scripts").rglob("*")):
            if not path.is_file() or path.is_symlink() or path.suffix == ".pyc":
                continue
            relative = path.relative_to(source)
            expected = frozen.get(str(path.relative_to(ROOT)))
            if expected is None or digest(path) != expected:
                raise RuntimeError(f"parent source not frozen: {path}")
            destination = packet / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
            inventory.append({"path": str(relative), "sha256": expected, "role": "B3 executed source"})
        # Compact scientific result files, with independent snapshot hashes.
        excluded = {"grounding.json", "compliance_audit.json", "operation_contract.json", "consistency.json"}
        for path in sorted((source / "analysis").rglob("*")):
            if not path.is_file() or path.is_symlink() or "scripts" in path.relative_to(source).parts:
                continue
            if path.name in excluded or path.suffix not in {".csv", ".tsv", ".json", ".txt"}:
                continue
            size = path.stat().st_size
            if size > 2_000_000 or used_bytes + size > 8_000_000:
                continue
            used_bytes += size
            relative = path.relative_to(source)
            destination = packet / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
            inventory.append({"path": str(relative), "sha256": digest(destination), "role": "B3 scientific intermediate snapshot"})
        write_json(packet / "imported_artifacts.json", inventory)
        episode_record = {
            "short_id": episode["short_id"],
            "capsule_uuid": episode["capsule_uuid"],
            "question_ids": episode["question_ids"],
            "workspace": str(packet),
            "accepted": bool(episode["accepted"]),
            "b_question_local_failures": episode.get("b_question_local_failures", {}),
            "b_grounding_failures": episode.get("b_grounding_failures", {}),
            "b_consistency_failures": episode.get("b_consistency_failures", {}),
            "event_metrics": episode.get("event_metrics", {}),
            "implementation": "frozen B3 parent; no B3 rerun",
        }
        records.append((episode_record, row, {"question_id": qid, "feedback": "no"}))
        targets.append({"question_id": qid, "short_id": row["short_id"], "verdict": verdict})
    return records, targets
