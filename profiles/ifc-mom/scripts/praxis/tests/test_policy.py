from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import task as task_module  # noqa: E402
from praxislib.policy import policy_report, write_policy_report  # noqa: E402


def run_git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


class PolicyTest(unittest.TestCase):
    def test_policy_action_returns_failure_status_from_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            report = Path(tmp_dir) / "policy-report.json"
            report.write_text('{"status":"FAIL"}\n', encoding="utf-8")
            with patch.object(task_module, "write_policy_report", return_value=report):
                exit_code = task_module.run_praxis_system_action("policy-check", [])

        self.assertEqual(exit_code, 1)

    def test_policy_report_passes_for_clean_portable_core(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / ".praxis").mkdir()
            (root / "praxis.projects.toml").write_text("version = 1\n[projects.docs]\npath = \"docs\"\nkind = \"docs\"\n", encoding="utf-8")
            (root / ".codex").mkdir()
            (root / ".codex" / "config.toml").write_text("profile = \"codex\"\n", encoding="utf-8")
            (root / ".praxis" / "commands.toml").write_text(
                """
schema_version = 1

[[command]]
id = "project.cleanup"
risk = "destructive"
requires_confirmation = true
""",
                encoding="utf-8",
            )

            report = policy_report(root)

        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["summary"]["failed"], 0)

    def test_policy_report_ignores_untracked_local_platform_runtime_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            run_git(root, "init")
            (root / ".praxis").mkdir()
            (root / ".opencode").mkdir()
            (root / ".worktrees" / "example").mkdir(parents=True)
            (root / "praxis.projects.toml").write_text("version = 1\n[projects.docs]\npath = \"docs\"\nkind = \"docs\"\n", encoding="utf-8")

            report = policy_report(root)

        self.assertEqual(report["status"], "PASS")

    def test_policy_report_flags_tracked_core_platform_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            run_git(root, "init")
            (root / ".github" / "workflows").mkdir(parents=True)
            (root / ".github" / "workflows" / "ci.yml").write_text("name: ci\n", encoding="utf-8")
            (root / ".praxis").mkdir()
            (root / "praxis.projects.toml").write_text("version = 1\n[projects.docs]\npath = \"docs\"\nkind = \"docs\"\n", encoding="utf-8")
            run_git(root, "add", ".github/workflows/ci.yml")

            report = policy_report(root)

        self.assertEqual(report["status"], "FAIL")
        messages = "\n".join(item["message"] for item in report["checks"] if item["status"] == "FAIL")
        self.assertIn(".github must be generated from a platform template", messages)

    def test_policy_report_flags_core_platform_dirs_and_unconfirmed_destructive_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / ".github").mkdir()
            (root / ".codex" / "agent-contracts").mkdir(parents=True)
            (root / ".praxis").mkdir()
            (root / ".praxis" / "commands.toml").write_text(
                """
schema_version = 1

[[command]]
id = "bad.cleanup"
risk = "destructive"
requires_confirmation = false
""",
                encoding="utf-8",
            )

            report_path = write_policy_report(root)
            report = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(report["status"], "FAIL")
        messages = "\n".join(item["message"] for item in report["checks"] if item["status"] == "FAIL")
        self.assertIn(".github must be generated from a platform template", messages)
        self.assertIn(".codex/agent-contracts must move to .praxis/contracts/agents", messages)
        self.assertIn("bad.cleanup destructive commands require confirmation", messages)

if __name__ == "__main__":
    unittest.main()
