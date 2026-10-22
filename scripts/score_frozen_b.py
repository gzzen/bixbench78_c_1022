#!/usr/bin/env python3
# Path: scripts/score_frozen_b.py
# Purpose: Private post-freeze scoring of one frozen B generation; produces the parent scoring that C reads.
"""Score a frozen B generation against an answer key supplied from outside this checkout.

Run only after B is frozen.  The freeze status and every frozen artifact hash are
verified before the judge or answer key is loaded.  Verdict rules reuse the B
export (`export_rows`), so they match scoring the exported JSONL privately.
No ideal-answer text is written.  No generation code imports this module.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.export_predictions import export_rows, load_frozen, sha256  # noqa: E402

EVALUATOR_MODULE = "yes_no_open_evaluator.py"


def _inside_checkout(path: Path) -> bool:
    return path.resolve().is_relative_to(ROOT)


def verify_freeze(generation: dict[str, Any]) -> None:
    changed = []
    for artifact in generation["freeze"]["artifacts"]:
        path = ROOT / artifact["path"]
        if artifact.get("sha256") and (not path.is_file() or sha256(path) != artifact["sha256"]):
            changed.append(artifact["path"])
    if changed:
        raise RuntimeError(f"frozen B artifact changed: {changed[:3]}")


def load_judge(evaluator_dir: Path) -> Callable[[str, str], Any]:
    spec = importlib.util.spec_from_file_location("yes_no_open_evaluator", evaluator_dir / EVALUATOR_MODULE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {evaluator_dir / EVALUATOR_MODULE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.judge


def score(generation_path: Path, answers_path: Path, evaluator_dir: Path) -> dict[str, Any]:
    generation = load_frozen(generation_path)
    verify_freeze(generation)
    for path in (answers_path, evaluator_dir):
        if _inside_checkout(path):
            raise RuntimeError(f"private scoring input must live outside the checkout: {path}")
    rows = export_rows(generation, "b", generation_path.stem)
    if len(rows) != len({row["question_id"] for row in rows}):
        raise RuntimeError("generation contains duplicate question IDs")
    judge = load_judge(evaluator_dir)
    answers = json.loads(answers_path.read_text(encoding="utf-8"))
    verdicts = []
    for row in rows:
        candidates = row["candidates"]
        answer = str(candidates[0].get("answer", "")).strip() if candidates else ""
        verdicts.append({
            "question_id": row["question_id"],
            "present": bool(answer),
            "correct": bool(judge(answers[row["question_id"]], answer)) if answer else False,
            "accepted": row["controller_accepted"],
            "resolved": row["status"] == "resolved",
        })
    n = len(verdicts)
    raw = sum(v["correct"] for v in verdicts)
    answered = sum(v["present"] for v in verdicts)
    compliant = sum(v["correct"] and v["accepted"] and v["resolved"] for v in verdicts)
    return {
        "status": "completed_posthoc_after_freeze",
        "condition": "b",
        "scorer": "scripts/score_frozen_b.py",
        "source_generation": str(generation_path),
        "source_generation_sha256": sha256(generation_path),
        "source_manifest_sha256": generation["freeze"].get("manifest_sha256"),
        "evaluator_sha256": sha256(evaluator_dir / EVALUATOR_MODULE),
        "answers_sha256": sha256(answers_path),
        "private_ideal_answers_persisted": False,
        "questions": n,
        "raw_correct": raw,
        "raw_accuracy": raw / n,
        "answered": answered,
        "coverage": answered / n,
        "compliant_correct": compliant,
        "compliant_accuracy": compliant / n,
        "effective_answered": sum(v["present"] and v["accepted"] and v["resolved"] for v in verdicts),
        "verdicts": verdicts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Post-freeze private scoring of a frozen B generation (C parent).")
    parser.add_argument("--generation", type=Path, required=True, help="analysis/<tag>_generation.json")
    parser.add_argument("--answers", type=Path, required=True, help="private answer key, outside this checkout")
    parser.add_argument("--evaluator-dir", type=Path, required=True,
                        help=f"directory with {EVALUATOR_MODULE}, outside this checkout")
    parser.add_argument("--output", type=Path, help="default analysis/<tag>_scoring.json")
    parser.add_argument("--report", type=Path, help="default reports/<tag>_B_SCORING.md")
    args = parser.parse_args()

    generation_path = args.generation.resolve()
    tag = re.sub(r"_generation$", "", generation_path.stem)
    output = (args.output or ROOT / f"analysis/{tag}_scoring.json").resolve()
    report = (args.report or ROOT / f"reports/{tag}_B_SCORING.md").resolve()
    if output.exists():
        raise SystemExit(f"refusing to overwrite an existing scoring: {output}")
    scoring = score(generation_path, args.answers.resolve(), args.evaluator_dir.resolve())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(scoring, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    n = scoring["questions"]
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        f"# {tag}: frozen B scoring\n\n"
        "Private post-freeze score; no ideal-answer text is persisted. C locks every compliant correct question.\n\n"
        "| Metric | Value |\n|---|---:|\n"
        f"| Answer-only accuracy | {scoring['raw_correct']}/{n} ({scoring['raw_accuracy']:.2%}) |\n"
        f"| Coverage | {scoring['answered']}/{n} ({scoring['coverage']:.2%}) |\n"
        f"| Compliant effective accuracy | {scoring['compliant_correct']}/{n} ({scoring['compliant_accuracy']:.2%}) |\n",
        encoding="utf-8",
    )
    print(json.dumps({key: value for key, value in scoring.items() if key != "verdicts"}, indent=2))


if __name__ == "__main__":
    main()
