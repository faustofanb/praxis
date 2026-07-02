from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import call, patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import verify  # noqa: E402


class BackendVerifyPlanTest(unittest.TestCase):
    def test_sql_only_changes_skip_maven_compile(self) -> None:
        files = [
            "lamp-support/lamp-boot-server/src/main/resources/db/migration/mes/2026/05/V1__demo.sql",
            "../docs/02-req/2026-05/2026-05-12-demo/04-产出物/SQL/01-demo.sql",
        ]

        self.assertTrue(verify.is_sql_only_change(files))
        self.assertFalse(verify.backend_compile_files(files))

    def test_java_changes_still_require_compile_detection(self) -> None:
        files = ["lamp-mes/lamp-mes-controller/src/main/java/top/tangyh/Demo.java"]

        self.assertFalse(verify.is_sql_only_change(files))
        self.assertEqual(verify.backend_compile_files(files), files)

    def test_pda_source_changes_only_lint_changed_files_by_default(self) -> None:
        with (
            patch.object(
                verify,
                "classify_frontend",
                return_value={"fullCheck": False, "lintFiles": ["src/pages/demo/index.vue"], "packages": []},
            ),
            patch.object(verify, "run") as run,
            patch.dict(verify.os.environ, {}, clear=True),
        ):
            verify.verify_pnpm_uniapp(Path("/repo"), "pnpm-uniapp", ["src/pages/demo/index.vue"])

        run.assert_called_once_with(["pnpm", "exec", "eslint", "src/pages/demo/index.vue"], Path("/repo"))

    def test_web_source_changes_only_lint_changed_files_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_dir = Path(tmp_dir)
            (repo_dir / "package.json").write_text("{}", encoding="utf-8")
            (repo_dir / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")

            with (
                patch.object(
                    verify,
                    "classify_frontend",
                    return_value={
                        "fullCheck": False,
                        "lintFiles": ["apps/web-antd/src/views/demo/index.tsx"],
                        "packages": ["@vben/web-antd"],
                    },
                ),
                patch.object(verify, "run") as run,
                patch.dict(verify.os.environ, {}, clear=True),
            ):
                verify.verify_pnpm_web(repo_dir, "pnpm-web", ["apps/web-antd/src/views/demo/index.tsx"])

        run.assert_has_calls(
            [
                call(["pnpm", "install"], repo_dir),
                call(["pnpm", "exec", "eslint", "apps/web-antd/src/views/demo/index.tsx"], repo_dir),
            ]
        )
        self.assertNotIn(
            call(["pnpm", "-F", "@vben/web-antd", "run", "--if-present", "typecheck"], repo_dir),
            run.call_args_list,
        )

    def test_web_package_typecheck_requires_explicit_environment_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_dir = Path(tmp_dir)
            (repo_dir / "package.json").write_text("{}", encoding="utf-8")
            (repo_dir / "node_modules").mkdir()
            (repo_dir / "node_modules/.modules.yaml").write_text("layoutVersion: 5\n", encoding="utf-8")

            with (
                patch.object(
                    verify,
                    "classify_frontend",
                    return_value={
                        "fullCheck": False,
                        "lintFiles": ["apps/web-antd/src/views/demo/index.tsx"],
                        "packages": ["@vben/web-antd"],
                    },
                ),
                patch.object(verify, "run") as run,
                patch.dict(verify.os.environ, {"MOM_WEB_PACKAGE_TYPECHECK": "1"}, clear=True),
            ):
                verify.verify_pnpm_web(repo_dir, "pnpm-web", ["apps/web-antd/src/views/demo/index.tsx"])

        run.assert_has_calls(
            [
                call(["pnpm", "exec", "eslint", "apps/web-antd/src/views/demo/index.tsx"], repo_dir),
                call(["pnpm", "-F", "@vben/web-antd", "run", "--if-present", "typecheck"], repo_dir),
            ]
        )

    def test_web_config_changes_do_not_escalate_to_repository_check_or_full_eslint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_dir = Path(tmp_dir)
            (repo_dir / "package.json").write_text("{}", encoding="utf-8")
            (repo_dir / "node_modules").mkdir()
            (repo_dir / "node_modules/.modules.yaml").write_text("layoutVersion: 5\n", encoding="utf-8")

            with (
                patch.object(
                    verify,
                    "classify_frontend",
                    return_value={
                        "fullCheck": True,
                        "lintFiles": ["apps/web-antd/src/views/demo/index.tsx"],
                        "packages": ["@vben/web-antd"],
                    },
                ),
                patch.object(verify, "run") as run,
                patch.dict(verify.os.environ, {}, clear=True),
            ):
                verify.verify_pnpm_web(repo_dir, "pnpm-web", ["eslint.config.mjs", "apps/web-antd/src/views/demo/index.tsx"])

        calls = [item.args[0] for item in run.call_args_list]
        self.assertNotIn(["pnpm", "check"], calls)
        self.assertIn(["pnpm", "exec", "eslint", "apps/web-antd/src/views/demo/index.tsx"], calls)
        self.assertNotIn(["pnpm", "-F", "@vben/web-antd", "run", "--if-present", "typecheck"], calls)

    def test_web_dependency_manifest_change_runs_install_even_when_node_modules_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_dir = Path(tmp_dir)
            (repo_dir / "package.json").write_text("{}", encoding="utf-8")
            (repo_dir / "node_modules").mkdir()
            (repo_dir / "node_modules/.modules.yaml").write_text("layoutVersion: 5\n", encoding="utf-8")

            with (
                patch.object(
                    verify,
                    "classify_frontend",
                    return_value={"fullCheck": True, "lintFiles": [], "packages": []},
                ),
                patch.object(verify, "run") as run,
            ):
                verify.verify_pnpm_web(repo_dir, "pnpm-web", ["package.json", "pnpm-lock.yaml"])

        run.assert_called_once_with(["pnpm", "install"], repo_dir)

    def test_pda_full_typecheck_requires_explicit_environment_opt_in(self) -> None:
        with (
            patch.object(
                verify,
                "classify_frontend",
                return_value={"fullCheck": True, "lintFiles": ["src/pages/demo/index.vue"], "packages": []},
            ),
            patch.object(verify, "run") as run,
            patch.dict(verify.os.environ, {}, clear=True),
        ):
            verify.verify_pnpm_uniapp(Path("/repo"), "pnpm-uniapp", ["tsconfig.json", "src/pages/demo/index.vue"])

        run.assert_called_once_with(["pnpm", "exec", "eslint", "src/pages/demo/index.vue"], Path("/repo"))

        with (
            patch.object(
                verify,
                "classify_frontend",
                return_value={"fullCheck": True, "lintFiles": ["src/pages/demo/index.vue"], "packages": []},
            ),
            patch.object(verify, "run") as run,
            patch.dict(verify.os.environ, {"MOM_PDA_FULL_TYPECHECK": "1"}, clear=True),
        ):
            verify.verify_pnpm_uniapp(Path("/repo"), "pnpm-uniapp", ["tsconfig.json", "src/pages/demo/index.vue"])

        run.assert_has_calls(
            [call(["pnpm", "exec", "eslint", "src/pages/demo/index.vue"], Path("/repo")), call(["pnpm", "type-check"], Path("/repo"))]
        )

    def test_verification_evidence_markdown_lists_commands_and_unverified_items(self) -> None:
        text = verify.verification_evidence_markdown(
            project="backend",
            repo_dir=Path("/repo"),
            files=["lamp-mes/src/main/java/Demo.java"],
            commands=[["mvn", "compile"]],
            status="PASS",
        )

        self.assertIn("## 验证记录", text)
        self.assertIn("项目：backend", text)
        self.assertIn("目录：`/repo`", text)
        self.assertIn("`mvn compile`", text)
        self.assertIn("未验证项：无", text)


if __name__ == "__main__":
    unittest.main()
