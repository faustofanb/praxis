from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from praxislib import code_graph as code_graph_module  # noqa: E402
from praxislib.code_graph import build_code_graph, code_graph_check, query_code_graph  # noqa: E402
from praxislib.project_index import project_index_summary  # noqa: E402


class CodeGraphTest(unittest.TestCase):
    def test_build_code_graph_indexes_files_and_python_import_edges(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "praxis.projects.toml").write_text(
                'version = 1\n[projects.app]\npath = "app"\nkind = "python-package"\n',
                encoding="utf-8",
            )
            (root / "app").mkdir()
            (root / "app" / "main.py").write_text("import utils\nprint(utils.VALUE)\n", encoding="utf-8")
            (root / "app" / "utils.py").write_text("VALUE = 1\n", encoding="utf-8")

            graph_path = build_code_graph(root)
            graph = json.loads(graph_path.read_text(encoding="utf-8"))

        self.assertEqual(graph["schemaVersion"], 2)
        self.assertEqual(graph["summary"]["edgeCoverage"], "present")
        paths = {node["path"] for node in graph["nodes"]}
        self.assertIn("app/main.py", paths)
        self.assertIn("app/utils.py", paths)
        self.assertIn("praxis.projects.toml", paths)
        self.assertIn({"source": "app/main.py", "target": "app/utils.py", "kind": "python-import"}, graph["edges"])

    def test_query_code_graph_returns_ranked_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "app").mkdir()
            (root / "app" / "main.py").write_text("class Router:\n    pass\n", encoding="utf-8")
            graph_path = build_code_graph(root)

            result = query_code_graph(root, "Router")
            check_result = code_graph_check(root)

            self.assertEqual(result["query"], "Router")
            self.assertEqual(result["matches"][0]["path"], "app/main.py")
            self.assertEqual(check_result, 0)
            self.assertEqual(graph_path.name, "code-graph.json")

    def test_build_code_graph_indexes_typescript_and_java_edges(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "praxis.projects.toml").write_text(
                'version = 1\n[projects.web]\npath = "web"\nkind = "node-package"\n[projects.api]\npath = "api"\nkind = "java-maven"\n',
                encoding="utf-8",
            )
            (root / "web" / "src" / "lib").mkdir(parents=True)
            (root / "web" / "src" / "main.ts").write_text("import { helper } from './lib/helper';\nhelper();\n", encoding="utf-8")
            (root / "web" / "src" / "lib" / "helper.ts").write_text("export function helper() {}\n", encoding="utf-8")
            (root / "api" / "src" / "main" / "java" / "com" / "demo").mkdir(parents=True)
            (root / "api" / "src" / "main" / "java" / "com" / "demo" / "App.java").write_text(
                "package com.demo;\nimport com.demo.Helper;\nclass App { Helper helper; }\n",
                encoding="utf-8",
            )
            (root / "api" / "src" / "main" / "java" / "com" / "demo" / "Helper.java").write_text(
                "package com.demo;\nclass Helper {}\n",
                encoding="utf-8",
            )

            graph = json.loads(build_code_graph(root).read_text(encoding="utf-8"))

        self.assertIn({"source": "web/src/main.ts", "target": "web/src/lib/helper.ts", "kind": "typescript-import"}, graph["edges"])
        self.assertIn(
            {
                "source": "api/src/main/java/com/demo/App.java",
                "target": "api/src/main/java/com/demo/Helper.java",
                "kind": "java-import",
            },
            graph["edges"],
        )
        self.assertEqual(graph["summary"]["edgeCoverage"], "present")

    def test_build_code_graph_indexes_uniapp_vue_edges(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "praxis.projects.toml").write_text(
                'version = 1\n[projects.pda]\npath = "pda"\nkind = "uniapp"\n',
                encoding="utf-8",
            )
            (root / "pda" / "pages" / "work").mkdir(parents=True)
            (root / "pda" / "utils").mkdir(parents=True)
            (root / "pda" / "pages" / "work" / "index.vue").write_text(
                "<template><view>{{ title }}</view></template>\n"
                "<script setup lang=\"ts\">\n"
                "import { formatTitle } from '../../utils/format';\n"
                "const title = formatTitle('demo');\n"
                "</script>\n",
                encoding="utf-8",
            )
            (root / "pda" / "utils" / "format.ts").write_text(
                "export function formatTitle(value: string) { return value; }\n",
                encoding="utf-8",
            )

            graph = json.loads(build_code_graph(root).read_text(encoding="utf-8"))
            result = query_code_graph(root, "index")

        paths = {node["path"] for node in graph["nodes"]}
        self.assertIn("pda/pages/work/index.vue", paths)
        self.assertIn({"source": "pda/pages/work/index.vue", "target": "pda/utils/format.ts", "kind": "typescript-import"}, graph["edges"])
        self.assertEqual(result["matches"][0]["path"], "pda/pages/work/index.vue")

    def test_build_code_graph_resolves_tsconfig_path_alias_edges(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "praxis.projects.toml").write_text(
                'version = 1\n[projects.pda]\npath = "pda"\nkind = "uniapp"\n',
                encoding="utf-8",
            )
            (root / "pda" / "src" / "router").mkdir(parents=True)
            (root / "pda" / "src" / "store").mkdir(parents=True)
            (root / "pda" / "tsconfig.json").write_text(
                '{\n'
                '  // JSONC comments and Windows-style separators are accepted.\n'
                '  "compilerOptions": {"baseUrl": ".", "paths": {"@/*": [".\\\\src\\\\*"], "#/*": ["./src/*"]}},\n'
                '  "include": ["src/**/*.ts", "src/**/*.vue"]\n'
                '}\n',
                encoding="utf-8",
            )
            (root / "pda" / "src" / "router" / "index.ts").write_text(
                "import { useMenuStore } from '@/store/menu';\n"
                "const page = () => import('#/pages/home/index.vue');\n"
                "useMenuStore();\n",
                encoding="utf-8",
            )
            (root / "pda" / "src" / "store" / "menu.ts").write_text(
                "export function useMenuStore() { return {}; }\n",
                encoding="utf-8",
            )
            (root / "pda" / "src" / "pages" / "home").mkdir(parents=True)
            (root / "pda" / "src" / "pages" / "home" / "index.vue").write_text(
                "<template><view>home</view></template>\n",
                encoding="utf-8",
            )

            graph = json.loads(build_code_graph(root).read_text(encoding="utf-8"))

        self.assertIn(
            {"source": "pda/src/router/index.ts", "target": "pda/src/store/menu.ts", "kind": "typescript-import"},
            graph["edges"],
        )
        self.assertIn(
            {"source": "pda/src/router/index.ts", "target": "pda/src/pages/home/index.vue", "kind": "typescript-import"},
            graph["edges"],
        )

    def test_query_code_graph_finds_java_backend_class(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "praxis.projects.toml").write_text(
                'version = 1\n[projects.backend]\npath = "backend"\nkind = "java-maven"\n',
                encoding="utf-8",
            )
            (root / "backend" / "src" / "main" / "java" / "com" / "demo").mkdir(parents=True)
            (root / "backend" / "src" / "main" / "java" / "com" / "demo" / "MesTaskService.java").write_text(
                "package com.demo;\npublic class MesTaskService {}\n",
                encoding="utf-8",
            )
            build_code_graph(root)

            result = query_code_graph(root, "MesTaskService")

        self.assertEqual(result["matches"][0]["path"], "backend/src/main/java/com/demo/MesTaskService.java")

    def test_build_code_graph_indexes_java_same_package_reference_edges(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "praxis.projects.toml").write_text(
                'version = 1\n[projects.backend]\npath = "backend"\nkind = "java-maven"\n',
                encoding="utf-8",
            )
            package_root = root / "backend" / "src" / "main" / "java" / "com" / "demo"
            package_root.mkdir(parents=True)
            (package_root / "MesTaskService.java").write_text(
                "package com.demo;\npublic class MesTaskService { private MesTaskRepository repository; }\n",
                encoding="utf-8",
            )
            (package_root / "MesTaskRepository.java").write_text(
                "package com.demo;\npublic class MesTaskRepository {}\n",
                encoding="utf-8",
            )

            graph = json.loads(build_code_graph(root).read_text(encoding="utf-8"))

        self.assertIn(
            {
                "source": "backend/src/main/java/com/demo/MesTaskService.java",
                "target": "backend/src/main/java/com/demo/MesTaskRepository.java",
                "kind": "java-reference",
            },
            graph["edges"],
        )

    def test_code_graph_check_fails_when_graph_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "praxis.projects.toml").write_text(
                'version = 1\n[projects.app]\npath = "app"\nkind = "python-package"\n',
                encoding="utf-8",
            )
            (root / "app").mkdir()
            (root / "app" / "main.py").write_text("print('hello')\n", encoding="utf-8")

            with redirect_stdout(io.StringIO()) as output:
                exit_code = code_graph_check(root)
            graph_exists = (root / ".praxis" / "out" / "code-graph.json").exists()

        text = output.getvalue()
        self.assertEqual(exit_code, 1)
        self.assertIn("code graph is missing", text)
        self.assertFalse(graph_exists)

    def test_query_code_graph_builds_when_graph_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "app").mkdir()
            (root / "app" / "main.py").write_text("class Router:\n    pass\n", encoding="utf-8")

            result = query_code_graph(root, "Router")
            graph_exists = (root / ".praxis" / "out" / "code-graph.json").is_file()

        self.assertEqual(result["matches"][0]["path"], "app/main.py")
        self.assertTrue(graph_exists)

    def test_query_code_graph_uses_existing_graph_without_freshness_scan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "app").mkdir()
            (root / "app" / "main.py").write_text("class Router:\n    pass\n", encoding="utf-8")
            build_code_graph(root)

            with mock.patch("praxislib.code_graph._files", side_effect=AssertionError("unexpected freshness scan")):
                result = query_code_graph(root, "Router")

        self.assertEqual(result["matches"][0]["path"], "app/main.py")

    def test_code_graph_check_fails_for_invalid_or_unsupported_graph(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            graph_path = root / ".praxis" / "out" / "code-graph.json"
            graph_path.parent.mkdir(parents=True)
            graph_path.write_text("{not-json", encoding="utf-8")

            with redirect_stdout(io.StringIO()) as invalid_output:
                invalid_exit = code_graph_check(root)

            graph_path.write_text('{"schemaVersion": 1, "nodes": []}\n', encoding="utf-8")
            with redirect_stdout(io.StringIO()) as schema_output:
                schema_exit = code_graph_check(root)

        self.assertEqual(invalid_exit, 1)
        self.assertIn("invalid JSON", invalid_output.getvalue())
        self.assertEqual(schema_exit, 1)
        self.assertIn("schema version is unsupported", schema_output.getvalue())

    def test_code_graph_check_fails_when_graph_is_stale_or_missing_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "praxis.projects.toml").write_text(
                'version = 1\n[projects.app]\npath = "app"\nkind = "python-package"\n',
                encoding="utf-8",
            )
            (root / "app").mkdir()
            existing = root / "app" / "main.py"
            existing.write_text("print('old')\n", encoding="utf-8")
            graph_path = build_code_graph(root)
            newer = graph_path.stat().st_mtime + 5
            existing.write_text("print('new')\n", encoding="utf-8")
            os.utime(existing, (newer, newer))
            (root / "app" / "new_module.py").write_text("VALUE = 1\n", encoding="utf-8")

            with (
                mock.patch("praxislib.code_graph.schedule_code_graph_refresh", return_value=True, create=True) as refresh,
                redirect_stdout(io.StringIO()) as output,
            ):
                exit_code = code_graph_check(root)

        text = output.getvalue()
        self.assertEqual(exit_code, 1)
        self.assertIn("stale source file", text)
        self.assertIn("missing indexed file", text)
        self.assertIn("async refresh queued", text)
        refresh.assert_called_once_with(root)

    def test_schedule_code_graph_refresh_starts_one_detached_worker(self) -> None:
        schedule = getattr(code_graph_module, "schedule_code_graph_refresh", None)
        self.assertIsNotNone(schedule)
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            with mock.patch("praxislib.code_graph.subprocess.Popen") as popen:
                first = schedule(root)
                second = schedule(root)

            lock = root / ".praxis" / "out" / "code-graph-refresh.lock"
            lock_exists = lock.exists()

        self.assertTrue(first)
        self.assertFalse(second)
        self.assertTrue(lock_exists)
        self.assertEqual(popen.call_count, 1)
        self.assertTrue(popen.call_args.kwargs["start_new_session"])

    def test_refresh_code_graph_rebuilds_and_releases_lock(self) -> None:
        refresh = getattr(code_graph_module, "refresh_code_graph", None)
        self.assertIsNotNone(refresh)
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "app").mkdir()
            (root / "app" / "main.py").write_text("VALUE = 1\n", encoding="utf-8")
            lock = root / ".praxis" / "out" / "code-graph-refresh.lock"
            lock.parent.mkdir(parents=True)
            lock.touch()

            exit_code = refresh(root)

            graph_exists = (root / ".praxis" / "out" / "code-graph.json").is_file()
            lock_exists = lock.exists()

        self.assertEqual(exit_code, 0)
        self.assertTrue(graph_exists)
        self.assertFalse(lock_exists)

    def test_code_graph_check_detects_content_change_with_preserved_mtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "praxis.projects.toml").write_text(
                'version = 1\n[projects.app]\npath = "app"\nkind = "python-package"\n',
                encoding="utf-8",
            )
            (root / "app").mkdir()
            source = root / "app" / "main.py"
            source.write_text("VALUE = 'old'\n", encoding="utf-8")
            graph_path = build_code_graph(root)
            original_stat = source.stat()
            source.write_text("VALUE = 'new'\n", encoding="utf-8")
            os.utime(source, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
            os.utime(graph_path, (graph_path.stat().st_atime, graph_path.stat().st_mtime + 5))

            with (
                mock.patch("praxislib.code_graph.schedule_code_graph_refresh", return_value=True),
                redirect_stdout(io.StringIO()) as output,
            ):
                exit_code = code_graph_check(root)

        text = output.getvalue()
        self.assertEqual(exit_code, 1)
        self.assertIn("changed source file: app/main.py", text)

    def test_query_code_graph_prefers_source_filename_over_config_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "praxis.projects.toml").write_text(
                'version = 1\n[projects.app]\npath = "app"\nkind = "python-package"\n',
                encoding="utf-8",
            )
            (root / "app").mkdir()
            (root / "app" / "router.py").write_text("class Router:\n    pass\n", encoding="utf-8")
            (root / "app" / "router.md").write_text("# Router\n\nimplementation note\n", encoding="utf-8")
            build_code_graph(root)

            result = query_code_graph(root, "router")

        self.assertEqual(result["matches"][0]["path"], "app/router.py")
        self.assertGreater(result["matches"][0]["score"], result["matches"][-1]["score"])

    def test_build_code_graph_excludes_nested_dependency_and_build_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "praxis.projects.toml").write_text(
                'version = 1\n[projects.web]\npath = "web"\nkind = "node-package"\n',
                encoding="utf-8",
            )
            (root / "web" / "src").mkdir(parents=True)
            (root / "web" / "node_modules" / "pkg").mkdir(parents=True)
            (root / "web" / "dist" / "assets").mkdir(parents=True)
            (root / "web" / "src" / "main.ts").write_text("export const route = 'task';\n", encoding="utf-8")
            (root / "web" / "node_modules" / "pkg" / "index.js").write_text("const noisy = 'task';\n", encoding="utf-8")
            (root / "web" / "dist" / "assets" / "bundle.js").write_text("const noisy = 'task';\n", encoding="utf-8")

            graph_path = build_code_graph(root)
            graph = json.loads(graph_path.read_text(encoding="utf-8"))
            paths = {node["path"] for node in graph["nodes"]}

        self.assertIn("web/src/main.ts", paths)
        self.assertNotIn("web/node_modules/pkg/index.js", paths)
        self.assertNotIn("web/dist/assets/bundle.js", paths)

    def test_build_code_graph_excludes_tolaria_local_runtime_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "praxis.projects.toml").write_text(
                'version = 1\n[projects.docs]\npath = "docs"\nkind = "docs"\n',
                encoding="utf-8",
            )
            (root / "docs" / "notes").mkdir(parents=True)
            (root / "docs" / ".tolaria" / "cache").mkdir(parents=True)
            (root / "docs" / "notes" / "task.md").write_text("# task\n", encoding="utf-8")
            (root / "docs" / ".tolaria" / "cache" / "index.json").write_text('{"task": true}\n', encoding="utf-8")

            graph_path = build_code_graph(root)
            graph = json.loads(graph_path.read_text(encoding="utf-8"))
            paths = {node["path"] for node in graph["nodes"]}

        self.assertIn("docs/notes/task.md", paths)
        self.assertNotIn("docs/.tolaria/cache/index.json", paths)

    def test_build_code_graph_includes_praxis_control_plane_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "praxis.projects.toml").write_text(
                'version = 1\n[projects.app]\npath = "app"\nkind = "python-package"\n',
                encoding="utf-8",
            )
            (root / "app").mkdir()
            (root / "app" / "main.py").write_text("print('app')\n", encoding="utf-8")
            (root / "scripts" / "codex" / "praxislib").mkdir(parents=True)
            (root / "scripts" / "codex" / "praxislib" / "code_graph.py").write_text("class PraxislibGraph: pass\n", encoding="utf-8")

            build_code_graph(root)
            result = query_code_graph(root, "praxislib")

        self.assertEqual(result["matches"][0]["path"], "scripts/codex/praxislib/code_graph.py")

    def test_project_index_summary_consumes_existing_code_graph(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "praxis.projects.toml").write_text(
                'version = 1\n[projects.app]\npath = "app"\nkind = "python-package"\n',
                encoding="utf-8",
            )
            (root / "app").mkdir()
            (root / "app" / "main.py").write_text("print('hello')\n", encoding="utf-8")
            build_code_graph(root)

            summary = project_index_summary(root)

        self.assertEqual(summary["codeGraph"]["path"], ".praxis/out/code-graph.json")
        self.assertEqual(summary["codeGraph"]["status"], "present")


if __name__ == "__main__":
    unittest.main()
