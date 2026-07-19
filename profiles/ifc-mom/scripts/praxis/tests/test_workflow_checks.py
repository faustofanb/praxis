from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from momlib.docs import doc_init  # noqa: E402
from momlib.workflow_checks import (  # noqa: E402
    change_check,
    classify_changed_file,
    db_plan,
    docs_check,
    docs_index,
    guard_check,
    migration_check,
    preflight,
    write_execution_compliance_evidence,
)


class WorkflowChecksTest(unittest.TestCase):
    def config(self, tmp_dir: str) -> dict:
        return {
            "projects": {
                "docs": {"path": str(Path(tmp_dir) / "docs")},
                "backend": {
                    "path": "ifc-mom-column-max",
                    "defaultBranch": "local",
                },
            }
        }

    def test_docs_check_flags_template_analysis_and_stale_readme(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self.config(tmp_dir)
            doc_init(config, "空泛分析", "用户要求：这是完整保留的原始需求描述。")

            with redirect_stdout(io.StringIO()) as output:
                exit_code = docs_check(config, "空泛分析")

        text = output.getvalue()
        self.assertEqual(exit_code, 1)
        self.assertIn("analysis document still contains template placeholder", text)
        self.assertIn("README latest conclusion is still placeholder", text)

    def test_execution_compliance_evidence_records_docs_placeholders_before_closeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self.config(tmp_dir)
            doc_init(config, "收口证据", "用户要求：这是完整保留的原始需求描述。")
            output_dir = Path(tmp_dir) / "runtime-evidence"

            with redirect_stdout(io.StringIO()) as output:
                path = write_execution_compliance_evidence(config, "backend", "收口证据", output_dir=output_dir)

            data = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(data["schemaVersion"], 1)
        self.assertEqual(data["project"], "backend")
        self.assertEqual(data["requirementName"], "收口证据")
        self.assertEqual(data["status"], "FAIL")
        self.assertTrue(any("placeholder" in issue for issue in data["docsIssues"]))
        self.assertIn("Execution compliance evidence:", output.getvalue())

    def test_docs_check_accepts_evidence_analysis_and_indexed_readme(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self.config(tmp_dir)
            req_dir = doc_init(config, "证据分析", "用户要求：这是完整保留的原始需求描述。")
            analysis = req_dir / "01-需求分析拆解" / "01-2026-05-13-1000-证据化分析.md"
            analysis.write_text(
                """# 证据化分析

## 来源证据

- 源码路径：lamp-mes/demo/Demo.java
- 表字段：mes_demo.id, mes_demo.status
- 样例数据：status = FAIL 3 条

## 明确结论

已确认接口与表字段关系。

## 未决项

无。
""",
                encoding="utf-8",
            )
            (req_dir / "README.md").write_text(
                """# 证据分析

## 最新结论

- 需求分析：`01-需求分析拆解/01-2026-05-13-1000-证据化分析.md`
- 任务规划：待补充
- 开发进度：待补充
""",
                encoding="utf-8",
            )

            with redirect_stdout(io.StringIO()) as output:
                exit_code = docs_check(config, "证据分析")

        self.assertEqual(exit_code, 0)
        self.assertIn("Docs check passed", output.getvalue())

    def test_docs_check_flags_readme_missing_latest_stage_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self.config(tmp_dir)
            req_dir = doc_init(config, "索引过期", "用户要求：这是完整保留的原始需求描述。")
            old_analysis = req_dir / "01-需求分析拆解" / "01-2026-05-13-1000-旧分析.md"
            latest_analysis = req_dir / "01-需求分析拆解" / "02-2026-05-13-1100-新分析.md"
            for path in [old_analysis, latest_analysis]:
                path.write_text(
                    """# 证据化分析

## 来源证据

- 源码路径：Demo.java

## 明确结论

已确认。
""",
                    encoding="utf-8",
                )
            (req_dir / "README.md").write_text(
                f"""# 索引过期

## 最新结论

- 需求分析：`{old_analysis.relative_to(req_dir).as_posix()}`
""",
                encoding="utf-8",
            )

            with redirect_stdout(io.StringIO()) as output:
                exit_code = docs_check(config, "索引过期")

        self.assertEqual(exit_code, 1)
        self.assertIn("README does not reference latest stage file", output.getvalue())

    def test_docs_check_flags_attachment_mentions_without_saved_file_or_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self.config(tmp_dir)
            req_dir = doc_init(config, "截图需求", "用户要求：按截图调整页面字段。")
            analysis = req_dir / "01-需求分析拆解" / "01-2026-05-13-1000-证据化分析.md"
            analysis.write_text(
                """# 证据化分析

## 来源证据

- 源码路径：Demo.java

## 明确结论

已确认。
""",
                encoding="utf-8",
            )
            (req_dir / "README.md").write_text(
                f"""# 截图需求

## 最新结论

- 需求分析：`{analysis.relative_to(req_dir).as_posix()}`
""",
                encoding="utf-8",
            )

            with redirect_stdout(io.StringIO()) as output:
                exit_code = docs_check(config, "截图需求")

        self.assertEqual(exit_code, 1)
        self.assertIn("mentions attachments/screenshots", output.getvalue())

    def test_docs_check_accepts_attachment_missing_reason_in_raw_requirement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self.config(tmp_dir)
            req_dir = doc_init(config, "截图留档说明", "用户要求：按截图调整页面字段。附件未落盘原因：当前环境无法取得图片二进制，请用户补传本地路径。")
            analysis = req_dir / "01-需求分析拆解" / "01-2026-05-13-1000-证据化分析.md"
            analysis.write_text(
                """# 证据化分析

## 来源证据

- 源码路径：Demo.java

## 明确结论

已确认。
""",
                encoding="utf-8",
            )
            (req_dir / "README.md").write_text(
                f"""# 截图留档说明

## 最新结论

- 需求分析：`{analysis.relative_to(req_dir).as_posix()}`
""",
                encoding="utf-8",
            )

            with redirect_stdout(io.StringIO()) as output:
                exit_code = docs_check(config, "截图留档说明")

        self.assertEqual(exit_code, 0)
        self.assertIn("Docs check passed", output.getvalue())

    def test_migration_check_blocks_official_flyway_without_intermediate_sql(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self.config(tmp_dir)
            doc_init(config, "迁移流程", "用户要求：这是完整保留的原始需求描述。")

            with (
                patch("momlib.workflow_checks.action_repo_dir", return_value=Path(tmp_dir)),
                patch(
                    "momlib.workflow_checks.changed_files",
                    return_value=[
                        "lamp-support/lamp-boot-server/src/main/resources/db/migration/mes/2026/05/V1__demo.sql"
                    ],
                ),
                redirect_stdout(io.StringIO()) as output,
            ):
                exit_code = migration_check(config, "backend", "迁移流程")

        self.assertEqual(exit_code, 1)
        self.assertIn("official Flyway migration changed before intermediate SQL is present", output.getvalue())

    def test_migration_check_accepts_intermediate_sql_for_official_flyway_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self.config(tmp_dir)
            req_dir = doc_init(config, "迁移流程", "用户要求：这是完整保留的原始需求描述。")
            (req_dir / "04-产出物" / "SQL" / "01-迁移草案.sql").write_text("select 1;\n", encoding="utf-8")

            with (
                patch("momlib.workflow_checks.action_repo_dir", return_value=Path(tmp_dir)),
                patch(
                    "momlib.workflow_checks.changed_files",
                    return_value=[
                        "lamp-support/lamp-boot-server/src/main/resources/db/migration/mes/2026/05/V1__demo.sql"
                    ],
                ),
                redirect_stdout(io.StringIO()) as output,
            ):
                exit_code = migration_check(config, "backend", "迁移流程")

        self.assertEqual(exit_code, 0)
        self.assertIn("Migration check passed", output.getvalue())

    def test_preflight_keeps_process_only_requirement_out_of_database_risk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self.config(tmp_dir)
            req_dir = doc_init(
                config,
                "Praxis流程演示需求",
                "用户要求：完整演示项目索引构建、需求目录落地、工作树新建和 gate 流程，不涉及数据库、SQL 或迁移交付。",
            )
            analysis = req_dir / "01-需求分析拆解" / "01-2026-06-21-流程分析.md"
            analysis.write_text(
                """# 流程分析

## 来源证据

- 源码路径：scripts/praxis/task.py

## 明确结论

这是流程演示需求，只验证 Praxis 命令链路。
""",
                encoding="utf-8",
            )
            (req_dir / "README.md").write_text(
                f"""# Praxis流程演示需求

## 最新结论

- 需求分析：`{analysis.relative_to(req_dir).as_posix()}`
""",
                encoding="utf-8",
            )

            with (
                patch("momlib.workflow_checks.project_worktree_dirs", return_value=[Path(tmp_dir) / "worktree"]),
                redirect_stdout(io.StringIO()) as output,
            ):
                exit_code = preflight(config, "backend", "Praxis流程演示需求")

        text = output.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("database investigation: not indicated", text)
        self.assertIn("SQL/migration intermediate artifact: not indicated", text)

    def test_preflight_ignores_raw_requirement_template_sql_hint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self.config(tmp_dir)
            req_dir = doc_init(config, "全流程演示", "用户要求：测试一个全流程需求让我看看效果。")
            analysis = req_dir / "01-需求分析拆解" / "01-2026-06-21-流程分析.md"
            analysis.write_text(
                """# 流程分析

## 来源证据

- 源码路径：scripts/praxis/task.py

## 明确结论

这是流程演示需求。
""",
                encoding="utf-8",
            )
            (req_dir / "README.md").write_text(
                f"""# 全流程演示

## 最新结论

- 需求分析：`{analysis.relative_to(req_dir).as_posix()}`
""",
                encoding="utf-8",
            )

            with (
                patch("momlib.workflow_checks.project_worktree_dirs", return_value=[Path(tmp_dir) / "worktree"]),
                redirect_stdout(io.StringIO()) as output,
            ):
                exit_code = preflight(config, "backend", "全流程演示")

        text = output.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("database investigation: not indicated", text)
        self.assertIn("SQL/migration intermediate artifact: not indicated", text)

    def test_change_check_blocks_intermediate_sql_without_official_flyway_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self.config(tmp_dir)
            req_dir = doc_init(config, "迁移收尾", "用户要求：这是完整保留的原始需求描述。")
            analysis = req_dir / "01-需求分析拆解" / "01-2026-05-13-1000-证据化分析.md"
            analysis.write_text(
                """# 证据化分析

## 来源证据

- 源码路径：Demo.java

## 明确结论

已确认。
""",
                encoding="utf-8",
            )
            (req_dir / "README.md").write_text(
                f"""# 迁移收尾

## 最新结论

- 需求分析：`{analysis.relative_to(req_dir).as_posix()}`
""",
                encoding="utf-8",
            )
            (req_dir / "04-产出物" / "SQL" / "01-迁移草案.sql").write_text("select 1;\n", encoding="utf-8")

            with (
                patch("momlib.workflow_checks.action_repo_dir", return_value=Path(tmp_dir)),
                patch("momlib.workflow_checks.capture", return_value=""),
                patch("momlib.workflow_checks.delivery_commit_lines", return_value=["abc123 feat(mes): 迁移收尾"]),
                patch("momlib.workflow_checks.commit_changed_files", return_value=["lamp-mes/src/main/java/Demo.java"]),
                patch("momlib.workflow_checks.delivery_policy_issues", return_value=[]),
                redirect_stdout(io.StringIO()) as output,
            ):
                exit_code = change_check(config, "backend", "迁移收尾")

        self.assertEqual(exit_code, 1)
        self.assertIn("delivery has no official Flyway migration", output.getvalue())

    def test_guard_combines_docs_and_change_checks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self.config(tmp_dir)
            doc_init(config, "门禁检查", "用户要求：这是完整保留的原始需求描述。")

            with (
                patch("momlib.workflow_checks.action_repo_dir", return_value=Path(tmp_dir)),
                patch("momlib.workflow_checks.changed_files", return_value=[]),
                patch("momlib.workflow_checks.capture", return_value=""),
                redirect_stdout(io.StringIO()) as output,
            ):
                exit_code = guard_check(config, "backend", "门禁检查")

        text = output.getvalue()
        self.assertEqual(exit_code, 1)
        self.assertIn("analysis document still contains template placeholder", text)

    def test_docs_index_updates_latest_conclusions_and_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self.config(tmp_dir)
            req_dir = doc_init(config, "索引更新", "用户要求：这是完整保留的原始需求描述。")
            analysis = req_dir / "01-需求分析拆解" / "01-2026-05-13-1000-证据化分析.md"
            plan = req_dir / "02-任务规划" / "01-2026-05-13-1010-实施规划.md"
            progress = req_dir / "03-开发进度" / "01-2026-05-13-1020-开发进度.md"
            sql = req_dir / "04-产出物" / "SQL" / "01-2026-05-13-1030-迁移草案.sql"
            for path in [analysis, plan, progress, sql]:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("content\n", encoding="utf-8")

            with redirect_stdout(io.StringIO()) as output:
                exit_code = docs_index(config, "索引更新")

            readme = (req_dir / "README.md").read_text(encoding="utf-8")

        self.assertEqual(exit_code, 0)
        self.assertIn("Docs index updated", output.getvalue())
        self.assertIn("01-需求分析拆解/01-2026-05-13-1000-证据化分析.md", readme)
        self.assertIn("02-任务规划/01-2026-05-13-1010-实施规划.md", readme)
        self.assertIn("03-开发进度/01-2026-05-13-1020-开发进度.md", readme)
        self.assertIn("04-产出物/SQL/01-2026-05-13-1030-迁移草案.sql", readme)

    def test_db_plan_prints_database_investigation_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self.config(tmp_dir)
            config["database"] = {
                "local": {
                    "connection": "LOCAL",
                    "database": "aotu_dev_local",
                    "schema": "public",
                }
            }
            req_dir = doc_init(config, "数据库调查", "用户要求：这是完整保留的原始需求描述。")

            with redirect_stdout(io.StringIO()) as output:
                exit_code = db_plan(config, "数据库调查")

        text = output.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn(str(req_dir / "04-产出物" / "关联信息调查"), text)
        self.assertIn("表结构与字段注释", text)
        self.assertIn("样例数据", text)
        self.assertIn("数据分布", text)
        self.assertIn("只读 SQL 模板", text)
        self.assertIn("connection=LOCAL, database=aotu_dev_local, schema=public", text)
        self.assertIn("select current_database(), current_schema();", text)
        self.assertIn("table_catalog = 'aotu_dev_local'", text)
        self.assertIn("table_schema = 'public'", text)

    def test_preflight_reports_docs_worktree_and_data_risks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self.config(tmp_dir)
            req_dir = doc_init(config, "字段映射迁移", "需要调整 SQL 迁移和字段映射")
            analysis = req_dir / "01-需求分析拆解" / "01-2026-05-13-1000-证据化分析.md"
            analysis.write_text(
                """# 证据化分析

## 来源证据

- 表字段：demo.id

## 明确结论

已确认。
""",
                encoding="utf-8",
            )
            (req_dir / "README.md").write_text(
                f"""# 字段映射迁移

## 最新结论

- 需求分析：`{analysis.relative_to(req_dir).as_posix()}`
""",
                encoding="utf-8",
            )

            with (
                patch("momlib.workflow_checks.project_worktree_dirs", return_value=[Path(tmp_dir) / "worktree"]),
                redirect_stdout(io.StringIO()) as output,
            ):
                exit_code = preflight(config, "backend", "字段映射迁移")

        text = output.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("Preflight", text)
        self.assertIn("database investigation: required", text)
        self.assertIn("SQL/migration intermediate artifact: required", text)
        self.assertIn("Preflight docs index passed", text)

    def test_classify_changed_file_labels_workflow_risk_categories(self) -> None:
        cases = {
            "lamp-mes/src/test/java/DemoTest.java": "test",
            "lamp-mes/src/main/resources/db/migration/mes/V1__demo.sql": "migration",
            "lamp-mes/src/main/resources/application-dev.yml": "config",
            "docs/02-req/2026-05/demo/README.md": "docs",
            "lamp-mes/src/main/java/Demo.java": "source",
        }

        for path, expected in cases.items():
            with self.subTest(path=path):
                self.assertEqual(classify_changed_file(path), expected)

    def test_change_check_blocks_mixed_test_files_in_delivery_scope_and_dirty_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self.config(tmp_dir)
            req_dir = doc_init(config, "变更检查", "用户要求：这是完整保留的原始需求描述。")
            analysis = req_dir / "01-需求分析拆解" / "01-2026-05-13-1000-证据化分析.md"
            analysis.write_text(
                """# 证据化分析

## 来源证据

- 源码路径：Demo.java

## 明确结论

已确认。
""",
                encoding="utf-8",
            )
            (req_dir / "README.md").write_text(
                """# 变更检查

## 最新结论

- 需求分析：`01-需求分析拆解/01-2026-05-13-1000-证据化分析.md`
""",
                encoding="utf-8",
            )

            def fake_capture(command: list[str], cwd: Path) -> str:
                text = " ".join(command)
                if "status --short" in text:
                    return " M lamp-mes/src/main/java/Demo.java"
                if "log --oneline" in text:
                    return "abc123 feat: 需求提交\nbad999 test: 本地验证 不推送"
                if "log -1 --format=%B" in text:
                    return "feat(mes): 需求提交\n\n1. 新增业务逻辑"
                if "diff-tree" in text and "bad999" in text:
                    return "lamp-mes/src/test/java/DemoTest.java"
                if "diff-tree" in text:
                    return "lamp-mes/src/main/java/Demo.java\nlamp-mes/src/test/java/DemoTest.java"
                return ""

            with (
                patch("momlib.workflow_checks.action_repo_dir", return_value=Path(tmp_dir)),
                patch("momlib.workflow_checks.capture", side_effect=fake_capture),
                patch("momlib.delivery_policy.capture", side_effect=fake_capture),
                redirect_stdout(io.StringIO()) as output,
            ):
                exit_code = change_check(config, "backend", "变更检查")

        text = output.getvalue()
        self.assertEqual(exit_code, 1)
        self.assertIn("working tree is not clean", text)
        self.assertIn("delivery commit contains test file", text)

    def test_change_check_accepts_clean_delivery_with_test_commit_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self.config(tmp_dir)
            req_dir = doc_init(config, "变更检查通过", "用户要求：这是完整保留的原始需求描述。")
            analysis = req_dir / "01-需求分析拆解" / "01-2026-05-13-1000-证据化分析.md"
            analysis.write_text(
                """# 证据化分析

## 来源证据

- 源码路径：Demo.java

## 明确结论

已确认。
""",
                encoding="utf-8",
            )
            (req_dir / "README.md").write_text(
                """# 变更检查通过

## 最新结论

- 需求分析：`01-需求分析拆解/01-2026-05-13-1000-证据化分析.md`
""",
                encoding="utf-8",
            )

            def fake_capture(command: list[str], cwd: Path) -> str:
                text = " ".join(command)
                if "status --short" in text:
                    return ""
                if "log --oneline" in text:
                    return "abc123 feat: 需求提交\nbad999 test: 本地验证 不推送"
                if "log -1 --format=%B" in text:
                    return "feat(mes): 需求提交\n\n1. 新增业务逻辑"
                if "diff-tree" in text and "bad999" in text:
                    return "lamp-mes/src/test/java/DemoTest.java"
                if "diff-tree" in text:
                    return "lamp-mes/src/main/java/Demo.java"
                return ""

            with (
                patch("momlib.workflow_checks.action_repo_dir", return_value=Path(tmp_dir)),
                patch("momlib.workflow_checks.capture", side_effect=fake_capture),
                patch("momlib.delivery_policy.capture", side_effect=fake_capture),
                redirect_stdout(io.StringIO()) as output,
            ):
                exit_code = change_check(config, "backend", "变更检查通过")

        self.assertEqual(exit_code, 0)
        self.assertIn("Change check passed", output.getvalue())

    def test_guard_blocks_page_fix_touching_frontend_common_hook_without_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self.config(tmp_dir)
            req_dir = doc_init(config, "页面字段显示修复", "用户要求：修复单个页面字段显示问题。")
            analysis = req_dir / "01-需求分析拆解" / "01-2026-05-13-1000-证据化分析.md"
            analysis.write_text(
                """# 证据化分析

## 来源证据

- 源码路径：apps/web-antd/src/views/tpm/demo/index.vue

## 明确结论

仅涉及单页面字段显示。
""",
                encoding="utf-8",
            )
            (req_dir / "README.md").write_text(
                """# 页面字段显示修复

## 最新结论

- 需求分析：`01-需求分析拆解/01-2026-05-13-1000-证据化分析.md`
""",
                encoding="utf-8",
            )

            def fake_capture(command: list[str], cwd: Path) -> str:
                text = " ".join(command)
                if "status --short" in text or "log --oneline" in text:
                    return ""
                return ""

            with (
                patch("momlib.workflow_checks.action_repo_dir", return_value=Path(tmp_dir)),
                patch("momlib.workflow_checks.changed_files", return_value=["apps/web-antd/src/hooks/useTable.ts"]),
                patch("momlib.workflow_checks.capture", side_effect=fake_capture),
                patch("momlib.delivery_policy.capture", side_effect=fake_capture),
                redirect_stdout(io.StringIO()) as output,
            ):
                exit_code = guard_check(config, "web", "页面字段显示修复")

        text = output.getvalue()
        self.assertEqual(exit_code, 1)
        self.assertIn("common frontend hook/tool changed by a page-local requirement", text)

    def test_change_check_blocks_pad_controller_without_menu_authorization_migration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self.config(tmp_dir)
            req_dir = doc_init(config, "PAD接口授权检查", "用户要求：这是完整保留的原始需求描述。")
            analysis = req_dir / "01-需求分析拆解" / "01-2026-05-13-1000-证据化分析.md"
            analysis.write_text(
                """# 证据化分析

## 来源证据

- 源码路径：MesMoldManagementPadController.java

## 明确结论

已确认。
""",
                encoding="utf-8",
            )
            (req_dir / "README.md").write_text(
                """# PAD接口授权检查

## 最新结论

- 需求分析：`01-需求分析拆解/01-2026-05-13-1000-证据化分析.md`
""",
                encoding="utf-8",
            )

            def fake_capture(command: list[str], cwd: Path) -> str:
                text = " ".join(command)
                if "status --short" in text:
                    return ""
                if "log --oneline" in text:
                    return "abc123 feat: PAD接口"
                if "log -1 --format=%B" in text:
                    return "feat(mes): PAD接口\n\n1. 新增 PAD 查询接口"
                if "diff-tree" in text:
                    return (
                        "lamp-mes-bff/lamp-mes-bff-controller/src/main/java/"
                        "top/tangyh/lamp/mes/pad/controller/task/MesMoldManagementPadController.java"
                    )
                return ""

            with (
                patch("momlib.workflow_checks.action_repo_dir", return_value=Path(tmp_dir)),
                patch("momlib.workflow_checks.capture", side_effect=fake_capture),
                patch("momlib.delivery_policy.capture", side_effect=fake_capture),
                redirect_stdout(io.StringIO()) as output,
            ):
                exit_code = change_check(config, "backend", "PAD接口授权检查")

        text = output.getvalue()
        self.assertEqual(exit_code, 1)
        self.assertIn("missing menu authorization Flyway migration", text)

    def test_change_check_accepts_pad_controller_with_menu_authorization_migration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self.config(tmp_dir)
            req_dir = doc_init(config, "PAD接口授权通过", "用户要求：这是完整保留的原始需求描述。")
            analysis = req_dir / "01-需求分析拆解" / "01-2026-05-13-1000-证据化分析.md"
            analysis.write_text(
                """# 证据化分析

## 来源证据

- 源码路径：MesMoldManagementPadController.java

## 明确结论

已确认。
""",
                encoding="utf-8",
            )
            (req_dir / "README.md").write_text(
                """# PAD接口授权通过

## 最新结论

- 需求分析：`01-需求分析拆解/01-2026-05-13-1000-证据化分析.md`
""",
                encoding="utf-8",
            )
            sql_dir = req_dir / "04-产出物" / "SQL"
            sql_dir.mkdir(parents=True, exist_ok=True)
            (sql_dir / "菜单授权.sql").write_text("-- 菜单授权来源 SQL\n", encoding="utf-8")

            def fake_capture(command: list[str], cwd: Path) -> str:
                text = " ".join(command)
                if "status --short" in text:
                    return ""
                if "log --oneline" in text:
                    return "abc123 feat: PAD接口"
                if "log -1 --format=%B" in text:
                    return "feat(mes): PAD接口\n\n1. 新增 PAD 查询接口\n2. 新增菜单授权迁移脚本"
                if "diff-tree" in text:
                    return "\n".join(
                        [
                            "lamp-mes-bff/lamp-mes-bff-controller/src/main/java/top/tangyh/lamp/mes/pad/controller/task/MesMoldManagementPadController.java",
                            "lamp-support/lamp-boot-server/src/main/resources/db/migration/mes/2026/06/V1__mes_PAD接口授权.sql",
                        ]
                    )
                return ""

            with (
                patch("momlib.workflow_checks.action_repo_dir", return_value=Path(tmp_dir)),
                patch("momlib.workflow_checks.capture", side_effect=fake_capture),
                patch("momlib.delivery_policy.capture", side_effect=fake_capture),
                redirect_stdout(io.StringIO()) as output,
            ):
                exit_code = change_check(config, "backend", "PAD接口授权通过")

        self.assertEqual(exit_code, 0)
        self.assertIn("Change check passed", output.getvalue())


if __name__ == "__main__":
    unittest.main()
