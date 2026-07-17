from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from momlib.context import context_brief_command, context_command, rule_skill_paths, worker_rule_skill_paths  # noqa: E402


IFC_MOM = ".praxis/extensions/ifc-mom"


class ContextCommandTest(unittest.TestCase):
    def test_context_brief_command_prints_low_noise_resume_summary(self) -> None:
        config = {
            "projects": {
                "docs": {"path": "/tmp/docs"},
                "backend": {
                    "path": "ifc-mom-column-max",
                    "defaultBranch": "local",
                },
            }
        }

        with redirect_stdout(io.StringIO()) as output:
            context_brief_command(config, "backend", "氧化上下梁识别问题")

        text = output.getvalue()
        self.assertIn("Context brief", text)
        self.assertIn("目标项目: backend", text)
        self.assertIn("需求名: 氧化上下梁识别问题", text)
        self.assertIn("推荐验证: task project -- verify backend 氧化上下梁识别问题", text)
        self.assertIn("完整上下文: task context -- backend 氧化上下梁识别问题", text)
        self.assertNotIn("dbx_list_connections", text)
        self.assertNotIn("Graph" + "ify", text)
        self.assertNotIn("角色 Agent 子任务上下文", text)

    def test_context_commands_print_next_actions(self) -> None:
        config = {
            "projects": {
                "docs": {"path": "/tmp/docs"},
                "backend": {
                    "path": "ifc-mom-column-max",
                    "defaultBranch": "local",
                },
            }
        }

        with redirect_stdout(io.StringIO()) as brief_output:
            context_brief_command(config, "backend", "氧化上下梁识别问题")
        with redirect_stdout(io.StringIO()) as full_output:
            context_command(config, "backend", "氧化上下梁识别问题")

        brief_text = brief_output.getvalue()
        full_text = full_output.getvalue()
        for text in (brief_text, full_text):
            self.assertIn("nextActions:", text)
            self.assertIn("task context -- backend 氧化上下梁识别问题", text)
            self.assertIn("task project -- preflight backend 氧化上下梁识别问题", text)
        self.assertIn("[推荐] 恢复完整上下文", brief_text)
        self.assertIn("[推荐] 执行工作区预检", full_text)

    def test_context_command_uses_fast_path_without_default_subagents_or_checks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = {
                "database": {
                    "local": {
                        "connection": "LOCAL",
                        "database": "aotu_dev_local",
                        "schema": "public",
                    }
                },
                "projects": {
                    "docs": {"path": str(Path(tmp_dir) / "docs")},
                    "backend": {
                        "path": str(Path(tmp_dir) / "ifc-mom-column-max"),
                        "defaultBranch": "local",
                    },
                }
            }

            with redirect_stdout(io.StringIO()) as output:
                context_command(config, "backend", "氧化上下梁识别问题")

        text = output.getvalue()
        self.assertIn("快速需求控制面", text)
        self.assertIn("当前主对话直接完成调查和代码修改", text)
        self.assertIn("同名需求恢复已有目录和工作树", text)
        self.assertIn("默认只做语法或解析检查", text)
        self.assertIn("不默认执行 TDD、完整测试、预检、全局校验或收口门禁", text)
        self.assertIn("微小参数变更快速通道", text)
        self.assertIn("最多 1–2 条契约测试", text)
        self.assertIn("生产代码最后一次修改后只执行一次项目 verify", text)
        self.assertIn("禁止手动执行根级 Maven -am install", text)
        self.assertIn("发布本地 Maven 制品或跨仓库联调", text)
        self.assertIn("按需规则", text)
        self.assertIn("先用 dbx MCP 做必要的只读调查", text)
        self.assertIn("dbx_list_connections", text)
        self.assertIn("dbx_list_tables", text)
        self.assertIn("dbx_execute_query", text)
        self.assertIn("默认只查 LOCAL/DEV", text)
        self.assertIn("本 workspace 本地数据库: connection=LOCAL, database=aotu_dev_local, schema=public", text)
        self.assertIn("每次查询前确认 current_database()", text)
        self.assertNotIn("dbx_get_schema_context", text)
        self.assertNotIn("dbx_describe_table", text)
        self.assertIn("本次改动需要的表、字段或样例即可", text)
        self.assertIn("新需求使用 04-产出物/SQL/", text)
        self.assertIn("正式 Flyway 迁移目录只能在收尾环节", text)
        self.assertIn("可用 CodeGraph 定位；不可用或过期时直接用源码搜索", text)
        self.assertIn("过期图谱会自动排队异步刷新", text)
        self.assertIn("不强制新增分析文件", text)
        self.assertNotIn("自动规划 subagent/worker 拆分", text)

        self.assertIn("task project -- verify backend 氧化上下梁识别问题", text)

    def test_rule_skill_paths_are_control_plane_only(self) -> None:
        paths = rule_skill_paths("backend")

        self.assertEqual(
            paths,
            ["AGENTS.md", ".praxis/rules/praxis-workflow.md", f"{IFC_MOM}/skills/global/mom-agent-workflow/SKILL.md"],
        )
        self.assertNotIn(".rule/README.md", paths)
        self.assertNotIn(".skill/README.md", paths)
        self.assertNotIn(".rule/global/05-需求文档组织规范.md", paths)
        self.assertNotIn(".rule/projects/backend/README.md", paths)

    def test_mes_pda_uses_shared_pda_worker_context(self) -> None:
        self.assertEqual(
            worker_rule_skill_paths("mes-pda"),
            [
                f"{IFC_MOM}/skills/global/mom-database-investigation/SKILL.md",
                f"{IFC_MOM}/skills/global/mom-delivery-branch-hygiene/SKILL.md",
                f"{IFC_MOM}/rules/projects/pda/README.md",
                f"{IFC_MOM}/skills/projects/pda/pda-development/SKILL.md",
            ],
        )

    def test_big_screen_uses_dedicated_worker_context(self) -> None:
        self.assertEqual(
            worker_rule_skill_paths("big-screen"),
            [
                f"{IFC_MOM}/skills/global/mom-database-investigation/SKILL.md",
                f"{IFC_MOM}/skills/global/mom-delivery-branch-hygiene/SKILL.md",
                f"{IFC_MOM}/rules/projects/big-screen/README.md",
                f"{IFC_MOM}/skills/projects/big-screen/big-screen-development/SKILL.md",
            ],
        )

    def test_backend_worker_context_includes_code_quality_compliance(self) -> None:
        self.assertEqual(
            worker_rule_skill_paths("backend"),
            [
                f"{IFC_MOM}/skills/global/mom-database-investigation/SKILL.md",
                f"{IFC_MOM}/skills/global/mom-delivery-branch-hygiene/SKILL.md",
                f"{IFC_MOM}/skills/global/mom-code-quality-compliance/SKILL.md",
                f"{IFC_MOM}/rules/projects/backend/README.md",
                f"{IFC_MOM}/skills/projects/backend/README.md",
            ],
        )


if __name__ == "__main__":
    unittest.main()
