#!/usr/bin/env python3
# Path: conditions/c/c_minimal/test_repair_policy.py
# Purpose: Regression tests for standalone C-v2 conservative repair invariants.
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from conditions.c.c_minimal.repair.repair_policy import audit_repair_execution, failed_repair_result, finalize_repair
from conditions.c.c_minimal.pipeline import normalize_question_repair_proposal, preserve_primary_on_unresolved


def result(qid: str, answer: str) -> dict:
    return {
        "question_id": qid,
        "status": "resolved",
        "candidates": [{"answer": answer, "method": "method", "evidence": "evidence"}],
        "summary": "summary",
    }


class RepairPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.primary = {
            "capsule_uuid": "capsule",
            "short_id": "bix-test",
            "workflow_summary": "primary",
            "results": [result("q1", "keep"), result("q2", "old")],
        }
        self.feedback = [
            {"question_id": "q1", "feedback": "yes"},
            {"question_id": "q2", "feedback": "no"},
        ]

    def proposal(self, dimensions: list[str], *, reran: bool = True, sources: list[str] | None = None) -> dict:
        return {
            "capsule_uuid": "capsule",
            "short_id": "bix-test",
            "workflow_summary": "repair",
            "results": [result("q1", "malicious rewrite"), result("q2", "new")],
            "repair_records": [{
                "question_id": "q2",
                "primary_feedback": "no",
                "diagnosis": "one suspected decision",
                "changed_dimensions": dimensions,
                "rationale": "supported by public input",
                "interpretations": [
                    {"interpretation": "old", "evidence": "primary evidence"},
                    {"interpretation": "new", "evidence": "capsule evidence"},
                ],
                "execution": {
                    "reran_analysis": reran,
                    "computation_required": bool(sources),
                    "source_files": sources or [],
                },
            }],
        }

    def test_yes_result_is_controller_frozen(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            final, provenance = finalize_repair(
                self.primary, self.proposal(["unit_precision_type"]), self.feedback, Path(value)
            )
        self.assertEqual(final["results"][0], self.primary["results"][0])
        self.assertEqual(provenance[0]["changed_dimension"], "unit_precision_type")

    def test_four_dimensions_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            with self.assertRaisesRegex(ValueError, "at most three"):
                finalize_repair(self.primary, self.proposal(
                    ["scope_filter", "statistical_method", "entity_mapping", "unit_precision_type"]),
                    self.feedback, Path(value))

    def test_coupled_dimensions_accept_two_interpretations(self) -> None:
        proposal = self.proposal(["scope_filter", "statistical_method"])
        proposal["repair_records"][0]["interpretations"] = proposal["repair_records"][0]["interpretations"][:2]
        with tempfile.TemporaryDirectory() as value:
            _, provenance = finalize_repair(self.primary, proposal, self.feedback, Path(value))
            self.assertEqual(provenance[0]['changed_dimensions'], ['scope_filter', 'statistical_method'])

    def test_changed_repair_must_rerun(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            with self.assertRaisesRegex(ValueError, "must rerun"):
                finalize_repair(
                    self.primary, self.proposal(["entity_mapping"], reran=False), self.feedback, Path(value)
                )

    def test_computational_repair_requires_persisted_source(self) -> None:
        proposal = self.proposal(["statistical_method"])
        proposal["repair_records"][0]["execution"]["computation_required"] = True
        with tempfile.TemporaryDirectory() as value:
            with self.assertRaisesRegex(ValueError, "requires persisted source"):
                finalize_repair(self.primary, proposal, self.feedback, Path(value))

    def test_persisted_source_is_hashed(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            workspace = Path(value)
            source = workspace / "analysis/scripts/repair.py"
            source.parent.mkdir(parents=True)
            source.write_text("print('repair')\n", encoding="utf-8")
            final, provenance = finalize_repair(
                self.primary,
                self.proposal(["statistical_method"], sources=["analysis/scripts/repair.py"]),
                self.feedback,
                workspace,
            )
        self.assertEqual(final["results"][1]["candidates"][0]["answer"], "new")
        self.assertEqual(len(provenance[0]["source_files"][0]["sha256"]), 64)

    def test_input_data_may_accompany_persisted_program(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            workspace = Path(value)
            script = workspace / "analysis/scripts/repair.py"
            data = workspace / "data/input.csv"
            script.parent.mkdir(parents=True)
            data.parent.mkdir(parents=True)
            script.write_text("print('repair')\n", encoding="utf-8")
            data.write_text("value\n1\n", encoding="utf-8")
            _, provenance = finalize_repair(
                self.primary,
                self.proposal(
                    ["statistical_method"],
                    sources=["analysis/scripts/repair.py", "data/input.csv"],
                ),
                self.feedback,
                workspace,
            )
        self.assertEqual([item["path"] for item in provenance[0]["source_files"]], [
            "analysis/scripts/repair.py", "data/input.csv",
        ])

    def test_no_dimension_requires_unresolved(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            with self.assertRaisesRegex(ValueError, "must be unresolved"):
                finalize_repair(self.primary, self.proposal([], reran=False), self.feedback, Path(value))

    def test_defensible_abstention_is_accepted(self) -> None:
        proposal = self.proposal([], reran=False)
        proposal["results"][1] = {
            "question_id": "q2", "status": "unresolved", "candidates": [], "summary": "no defensible repair"
        }
        with tempfile.TemporaryDirectory() as value:
            final, provenance = finalize_repair(self.primary, proposal, self.feedback, Path(value))
        self.assertEqual(final["results"][1]["status"], "unresolved")
        self.assertIsNone(provenance[0]["changed_dimension"])

    def test_abstention_after_persisted_analysis_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            workspace = Path(value)
            source = workspace / "analysis/scripts/check.py"
            source.parent.mkdir(parents=True)
            source.write_text("print('checked')\n", encoding="utf-8")
            proposal = self.proposal([], sources=["analysis/scripts/check.py"])
            proposal["results"][1] = {
                "question_id": "q2", "status": "unresolved", "candidates": [], "summary": "no defensible repair"
            }
            final, provenance = finalize_repair(self.primary, proposal, self.feedback, workspace)
        self.assertEqual(final["results"][1]["status"], "unresolved")
        self.assertEqual(provenance[0]["source_files"][0]["path"], "analysis/scripts/check.py")

    def test_capsule_identity_mismatch_is_rejected(self) -> None:
        proposal = self.proposal(["unit_precision_type"])
        proposal["capsule_uuid"] = "wrong"
        with tempfile.TemporaryDirectory() as value:
            with self.assertRaisesRegex(ValueError, "identity mismatch"):
                finalize_repair(self.primary, proposal, self.feedback, Path(value))

    def test_failed_repair_preserves_imported_b_results(self) -> None:
        final = failed_repair_result(self.primary, self.feedback, "malformed repair")
        self.assertEqual(final["results"], self.primary["results"])

    def test_unresolved_question_repair_falls_back_only_that_question(self) -> None:
        proposed = {
            **self.primary,
            "results": [
                result("q1", "changed"),
                {"question_id": "q2", "status": "unresolved", "candidates": [], "summary": "abstain"},
            ],
        }
        final, fallback_ids = preserve_primary_on_unresolved(self.primary, proposed)
        self.assertEqual(final["results"][0]["candidates"][0]["answer"], "changed")
        self.assertEqual(final["results"][1], self.primary["results"][1])
        self.assertEqual(fallback_ids, ["q2"])

    def test_unsupported_resolved_noop_becomes_safe_abstention(self) -> None:
        proposal = {
            "results": [result("q2", "guessed")],
            "repair_records": [{"question_id": "q2", "changed_dimensions": []}],
        }
        normalized = normalize_question_repair_proposal(proposal, "q2")
        self.assertEqual(normalized["results"][0]["status"], "unresolved")
        self.assertEqual(normalized["results"][0]["candidates"], [])

    def test_read_only_inline_inspection_is_allowed_for_abstention(self) -> None:
        events = [{
            "event": {
                "type": "item.completed",
                "item": {"type": "command_execution", "command": "python -c 'print(1)'"},
            }
        }]
        # No provenance means no answer-producing computation was declared.
        audit_repair_execution(events, [])

    def test_missing_primary_reconstruction_is_not_normalized_to_abstention(self) -> None:
        proposed = {'results': [result('q2', 'reconstructed')],
                    'repair_records': [{'question_id': 'q2', 'changed_dimensions': []}]}
        normalized = normalize_question_repair_proposal(proposed, 'q2', missing_primary=True)
        self.assertEqual(normalized['results'][0]['status'], 'resolved')
        # Execution/provenance still has to pass finalize_repair separately.

    def test_abstention_with_provenance_record_is_not_computation(self) -> None:
        events = [{'event': {'type': 'item.completed', 'item': {
            'type': 'command_execution', 'command': "python -c 'print(1)'"}}}]
        audit_repair_execution(events, [{'changed_dimension': None,
            'reran_analysis': False, 'computation_required': False, 'source_files': []}])
        with self.assertRaises(ValueError):
            audit_repair_execution(events, [{'changed_dimension': 'statistical_method',
                'reran_analysis': True, 'computation_required': True, 'source_files': []}])


if __name__ == "__main__":
    unittest.main()
