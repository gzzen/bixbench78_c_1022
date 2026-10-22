# Path: conditions/c/c_minimal/test_c_minimal.py
# Purpose: c_minimal base pipeline over fake OpenCode calls: accept, fallback, policy interruption, failures.
from __future__ import annotations

import ast
import hashlib
import json
import unittest
from pathlib import Path

from conditions.c.c_minimal import agent_call, pipeline
from conditions.c.c_minimal.pipeline import MinimalRepair
from conditions.c.c_minimal.prompts import MINIMAL_REPAIR_PROMPT
from conditions.c.c_minimal.test_support import ROW, command, proposal, repair_step, run_repair, text

SOURCE = Path(__file__).resolve().parents[4] / "ngch_78_frozen_release_20261021/solver/conditions/c/runner.py"


class MinimalRepairTests(unittest.TestCase):
    def run_minimal(self, steps):
        return run_repair(MinimalRepair(), steps)

    def test_level_attributes(self):
        self.assertEqual((MinimalRepair.name, MinimalRepair.policy, MinimalRepair.max_calls_per_question),
                         ("c_minimal", "minimal", 1))
        self.assertEqual([name for name, _ in MinimalRepair.lineage()], ["c_minimal"])
        self.assertEqual(json.loads((MinimalRepair.package_dir / "config.json").read_text())["extends"], "frozen_b_parent")

    def test_prompt_hash_matches_historical_protocol(self):
        # repair_prompt_sha256 recorded in all five selected runs/c/*/protocol.json.
        self.assertEqual(hashlib.sha256(MINIMAL_REPAIR_PROMPT.encode()).hexdigest(),
                         "60d926643dfb054ab061bb5d2824faf9305c3a64b29b69e989ef7f4247032586")

    @unittest.skipUnless(SOURCE.is_file(), "frozen source package not present")
    def test_prompt_is_byte_identical_to_source(self):
        consts = {n.targets[0].id: n.value.value for n in ast.parse(SOURCE.read_text()).body
                  if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and isinstance(n.value, ast.Constant)}
        self.assertEqual(MINIMAL_REPAIR_PROMPT, consts["MINIMAL_REPAIR_PROMPT"])

    def test_valid_repair_replaces_only_the_target_answer(self):
        repair, agent, files = self.run_minimal([repair_step(proposal())])
        self.assertTrue(repair["accepted"])
        self.assertFalse(repair["fallback_to_primary"])
        self.assertEqual(repair["final_result"]["results"][0]["candidates"][0]["answer"], "new")
        self.assertEqual([r["question_id"] for r in repair["final_result"]["results"]], [ROW["question_id"]])
        self.assertEqual((len(agent.calls), repair["total_agent_calls"]), (1, 1))
        self.assertEqual(agent.calls[0]["schema"], "repair_result.schema.json")
        self.assertEqual(agent.calls[0]["prompt"], MINIMAL_REPAIR_PROMPT)
        self.assertEqual(json.loads(files["repair_packet.json"])["evaluator_verdict"], "no")
        self.assertEqual(json.loads(files["question_only.json"]), ROW)
        self.assertIn("analysis/scripts/b.py", files, "frozen B scripts are handed to the repair workspace")
        self.assertNotIn("semantic_audit", repair)
        self.assertIsNone(repair["blind_workspace"])

    def test_no_semantic_audit_is_required(self):
        repair, _, files = self.run_minimal([repair_step(proposal(), audit=False)])
        self.assertTrue(repair["accepted"])
        self.assertNotIn("analysis/semantic_audit.json", files)

    def test_abstention_falls_back_to_frozen_b(self):
        repair, _, files = self.run_minimal([repair_step(proposal(dimensions=(), resolved=False))])
        self.assertTrue(repair["accepted"])
        self.assertTrue(repair["fallback_to_primary"])
        self.assertEqual(json.loads(files["final_result.json"])["results"][0]["candidates"][0]["answer"], "old")

    def test_policy_violation_is_one_call_and_keeps_b(self):
        step = repair_step(proposal(), violation={"type": "controller.policy_violation", "reason": "evaluator"})
        repair, agent, files = self.run_minimal([step])
        self.assertEqual(len(agent.calls), 1)
        self.assertEqual(repair["controller_status"], "interrupted_policy_violation")
        self.assertFalse(repair["accepted"] or repair["retry_attempted"])
        self.assertEqual(json.loads(files["final_result.json"])["results"][0]["candidates"][0]["answer"], "old")

    def test_missing_json_output_fails_closed(self):
        repair, _, files = self.run_minimal([repair_step(None)])
        self.assertEqual(repair["controller_status"], "failed")
        self.assertIn("no final assistant text", repair["failure_reason"])
        self.assertEqual(json.loads(files["final_result.json"])["results"][0]["candidates"][0]["answer"], "old")

    def test_nonzero_exit_fails_closed(self):
        repair, _, _ = self.run_minimal([repair_step(proposal(), code=1)])
        self.assertEqual(repair["controller_status"], "failed")
        self.assertIn("generation exit=1", repair["failure_reason"])

    def test_declared_source_must_have_execution_evidence(self):
        step = repair_step(proposal(), events=[command("python -c 'print(42)'"), text(proposal())])
        repair, _, _ = self.run_minimal([step])
        self.assertFalse(repair["accepted"])
        self.assertIn("lacks execution evidence", repair["failure_reason"])

    def test_missing_grounding_fails_closed(self):
        repair, _, _ = self.run_minimal([repair_step(proposal(), grounding=False)])
        self.assertFalse(repair["accepted"])
        self.assertIn("grounding", repair["failure_reason"])

    def test_localize_paths_strips_absolute_parent_script_paths(self):
        self.assertEqual(pipeline.localize_repair_paths({"e": "ran /host/run/ws/analysis/scripts/a.py"}),
                         {"e": "ran analysis/scripts/a.py"})

    def test_usage_reads_opencode_step_finish_tokens(self):
        step = {"event": {"type": "step_finish", "part": {"type": "step-finish",
                "tokens": {"input": 10, "output": 4, "reasoning": 2, "cache": {"read": 3, "write": 0}}}}}
        self.assertEqual(agent_call.captured_usage([step, step]),
                         {"input": 20, "output": 8, "reasoning": 4, "cache_read": 6, "cache_write": 0})
        self.assertEqual(agent_call.captured_usage([{"type": "turn.completed", "usage": {"input_tokens": 5}}]),
                         {"input_tokens": 5})


if __name__ == "__main__":
    unittest.main()
