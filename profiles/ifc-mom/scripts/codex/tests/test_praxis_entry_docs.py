from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def tracked_files(*paths: str) -> list[Path]:
    completed = subprocess.run(
        ["git", "ls-files", "--", *paths],
        cwd=ROOT,
        text=True,
        check=True,
        stdout=subprocess.PIPE,
    )
    return [path for line in completed.stdout.splitlines() if line and (path := ROOT / line).exists()]


def assert_text_has_no_absolute_workspace_paths(testcase: unittest.TestCase, path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    testcase.assertNotIn("/Users/fausto", text)
    testcase.assertNotIn("/private/var", text)


class PraxisEntryDocsTest(unittest.TestCase):
    def test_readme_is_generic_praxis_entry(self) -> None:
        text = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("# Praxis", text)
        self.assertIn("not first-turn-only", text)
        self.assertIn("turn contract", text)
        self.assertIn("latest user request", text)
        for forbidden in ["IFC MOM Workspace Guide", "Codex 使用方式", "PDA", "MagicAPI", "ETL", "大屏", "制造业"]:
            self.assertNotIn(forbidden, text)

    def test_agents_is_thin_agent_entry(self) -> None:
        text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")

        self.assertIn("# AGENTS.md", text)
        self.assertIn("praxis.toml", text)
        self.assertIn("praxis.projects.toml", text)
        self.assertIn(".praxis/contracts/agents/turn.schema.json", text)
        self.assertIn("Every Turn Contract", text)
        self.assertIn("latest user request", text)
        self.assertIn("newest request", text)
        for forbidden in ["后端", "PDA", "MagicAPI", "报表", "大屏", "ifc-mom-column-max"]:
            self.assertNotIn(forbidden, text)

    def test_turn_contract_is_machine_readable(self) -> None:
        path = ROOT / ".praxis/contracts/agents/turn.schema.json"
        payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(payload["role"], "praxis-turn-contract")
        self.assertIn("latestUserMessage", payload["input_required"])
        self.assertIn("bind_to_latest_user_message", payload["turn_start_checks"])
        self.assertIn("reuse_stale_first_turn_context", payload["forbidden"])

    def test_codex_config_has_no_workspace_absolute_paths(self) -> None:
        for path in tracked_files(".codex"):
            assert_text_has_no_absolute_workspace_paths(self, path)

    def test_extension_metadata_has_no_workspace_absolute_paths(self) -> None:
        for path in tracked_files(".praxis/extensions"):
            if path.suffix in {".toml", ".md"}:
                assert_text_has_no_absolute_workspace_paths(self, path)

    def test_legacy_graph_provider_is_removed_from_tracked_sources(self) -> None:
        forbidden = "Graph" + "ify"
        forbidden_lower = forbidden.lower()
        for path in tracked_files(".praxis", "README.md", "AGENTS.md", "scripts/codex"):
            if path.suffix.lower() not in {".md", ".py", ".toml", ".tpl", ".yml", ".yaml"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            self.assertNotIn(forbidden, text, msg=str(path))
            self.assertNotIn(forbidden_lower, text.lower(), msg=str(path))

    def test_extension_docs_use_packaged_rule_and_skill_paths(self) -> None:
        extension_root = ROOT / ".praxis" / "extensions" / "ifc-mom"
        for path in extension_root.rglob("*.md"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn(".rule/", text, msg=str(path))
            self.assertNotIn(".skill/", text, msg=str(path))
            self.assertNotIn(".praxis/projects.toml", text, msg=str(path))


if __name__ == "__main__":
    unittest.main()
