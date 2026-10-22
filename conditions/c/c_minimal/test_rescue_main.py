# Path: conditions/c/c_minimal/test_rescue_main.py
# Purpose: End-to-end CLI over a fake frozen B parent: preflight makes no calls; execute snapshots the lineage and freezes.
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from conditions.c.c_minimal import parent, rescue_main
from conditions.c.c_minimal.pipeline import MinimalRepair
from conditions.c.c_minimal.test_support import FakeAgent, offline, proposal, repair_step, result

ROOT = rescue_main.ROOT
QIDS = ["bix-1-q1", "bix-1-q2"]
ROWS = [{"question_id": q, "short_id": "bix-1", "capsule_uuid": "cap-1", "question": q} for q in QIDS]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RescueMainTests(unittest.TestCase):
    def setUp(self):
        # Freeze manifests use ROOT-relative paths, so the fixture lives under the git-ignored runs/.
        self.created_runs = not (ROOT / "runs").exists()
        (ROOT / "runs").mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT / "runs", prefix="c_test_")
        self.base = Path(self.tmp.name)
        workspace = self.base / "b/0000/bix-1__cap-1"
        (workspace / "analysis/scripts").mkdir(parents=True)
        (workspace / "capsule_result.json").write_text(json.dumps({
            "capsule_uuid": "cap-1", "short_id": "bix-1", "workflow_summary": "B",
            "results": [result("bix-1-q1", "kept"), result("bix-1-q2", "old")]}))
        (workspace / "analysis/grounding.json").write_text(json.dumps({"capsule_uuid": "cap-1", "questions": []}))
        (workspace / "analysis/scripts/b.py").write_text("print('b')\n")
        artifacts = [{"path": str(p.relative_to(ROOT)), "sha256": sha(p)}
                     for p in (workspace / "capsule_result.json", workspace / "analysis/scripts/b.py")]
        self.generation = self.base / "tag_b_generation.json"
        self.generation.write_text(json.dumps({
            "manifest": {"model": "deepseek/deepseek-flash", "reasoning_effort": "high"},
            "episodes": [{"short_id": "bix-1", "capsule_uuid": "cap-1", "question_ids": QIDS,
                          "workspace": str(workspace), "accepted": True}],
            "freeze": {"status": "frozen_before_private_scoring", "manifest_sha256": "m", "artifacts": artifacts}}))
        self.scoring = self.base / "tag_b_scoring.json"
        self.scoring.write_text(json.dumps({"status": "completed_posthoc_after_freeze", "verdicts": [
            {"question_id": "bix-1-q1", "correct": True, "accepted": True, "resolved": True},
            {"question_id": "bix-1-q2", "correct": False, "accepted": True, "resolved": True}]}))

    def tearDown(self):
        self.tmp.cleanup()
        if self.created_runs and not any((ROOT / "runs").iterdir()):
            (ROOT / "runs").rmdir()

    def run_main(self, *extra, agent=None, condition=None):
        argv = ["runner.py", "--parent-generation", str(self.generation), "--parent-scoring", str(self.scoring),
                "--parent-registry", str(self.base / "registry.json"), "--run-root", str(self.base / "c_run"),
                "--output", str(self.base / "c_generation.json"), "--report", str(self.base / "C.md"), *extra]
        stdout = io.StringIO()
        with patch.object(sys, "argv", argv), patch.object(parent, "load_rows", lambda: [dict(r) for r in ROWS]), \
                patch.object(parent, "public_question", dict), offline(agent or FakeAgent([])), \
                contextlib.redirect_stdout(stdout):
            rescue_main.main(condition or MinimalRepair())
        return json.loads(stdout.getvalue())

    def test_preflight_makes_no_agent_calls_and_inherits_parent_model(self):
        agent = FakeAgent([])
        summary = self.run_main(agent=agent)
        self.assertEqual(agent.calls, [])
        self.assertEqual((summary["locked_b3_yes"], summary["c_rescue_targets"]), (1, 1))
        self.assertEqual((summary["model"], summary["reasoning_effort"]), ("deepseek/deepseek-flash", "high"))
        self.assertFalse((self.base / "c_run").exists())

    def test_default_run_root_sits_directly_under_runs(self):
        argv = ["runner.py", "--parent-generation", str(self.generation), "--parent-scoring", str(self.scoring),
                "--parent-registry", str(self.base / "registry.json")]
        stdout = io.StringIO()
        with patch.object(sys, "argv", argv), contextlib.redirect_stdout(stdout):
            rescue_main.main(MinimalRepair())
        self.assertEqual(json.loads(stdout.getvalue())["run_root"], str(ROOT / "runs/tag_b_c_minimal"))

    def test_execute_freezes_protocol_snapshot_and_rescue(self):
        summary = self.run_main("--execute", agent=FakeAgent([repair_step(proposal())]))
        self.assertEqual((summary["c_rescue_targets"], summary["c_rescue_success"], summary["total_agent_calls"]), (1, 1, 1))
        output = json.loads((self.base / "c_generation.json").read_text())
        self.assertEqual(output["freeze"]["status"], "frozen_before_private_scoring")
        self.assertEqual(output["experiment_revision"], "C-v6 minimal evidence-backed repair full rescue")
        self.assertEqual(output["locked_b3_success_question_ids"], ["bix-1-q1"])
        protocol = json.loads((self.base / "c_run/protocol.json").read_text())
        self.assertEqual((protocol["lineage"], protocol["policy_retry"]), (["c_minimal"], False))
        paths = {entry["path"] for entry in protocol["sources"]}
        self.assertIn("conditions/c/c_minimal/pipeline.py", paths)
        self.assertIn("common/integrity/opencode_capture.py", paths)
        self.assertFalse(any(Path(p).name.startswith("test_") for p in paths))
        self.assertTrue((self.base / "c_run/code_snapshot/conditions/c/c_minimal/pipeline.py").is_file())
        for artifact in output["freeze"]["artifacts"]:
            self.assertEqual(sha(ROOT / artifact["path"]), artifact["sha256"])

    def test_execute_refuses_existing_output_or_nonempty_run_root(self):
        (self.base / "c_generation.json").write_text("{}")
        with self.assertRaises(SystemExit):
            self.run_main("--execute")
        (self.base / "c_generation.json").unlink()
        (self.base / "c_run").mkdir()
        (self.base / "c_run/old").write_text("x")
        with self.assertRaises(SystemExit):
            self.run_main("--execute")


if __name__ == "__main__":
    unittest.main()
