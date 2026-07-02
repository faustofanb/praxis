from __future__ import annotations

import json
import tempfile
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from momlib import praxis  # noqa: E402


class PraxisCompatibilityTest(unittest.TestCase):
    def test_praxis_profile_falls_back_without_profile_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = {
                "projects": {"backend": {"path": str(root / "ifc-mom-column-max"), "defaultBranch": "local"}}
            }
            req_dir = root / "docs" / "02-req" / "2026-06" / "example"
            req_dir.mkdir(parents=True)
            requirement = "example"

            with (
                patch.object(praxis, "ROOT_DIR", root),
                patch.object(praxis, "PRAXIS_PROFILE", root / ".praxis" / "profile.toml"),
                patch.object(
                    praxis,
                    "PRAXIS_DIR",
                    root / ".praxis" / "out",
                ),
                patch.object(
                    praxis,
                    "PRAXIS_CONTEXT_DIR",
                    root / ".praxis" / "out" / "context",
                ),
                patch.object(
                    praxis,
                    "PRAXIS_VERDICT_DIR",
                    root / ".praxis" / "out" / "verdicts",
                ),
                patch.object(
                    praxis,
                    "PRAXIS_READINESS_DIR",
                    root / ".praxis" / "out" / "readiness",
                ),
                patch.object(
                    praxis,
                    "PRAXIS_HANDOFF_DIR",
                    root / ".praxis" / "out" / "handoffs",
                ),
                patch.object(
                    praxis,
                    "PRAXIS_LOCK_DIR",
                    root / ".praxis" / "out" / "locks",
                ),
                patch.object(
                    praxis,
                    "PRAXIS_INDEX_FILE",
                    root / ".praxis" / "out" / "project-index.json",
                ),
                patch.object(
                    praxis,
                    "PRAXIS_PROPOSALS_FILE",
                    root / ".praxis" / "out" / "evolution-proposals.json",
                ),
                patch.object(
                    praxis,
                    "PRAXIS_RUNTIME_FILE",
                    root / ".praxis" / "out" / "runtime-evaluation.json",
                ),
                patch.object(praxis, "find_requirement_dir", return_value=req_dir),
            ):
                packet_path = praxis.praxis_context_packet(config, "backend", requirement)
                packet = json.loads(packet_path.read_text(encoding="utf-8"))
                self.assertEqual(packet["controlPlane"]["primaryCommand"], "task")
                self.assertEqual(packet["project"], "backend")
                self.assertEqual(packet["requirementName"], requirement)
                self.assertEqual(packet["facts"]["requirementDir"], "docs/02-req/2026-06/example")
                self.assertNotIn(str(root), json.dumps(packet, ensure_ascii=False))


    def test_praxis_profile_strict_still_fails_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            with (
                patch.object(praxis, "ROOT_DIR", root),
                patch.object(praxis, "PRAXIS_PROFILE", root / ".praxis" / "profile.toml"),
            ):
                with self.assertRaises(FileNotFoundError):
                    _ = praxis.praxis_profile(strict=True)

    def test_workflow_command_contract_flags_missing_separator_and_unknown_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            praxis_dir = root / ".praxis"
            praxis_dir.mkdir()
            (root / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
            (root / ".rule").mkdir()
            (root / ".skill").mkdir()
            (praxis_dir / "commands.toml").write_text(
                """
schema_version = 1

[[command]]
id = "project.verify"
argv = "task project verify backend 需求名"
""",
                encoding="utf-8",
            )
            (praxis_dir / "manifest.toml").write_text(
                """
schema_version = 1

[task.backend]
commands = ["project.verify", "project.classify"]
rules = ["AGENTS.md", ".rule/missing.md"]
skills = [".skill/missing/SKILL.md"]
""",
                encoding="utf-8",
            )
            (praxis_dir / "methodology.toml").write_text("schema_version = 1\n", encoding="utf-8")

            with patch.object(praxis, "ROOT_DIR", root):
                errors = praxis._workflow_command_contract_errors()

        self.assertTrue(any("missing go-task -- separator" in error for error in errors))
        self.assertTrue(any("project.classify" in error for error in errors))
        self.assertTrue(any(".rule/missing.md" in error for error in errors))
        self.assertTrue(any(".skill/missing/SKILL.md" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
