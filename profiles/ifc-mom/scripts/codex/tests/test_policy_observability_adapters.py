from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from praxislib.adapters import adapter_plan, write_adapter_plan  # noqa: E402
from praxislib.observability import write_trace_span, write_trace_summary  # noqa: E402
from praxislib.policy import policy_report, write_policy_report  # noqa: E402


def run_git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


class PolicyObservabilityAdaptersTest(unittest.TestCase):
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

    def test_adapter_plan_keeps_optional_tools_optional(self) -> None:
        plan = adapter_plan()

        tools = {tool["id"]: tool for tool in plan["tools"]}
        for tool_id in ["dagger", "nx", "opa", "conftest", "semgrep", "codeql", "renovate", "mvnd"]:
            self.assertIn(tool_id, tools)
            self.assertFalse(tools[tool_id]["required"])
            self.assertTrue(tools[tool_id]["officialUrl"].startswith("https://"))
        self.assertEqual(tools["codeql"]["templatePath"], ".praxis/adapters/quality/codeql-action.yml.tpl")

    def test_write_adapter_plan_persists_machine_readable_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = write_adapter_plan(Path(tmp_dir))
            report = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(report["schemaVersion"], 1)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(path.name, "adapter-plan.json")

    def test_trace_span_and_summary_include_otlp_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            with patch.dict(os.environ, {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://collector:4318"}, clear=False):
                span_path = write_trace_span(root, command="task system -- check", status="PASS", attributes={"stage": "test"})
                summary_path = write_trace_summary(root)

            spans = [json.loads(line) for line in span_path.read_text(encoding="utf-8").splitlines()]
            summary = json.loads(summary_path.read_text(encoding="utf-8"))

        self.assertEqual(spans[0]["command"], "task system -- check")
        self.assertEqual(spans[0]["status"], "PASS")
        self.assertIn("traceId", spans[0])
        self.assertEqual(summary["otlp"]["endpoint"], "http://collector:4318")
        self.assertEqual(summary["summary"]["spanCount"], 1)
        self.assertEqual(summary["summary"]["traceLog"], ".praxis/out/traces/praxis-trace.jsonl")
        self.assertNotIn(str(root), json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
