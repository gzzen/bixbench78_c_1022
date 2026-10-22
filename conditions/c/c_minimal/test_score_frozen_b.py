# Path: conditions/c/c_minimal/test_score_frozen_b.py
# Purpose: `scripts/score_frozen_b.py`: post-freeze B verdicts feed load_parent; key stays outside the checkout.
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from conditions.c.c_minimal.parent import ROOT, load_parent
from conditions.c.c_minimal.test_support import result
from scripts import score_frozen_b

JUDGE = "CALLS = []\n\ndef judge(ideal, answer):\n    CALLS.append(answer)\n    return ideal == answer\n"


class ScoreFrozenBTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.assertFalse(root.resolve().is_relative_to(ROOT), "fixture key must live outside the checkout")
        workspace = root / "b/bix-1"
        workspace.mkdir(parents=True)
        missing = {"question_id": "q3", "status": "unresolved", "candidates": [], "summary": "none"}
        (workspace / "capsule_result.json").write_text(json.dumps({"results": [
            result("q1", "right"), result("q2", "wrong"), missing, result("q4", "right")]}))
        self.artifact = workspace / "capsule_result.json"
        self.generation = root / "demo_b_generation.json"
        self.write_generation()
        self.evaluator = root / "private"
        self.evaluator.mkdir()
        (self.evaluator / "yes_no_open_evaluator.py").write_text(JUDGE)
        self.answers = self.evaluator / "answers.json"
        self.answers.write_text(json.dumps({q: "right" for q in ("q1", "q2", "q3", "q4")}))

    def tearDown(self):
        self.tmp.cleanup()

    def write_generation(self, status="frozen_before_private_scoring"):
        self.generation.write_text(json.dumps({
            "manifest": {"model": "deepseek/deepseek-flash", "reasoning_effort": "high"},
            "episodes": [{"short_id": "bix-1", "capsule_uuid": "cap", "question_ids": ["q1", "q2", "q3", "q4"],
                          "workspace": str(self.artifact.parent), "accepted": True,
                          "question_local_failures": {"q4": "grounding"}}],
            "freeze": {"status": status, "manifest_sha256": "m", "artifacts": [
                {"path": str(self.artifact), "sha256": hashlib.sha256(self.artifact.read_bytes()).hexdigest()}]}}))

    def score(self):
        return score_frozen_b.score(self.generation, self.answers, self.evaluator)

    def test_verdicts_follow_b_export_rules(self):
        scoring = self.score()
        verdicts = {v["question_id"]: v for v in scoring["verdicts"]}
        self.assertEqual(verdicts["q1"], {"question_id": "q1", "present": True, "correct": True,
                                          "accepted": True, "resolved": True})
        self.assertFalse(verdicts["q2"]["correct"])
        self.assertEqual((verdicts["q3"]["present"], verdicts["q3"]["correct"], verdicts["q3"]["resolved"]),
                         (False, False, False))
        self.assertTrue(verdicts["q4"]["correct"])
        self.assertFalse(verdicts["q4"]["accepted"], "question-local failure is not accepted")
        self.assertEqual((scoring["raw_correct"], scoring["answered"], scoring["compliant_correct"]), (2, 3, 1))
        self.assertEqual(scoring["status"], "completed_posthoc_after_freeze")
        self.assertFalse(scoring["private_ideal_answers_persisted"])
        self.assertNotIn("right", json.dumps({k: v for k, v in scoring.items() if k != "verdicts"}))

    def test_judge_is_loaded_by_path_and_not_called_without_an_answer(self):
        loaded = []
        real = score_frozen_b.load_judge

        def recording(directory):
            judge = real(directory)
            loaded.append(judge.__globals__["CALLS"])
            return judge

        with patch.object(score_frozen_b, "load_judge", recording):
            self.score()
        self.assertEqual(loaded, [["right", "wrong", "right"]])
        self.assertNotIn(str(self.evaluator), sys.path)

    def test_refuses_unfrozen_or_changed_generation(self):
        self.write_generation(status="running")
        with self.assertRaisesRegex(RuntimeError, "not frozen"):
            self.score()
        self.write_generation()
        self.artifact.write_text(self.artifact.read_text() + " ")
        with self.assertRaisesRegex(RuntimeError, "artifact changed"):
            self.score()

    def test_refuses_answer_key_or_evaluator_inside_checkout(self):
        with self.assertRaisesRegex(RuntimeError, "outside the checkout"):
            score_frozen_b.score(self.generation, ROOT / "answers.json", self.evaluator)
        with self.assertRaisesRegex(RuntimeError, "outside the checkout"):
            score_frozen_b.score(self.generation, self.answers, ROOT / "scripts")

    def test_scoring_feeds_load_parent_and_is_bound_to_its_generation(self):
        scoring_path = Path(self.tmp.name) / "scoring.json"
        scoring_path.write_text(json.dumps(self.score()))
        registry = Path(self.tmp.name) / "parent.json"
        _, _, parent = load_parent(self.generation, scoring_path, registry)
        self.assertEqual(parent["locked_yes_question_ids"], ["q1"])
        self.assertEqual(parent["rescue_question_ids"], ["q2", "q3", "q4"])
        self.generation.write_text(self.generation.read_text() + " ")
        registry.unlink()
        with self.assertRaisesRegex(RuntimeError, "different B generation"):
            load_parent(self.generation, scoring_path, registry)

    def test_generation_code_never_references_the_scorer(self):
        offenders = [str(path.relative_to(ROOT)) for top in ("conditions", "common")
                     for path in (ROOT / top).rglob("*.py")
                     if not path.name.startswith("test_")
                     and any(s in path.read_text(encoding="utf-8") for s in ("score_frozen_b", "yes_no_open_evaluator"))]
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
