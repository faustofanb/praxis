from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from praxislib import config as praxis_config  # noqa: E402
from praxislib import praxis  # noqa: E402
from praxislib.project_index import (  # noqa: E402
    PROJECTS_FILE,
    scan_project_candidates,
    write_project_index_config,
)


class ProjectIndexTest(unittest.TestCase):
    def test_load_config_prefers_root_project_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / ".praxis").mkdir()
            (root / ".praxis" / "projects.toml").write_text(
                """
version = 1

[projects.legacy]
path = "legacy"
kind = "legacy"
""",
                encoding="utf-8",
            )
            (root / PROJECTS_FILE).write_text(
                """
version = 1

[projects.app]
path = "app"
kind = "node"
""",
                encoding="utf-8",
            )

            with patch.object(praxis_config, "ROOT_DIR", root):
                loaded = praxis_config.load_config()

        self.assertEqual(list(loaded["projects"]), ["app"])
        self.assertEqual(loaded["_praxis"]["configSource"], PROJECTS_FILE)

    def test_scan_project_candidates_detects_common_project_types(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "api").mkdir()
            (root / "api" / "pom.xml").write_text("<project />\n", encoding="utf-8")
            (root / "web").mkdir()
            (root / "web" / "package.json").write_text('{"scripts":{"build":"vite build"}}\n', encoding="utf-8")
            (root / "notes").mkdir()
            (root / "notes" / "README.md").write_text("# Notes\n", encoding="utf-8")

            projects = scan_project_candidates(root)

        self.assertEqual([project["name"] for project in projects], ["api", "notes", "web"])
        self.assertEqual({project["name"]: project["kind"] for project in projects}, {
            "api": "java-maven",
            "notes": "docs",
            "web": "node-package",
        })
        self.assertEqual({project["name"]: project["path"] for project in projects}, {
            "api": "api",
            "notes": "notes",
            "web": "web",
        })
        self.assertFalse(any(tmp_dir in project["path"] for project in projects))

    def test_scan_project_candidates_detects_nested_monorepo_packages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "apps" / "web").mkdir(parents=True)
            (root / "apps" / "web" / "package.json").write_text('{"scripts":{"test":"vitest"}}\n', encoding="utf-8")
            (root / "packages" / "worker").mkdir(parents=True)
            (root / "packages" / "worker" / "pyproject.toml").write_text("[project]\nname = 'worker'\n", encoding="utf-8")
            (root / "services" / "api").mkdir(parents=True)
            (root / "services" / "api" / "pom.xml").write_text("<project />\n", encoding="utf-8")
            (root / "apps" / "web" / "node_modules" / "dep").mkdir(parents=True)
            (root / "apps" / "web" / "node_modules" / "dep" / "package.json").write_text("{}", encoding="utf-8")

            projects = scan_project_candidates(root)

        self.assertEqual([project["path"] for project in projects], ["apps/web", "packages/worker", "services/api"])
        self.assertEqual({project["path"]: project["kind"] for project in projects}, {
            "apps/web": "node-package",
            "packages/worker": "python-package",
            "services/api": "java-maven",
        })

    def test_write_project_index_config_uses_root_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "api").mkdir()
            (root / "api" / "pom.xml").write_text("<project />\n", encoding="utf-8")

            output = write_project_index_config(root, force=True)
            text = output.read_text(encoding="utf-8")

            self.assertEqual(output, root / PROJECTS_FILE)
            self.assertIn("[projects.api]", text)
            self.assertIn('path = "api"', text)
            self.assertNotIn(".praxis/projects.toml", text)

    def test_praxis_index_records_root_config_and_extensions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / ".praxis" / "extensions" / "demo").mkdir(parents=True)
            (root / ".praxis" / "extensions" / "demo" / "extension.toml").write_text(
                """
schema_version = 1
id = "demo"
name = "Demo Extension"
""",
                encoding="utf-8",
            )
            (root / ".praxis" / "profile.toml").write_text(
                """
schema_version = 1
name = "Praxis"
status = "complete"
baseline = "portable"

[control_plane]
primary_command = "task"
command_groups = ["req", "project", "context", "gate", "delivery", "system"]
""",
                encoding="utf-8",
            )
            (root / PROJECTS_FILE).write_text(
                """
version = 1

[projects.docs]
path = "docs"
kind = "docs"
""",
                encoding="utf-8",
            )
            (root / "docs").mkdir()

            with (
                patch.object(praxis, "ROOT_DIR", root),
                patch.object(praxis, "PRAXIS_PROFILE", root / ".praxis" / "profile.toml"),
                patch.object(praxis, "PRAXIS_DIR", root / ".praxis" / "out"),
                patch.object(praxis, "PRAXIS_INDEX_FILE", root / ".praxis" / "out" / "project-index.json"),
                patch.object(praxis_config, "ROOT_DIR", root),
            ):
                path = praxis.praxis_index(scan=True)
                data = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(data["projectIndex"]["configSource"], PROJECTS_FILE)
        self.assertEqual(data["extensions"], [{"id": "demo", "name": "Demo Extension", "path": ".praxis/extensions/demo"}])
        self.assertIn("docs", data["projects"])
        self.assertEqual(data["projectIndex"]["root"], ".")
        self.assertNotIn(str(root), json.dumps(data, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
