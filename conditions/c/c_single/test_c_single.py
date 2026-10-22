# Path: conditions/c/c_single/test_c_single.py
# Purpose: c_single = c_minimal + required semantic audit; own prompt; everything else inherited.
from __future__ import annotations

import ast
import json
import tempfile
import unittest
from pathlib import Path

from conditions.c.c_minimal.pipeline import MinimalRepair
from conditions.c.c_minimal.test_support import proposal, repair_step, run_repair
from conditions.c.c_single.pipeline import SingleRepair
from conditions.c.c_single.prompts import SINGLE_REPAIR_PROMPT
from conditions.c.c_single.semantic_audit import FIELDS, validate_audit

SOURCE = Path(__file__).resolve().parents[4] / "ngch_78_frozen_release_20261021/solver/conditions/c/runner.py"


class SingleRepairTests(unittest.TestCase):
    def test_extends_c_minimal(self):
        self.assertTrue(issubclass(SingleRepair, MinimalRepair))
        self.assertEqual([name for name, _ in SingleRepair.lineage()], ["c_single", "c_minimal"])
        self.assertEqual((SingleRepair.policy, SingleRepair.max_calls_per_question), ("single", 1))
        self.assertIs(SingleRepair.run_question, MinimalRepair.run_question, "pipeline is inherited, not copied")
        self.assertIs(SingleRepair.pre_repair, MinimalRepair.pre_repair)
        self.assertEqual(json.loads((SingleRepair.package_dir / "config.json").read_text())["extends"], "c_minimal")

    @unittest.skipUnless(SOURCE.is_file(), "frozen source package not present")
    def test_prompt_is_byte_identical_to_source(self):
        consts = {n.targets[0].id: n.value.value for n in ast.parse(SOURCE.read_text()).body
                  if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and isinstance(n.value, ast.Constant)}
        self.assertEqual(SINGLE_REPAIR_PROMPT, consts["SINGLE_REPAIR_PROMPT"])

    def test_accepts_like_c_minimal_when_audit_passes(self):
        repair, agent, _ = run_repair(SingleRepair(), [repair_step(proposal(), audit=True)])
        self.assertTrue(repair["accepted"])
        self.assertEqual(repair["semantic_audit"]["question_id"], "bix-1-q2")
        self.assertEqual((len(agent.calls), agent.calls[0]["prompt"]), (1, SINGLE_REPAIR_PROMPT))
        self.assertIsNone(repair["blind_workspace"])

    def test_added_step_rejects_a_repair_c_minimal_accepts(self):
        minimal, _, _ = run_repair(MinimalRepair(), [repair_step(proposal(), audit=False)])
        single, _, files = run_repair(SingleRepair(), [repair_step(proposal(), audit=False)])
        self.assertTrue(minimal["accepted"])
        self.assertFalse(single["accepted"])
        self.assertIn("semantic_audit.json", single["failure_reason"])
        self.assertEqual(json.loads(files["final_result.json"])["results"][0]["candidates"][0]["answer"], "old")

    def test_inherited_policy_interruption(self):
        step = repair_step(proposal(), audit=True, violation={"reason": "evaluator"})
        repair, agent, _ = run_repair(SingleRepair(), [step])
        self.assertEqual((len(agent.calls), repair["controller_status"]), (1, "interrupted_policy_violation"))

    def test_complete_field_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            w = Path(tmp)
            (w / "analysis").mkdir()
            audit = {"question_id": "q", "fields": [{"field": k, "status": "matched",
                     "evidence": "question wording"} for k in FIELDS],
                     "answer_contract_check": "units and requested estimator checked"}
            path = w / "analysis/semantic_audit.json"
            path.write_text(json.dumps(audit))
            validate_audit(w, "q")
            audit["fields"].pop()
            path.write_text(json.dumps(audit))
            with self.assertRaisesRegex(ValueError, "seven"):
                validate_audit(w, "q")


if __name__ == "__main__":
    unittest.main()
