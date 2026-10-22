# Path: conditions/c/c_blind/test_c_blind.py
# Purpose: c_blind = c_single + parent-blind contract phase; own prompts; audit and pipeline inherited.
from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path

from conditions.c.c_minimal.pipeline import MinimalRepair
from conditions.c.c_minimal.rescue_main import protocol_sources
from conditions.c.c_minimal.test_support import contract, contract_step, proposal, repair_step, run_repair
from conditions.c.c_single.pipeline import SingleRepair
from conditions.c.c_single.semantic_audit import FIELDS
from conditions.c.c_blind.blind_contract import validate_contract
from conditions.c.c_blind.pipeline import BlindRepair
from conditions.c.c_blind.prompts import BLIND_CONTRACT_PROMPT, QUESTION_REPAIR_PROMPT

SOURCE = Path(__file__).resolve().parents[4] / "ngch_78_frozen_release_20261021/solver/conditions/c/runner.py"


def run_blind(steps):
    return run_repair(BlindRepair(), steps)


class BlindRepairTests(unittest.TestCase):
    def test_extends_c_single(self):
        self.assertTrue(issubclass(BlindRepair, SingleRepair))
        self.assertEqual([name for name, _ in BlindRepair.lineage()], ["c_blind", "c_single", "c_minimal"])
        self.assertEqual((BlindRepair.policy, BlindRepair.max_calls_per_question), ("blind", 2))
        self.assertIs(BlindRepair.post_validate, SingleRepair.post_validate, "audit step is inherited")
        self.assertIs(BlindRepair.run_question, MinimalRepair.run_question)
        self.assertEqual(json.loads((BlindRepair.package_dir / "config.json").read_text())["extends"], "c_single")

    def test_protocol_snapshot_covers_the_whole_lineage(self):
        directories = {path.parent.name for path in protocol_sources(BlindRepair()) if "conditions" in path.parts}
        self.assertTrue({"c_blind", "c_single", "c_minimal"} <= directories)

    @unittest.skipUnless(SOURCE.is_file(), "frozen source package not present")
    def test_prompts_are_byte_identical_to_source(self):
        tree = ast.parse(SOURCE.read_text())
        consts = {n.targets[0].id: n.value.value for n in tree.body if isinstance(n, ast.Assign)
                  and isinstance(n.targets[0], ast.Name) and isinstance(n.value, ast.Constant)}
        self.assertEqual(QUESTION_REPAIR_PROMPT, consts["QUESTION_REPAIR_PROMPT"])
        blind = next(n.value.value for n in ast.walk(tree) if isinstance(n, ast.Assign)
                     and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "blind_prompt")
        self.assertEqual(BLIND_CONTRACT_PROMPT, blind)

    def test_verbatim_constraints(self):
        row = {"question_id": "q", "question": "Compare median scores."}
        payload = {"question_id": "q", "fields": dict.fromkeys(FIELDS, "unspecified"),
                   "explicit_constraints": ["median scores"], "ambiguities": []}
        validate_contract(payload, row)
        payload["explicit_constraints"] = ["mean scores"]
        with self.assertRaisesRegex(ValueError, "verbatim"):
            validate_contract(payload, row)

    def test_two_calls_and_blind_phase_sees_no_parent_artifacts(self):
        repair, agent, files = run_blind([contract_step(contract()), repair_step(proposal(), audit=True)])
        self.assertTrue(repair["accepted"])
        self.assertEqual((len(agent.calls), repair["total_agent_calls"]), (2, 2))
        self.assertEqual(agent.calls[0]["schema"], "semantic_contract.schema.json")
        self.assertEqual([c["prompt"] for c in agent.calls], [BLIND_CONTRACT_PROMPT, QUESTION_REPAIR_PROMPT])
        self.assertNotEqual(agent.calls[0]["workspace"], agent.calls[1]["workspace"])
        self.assertEqual([(c["workspace"].parent.name, c["workspace"].name) for c in agent.calls],
                         [("blind_contracts", "bix-1-q2__cap-1"), ("repair_questions", "bix-1-q2__cap-1")])
        self.assertEqual(json.loads(files["blind_contract.json"])["explicit_constraints"], ["median expression"])
        self.assertIn("<blind>/phase_freeze.json", files)
        blind_files = {name for name in files if name.startswith("<blind>/")}
        self.assertFalse({"<blind>/primary_result.json", "<blind>/repair_packet.json",
                          "<blind>/primary_grounding.json"} & blind_files)

    def test_invalid_contract_skips_repair_and_keeps_b(self):
        repair, agent, files = run_blind([contract_step(contract(explicit_constraints=["invented"]))])
        self.assertEqual((len(agent.calls), repair["total_agent_calls"]), (1, 1))
        self.assertFalse(repair["accepted"])
        self.assertIn("blind contract failure", repair["failure_reason"])
        self.assertNotIn("blind_contract.json", files)
        self.assertEqual(repair["final_result"]["results"][0]["candidates"][0]["answer"], "old")

    def test_blind_policy_violation_skips_repair(self):
        repair, agent, _ = run_blind([contract_step(contract(), violation={"reason": "evaluator"})])
        self.assertEqual(len(agent.calls), 1)
        self.assertIn("policy violation", repair["failure_reason"])

    def test_inherited_audit_step_still_applies(self):
        repair, _, _ = run_blind([contract_step(contract()), repair_step(proposal(), audit=False)])
        self.assertFalse(repair["accepted"])
        self.assertEqual(repair["final_result"]["results"][0]["candidates"][0]["answer"], "old")


if __name__ == "__main__":
    unittest.main()
