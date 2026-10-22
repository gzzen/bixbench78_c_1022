# Path: conditions/c/c_minimal/test_pack_run_artifacts.py
# Purpose: `pack_run_artifacts.py` finds flat C run roots, packs C's layout and labels it feedback-assisted.
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts import pack_run_artifacts as pack

FILES = {
    "runs/exp_b/0000/bix-1__cap/capsule_result.json": "{}",
    "runs/exp_b/0000/bix-1__cap/analysis/scripts/b.py": "print('b')\n",
    "runs/exp_b/0000/bix-1__cap/data/raw.csv": "a\n",
    "runs/exp_b_c_blind/protocol.json": "{}",
    "runs/exp_b_c_blind/prompt_snapshot.json": "{}",
    "runs/exp_b_c_blind/code_snapshot/conditions/c/c_minimal/pipeline.py": "x = 1\n",
    "runs/exp_b_c_blind/frozen_parent_packets/q2/primary_canonical.json": "{}",
    "runs/exp_b_c_blind/frozen_parent_packets/q2/analysis/scripts/b.py": "print('b')\n",
    "runs/exp_b_c_blind/repair_questions/q2/bix-1__cap/repair_packet.json": "{}",
    "runs/exp_b_c_blind/repair_questions/q2/bix-1__cap/repair_result.json": "{}",
    "runs/exp_b_c_blind/repair_questions/q2/bix-1__cap/final_result.json": "{}",
    "runs/exp_b_c_blind/repair_questions/q2/bix-1__cap/analysis/semantic_audit.json": "{}",
    "runs/exp_b_c_blind/repair_questions/q2/bix-1__cap/data/raw.csv": "a\n",
    "runs/exp_b_c_blind/blind_contracts/q2/bix-1__cap/blind_contract.json": "{}",
    "runs/exp_b_c_blind/blind_contracts/q2/bix-1__cap/phase_freeze.json": "{}",
    "analysis/exp_b_generation.json": "{}",
    "analysis/exp_b_scoring.json": "{}",
    "analysis/exp_b_c_parent.json": "{}",
    "analysis/exp_b_c_blind_generation.json": "{}",
    "reports/EXP_B_C_BLIND_GENERATION.md": "#\n",
    "results/exp_b/b.jsonl": "{}\n",
    "results/exp_b/c_blind.jsonl": "{}\n",
    "logs/exp_b/c_blind.log": "log\n",
}


class PackRunArtifactsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for relative, content in FILES.items():
            (self.root / relative).parent.mkdir(parents=True, exist_ok=True)
            (self.root / relative).write_text(content)

    def tearDown(self):
        self.tmp.cleanup()

    def pack(self, experiment):
        with patch.object(sys, "argv", ["pack", experiment, "--root", str(self.root)]), \
                contextlib.redirect_stdout(io.StringIO()):
            pack.main()
        with zipfile.ZipFile(self.root / "out" / f"{experiment}.zip") as archive:
            return json.loads(archive.read(f"{experiment}/PACK_MANIFEST.json"))

    def test_c_run_is_found_packed_and_labelled(self):
        manifest = self.pack("exp")
        self.assertEqual(manifest["run_roots"], ["runs/exp_b", "runs/exp_b_c_blind"])
        files = {entry["path"]: entry for entry in manifest["files"]}
        expected = set(FILES) - {"runs/exp_b/0000/bix-1__cap/data/raw.csv",
                                 "runs/exp_b_c_blind/repair_questions/q2/bix-1__cap/data/raw.csv",
                                 "analysis/exp_b_scoring.json"}
        self.assertEqual(set(files), expected)
        self.assertEqual(manifest["excluded_answer_derived"], ["analysis/exp_b_scoring.json"])
        flagged = {path for path, entry in files.items() if entry.get("feedback_assisted")}
        self.assertEqual(flagged, {path for path in expected if "c_blind" in path.lower() or "c_parent" in path})
        self.assertFalse(manifest["answer_blind"])

    def test_b_only_archive_stays_answer_blind(self):
        for relative in [r for r in FILES if "c_blind" in r.lower() or "c_parent" in r]:
            (self.root / relative).unlink()
        manifest = self.pack("exp")
        self.assertTrue(manifest["answer_blind"])
        self.assertFalse(any(entry.get("feedback_assisted") for entry in manifest["files"]))

    def test_cleanup_checks_cover_c_run_root_records(self):
        roots = pack.run_roots(self.root, "exp_b_c_blind")
        names = {path.relative_to(self.root).as_posix() for path in pack.workspace_artifacts(roots)}
        self.assertIn("runs/exp_b_c_blind/protocol.json", names)
        self.assertIn("runs/exp_b_c_blind/code_snapshot/conditions/c/c_minimal/pipeline.py", names)
        self.assertIn("runs/exp_b_c_blind/blind_contracts/q2/bix-1__cap/phase_freeze.json", names)


if __name__ == "__main__":
    unittest.main()
