# Path: conditions/c/c_minimal/test_export.py
# Purpose: `export_predictions --condition c`: B rows for locked questions, C answers only for validated rescues.
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.export_predictions import c_rows
from conditions.c.c_minimal.test_support import result


class CExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        workspace = root / "b/bix-1"
        workspace.mkdir(parents=True)
        (workspace / "capsule_result.json").write_text(json.dumps({"results": [
            result("q1", "kept"), result("q2", "old"), result("q3", "old"), result("q4", "old")]}))
        self.parent = root / "b_generation.json"
        self.parent.write_text(json.dumps({
            "manifest": {"model": "deepseek/deepseek-flash", "reasoning_effort": "high"},
            "episodes": [{"short_id": "bix-1", "capsule_uuid": "cap", "question_ids": ["q1", "q2", "q3", "q4"],
                          "workspace": str(workspace), "accepted": True, "question_local_failures": {"q4": "x"}}],
            "freeze": {"status": "frozen_before_private_scoring", "manifest_sha256": "m"}}))
        self.generation = {
            "level": "c_blind", "protocol": {"lineage": ["c_blind", "c_single", "c_minimal"]},
            "parent": {"parent_generation": str(self.parent),
                       "parent_generation_sha256": hashlib.sha256(self.parent.read_bytes()).hexdigest(),
                       "parent_scoring_sha256": "s", "locked_yes_question_ids": ["q1"],
                       "rescue_question_ids": ["q2", "q3", "q4"]},
            "rescue": [
                {"question_id": "q2", "accepted": True, "fallback_to_primary": False, "controller_status": "passed",
                 "final_result": {"results": [result("q2", "new")]}},
                {"question_id": "q3", "accepted": True, "fallback_to_primary": True, "controller_status": "passed",
                 "final_result": {"results": [result("q3", "old")]}},
                {"question_id": "q4", "accepted": False, "controller_status": "failed",
                 "final_result": {"results": [result("q4", "old")]}},
            ]}

    def tearDown(self):
        self.tmp.cleanup()

    def test_only_validated_rescues_replace_b(self):
        rows, extra = c_rows(self.generation, "run")
        by_id = {row["question_id"]: row for row in rows}
        self.assertEqual(by_id["q1"]["candidates"][0]["answer"], "kept")
        self.assertTrue(by_id["q1"]["controller_accepted"] and by_id["q1"]["b_locked"])
        self.assertEqual(by_id["q2"]["candidates"][0]["answer"], "new")
        self.assertTrue(by_id["q2"]["controller_accepted"] and by_id["q2"]["c_replaced"])
        for qid in ("q3", "q4"):
            self.assertFalse(by_id[qid]["controller_accepted"] or by_id[qid]["c_replaced"])
        self.assertEqual((extra["c_replaced_answers"], extra["locked_b_questions"]), (1, 1))
        self.assertEqual(extra["c_lineage"], ["c_blind", "c_single", "c_minimal"])
        self.assertEqual({row["condition"] for row in rows}, {"c"})

    def test_rejects_changed_parent_or_rescued_locked_question(self):
        self.generation["rescue"].append({"question_id": "q1", "accepted": True})
        with self.assertRaisesRegex(RuntimeError, "locked"):
            c_rows(self.generation, "run")
        self.generation["rescue"].pop()
        self.parent.write_text(self.parent.read_text() + " ")
        with self.assertRaisesRegex(RuntimeError, "hash mismatch"):
            c_rows(self.generation, "run")


if __name__ == "__main__":
    unittest.main()
