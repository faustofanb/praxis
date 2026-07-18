from __future__ import annotations

import tempfile
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from momlib import praxis  # noqa: E402


class PraxisCompatibilityTest(unittest.TestCase):
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
