from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from momlib.praxis_profile import write_praxis_profile_report  # noqa: E402


class PraxisProfileTest(unittest.TestCase):
    def test_write_praxis_profile_report_validates_core_and_project_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            praxis_dir = root / ".praxis"
            praxis_dir.mkdir()
            (root / ".rule" / "global").mkdir(parents=True)
            (root / ".rule" / "global" / "00-工作流精简索引.md").write_text("# index\n", encoding="utf-8")
            (root / ".skill" / "global" / "mom-context-budgeting").mkdir(parents=True)
            (root / ".skill" / "global" / "mom-context-budgeting" / "SKILL.md").write_text("# skill\n", encoding="utf-8")
            (root / "docs" / "02-req").mkdir(parents=True)
            (root / "docs" / "03-etl").mkdir(parents=True)
            (praxis_dir / "requirements").mkdir(parents=True)

            (praxis_dir / "commands.toml").write_text(
                """
schema_version = 1

[[command]]
id = "context.brief"
argv = "task context -- --brief <project> <requirement>"

[[command]]
id = "project.verify"
argv = "task project -- verify <project> <requirement>"

[[command]]
id = "project.readiness"
argv = "task gate -- ready <project> <requirement>"
""",
                encoding="utf-8",
            )
            (praxis_dir / "projects.toml").write_text(
                """
version = 1

[projects.backend]
path = "ifc-mom-column-max"
kind = "java-maven"
defaultBranch = "local"
upstreamBranch = "develop"

[projects.web]
path = "ifc-web-mom-max"
kind = "pnpm-web"
defaultBranch = "local"
upstreamBranch = "develop"
""",
                encoding="utf-8",
            )
            (praxis_dir / "core.toml").write_text(
                """
schema_version = 1

[platform]
name = "praxis-platform"
primary_command = "task"

[portability]
path_style = "posix-relative"
windows_supported = true

[[stage]]
id = "context"
commands = ["context.brief"]
portable = true

[[stage]]
id = "verification"
commands = ["project.verify"]
portable = true

[[stage]]
id = "closeout"
commands = ["project.readiness"]
portable = true

[[tool_candidate]]
id = "dagger"
phase = "pilot"
official_url = "https://docs.dagger.io/"

[risk_lane.low]
commands = ["context.brief"]
""",
                encoding="utf-8",
            )
            (praxis_dir / "project-adapter.toml").write_text(
                """
schema_version = 1

[adapter]
workspace = "ifc-mom"
shared_core = ".praxis/core.toml"

[paths]
business_requirements = "docs/02-req"
process_requirements = ".praxis/requirements"
etl_assets = "docs/03-etl"

[project_kinds.java-maven]
verification = "maven-module-compile"

[project_kinds.pnpm-web]
verification = "changed-source-lint-with-opt-in-package-typecheck"

rule_paths = [".rule/global/00-工作流精简索引.md"]
skill_paths = [".skill/global/mom-context-budgeting/SKILL.md"]
""",
                encoding="utf-8",
            )

            report_path = write_praxis_profile_report(root)

            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["core"]["path"], ".praxis/core.toml")
            self.assertEqual(report["adapter"]["path"], ".praxis/project-adapter.toml")
            self.assertEqual(report["adapter"]["workspace"], "ifc-mom")
            self.assertEqual(report["portableStages"], ["closeout", "context", "verification"])
            self.assertEqual(report["projectKinds"], ["java-maven", "pnpm-web"])
            self.assertEqual(report["toolCandidates"], ["dagger"])
            self.assertEqual(report_path, root / ".praxis" / "out" / "profile.json")

    def test_write_praxis_profile_report_allows_configured_external_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            praxis_dir = root / ".praxis"
            praxis_dir.mkdir()
            (praxis_dir / "requirements").mkdir(parents=True)
            (praxis_dir / "commands.toml").write_text(
                """
schema_version = 1

[[command]]
id = "context.brief"
argv = "task context -- --brief <project> <requirement>"
""",
                encoding="utf-8",
            )
            (praxis_dir / "projects.toml").write_text(
                """
version = 1

[projects.docs]
path = "docs"
kind = "docs"
defaultBranch = "main"
upstreamBranch = "main"
""",
                encoding="utf-8",
            )
            (praxis_dir / "core.toml").write_text(
                """
schema_version = 1

[platform]
primary_command = "task"

[portability]
path_style = "posix-relative"
windows_supported = true

[[stage]]
id = "context"
commands = ["context.brief"]
portable = true

[[tool_candidate]]
id = "dagger"
official_url = "https://docs.dagger.io/"
""",
                encoding="utf-8",
            )
            (praxis_dir / "project-adapter.toml").write_text(
                """
schema_version = 1

[adapter]
workspace = "ifc-mom"
shared_core = ".praxis/core.toml"

[paths]
business_requirements = "docs/02-req"
process_requirements = ".praxis/requirements"

[path_policy]
optional_external = ["business_requirements"]

[project_kinds.docs]
verification = "manual-doc-review-and-contract-check"
""",
                encoding="utf-8",
            )

            report_path = write_praxis_profile_report(root)

            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["issues"], [])


if __name__ == "__main__":
    unittest.main()
