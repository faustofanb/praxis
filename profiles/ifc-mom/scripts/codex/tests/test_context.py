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

    def test_context_command_splits_main_control_and_worker_context(self) -> None:
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
        self.assertIn("主对话控制面", text)
        self.assertIn("当前用户直接对话默认就是 Main Agent", text)
        self.assertIn("角色 Agent 子任务上下文", text)
        self.assertIn("代码编写和测试必须交给 Execution Agent", text)
        self.assertIn("质量复核交给 Quality Agent", text)
        self.assertIn("subagent 状态：planned/active/blocked/completed/waived", text)
        self.assertIn("不要用根目录全局 git status", text)
        self.assertIn("role_agent 必须明确为 requirement/execution/quality/delivery", text)
        self.assertIn("role agent 与主对话使用同一工作区", text)
        self.assertIn("role agent 禁止继续派发 subagent/Agent/worker", text)
        self.assertIn("必须手工执行时用 rtk git 或 /usr/bin/git，禁止裸 git", text)
        self.assertIn(f"{IFC_MOM}/skills/global/mom-agent-workflow/SKILL.md", text)
        self.assertIn(f"{IFC_MOM}/skills/global/mom-code-quality-compliance/SKILL.md", text)
        self.assertIn(f"{IFC_MOM}/rules/projects/backend/README.md", text)
        self.assertIn(f"{IFC_MOM}/skills/projects/backend/README.md", text)
        self.assertIn("先输出简短实施计划", text)
        self.assertIn("项目 skill；Superpowers 可用时作为辅助", text)
        self.assertIn("非平凡实现先给短设计", text)
        self.assertIn("自动规划 subagent/worker 拆分", text)
        self.assertIn("运行时策略要求用户显式授权才能 spawn", text)
        self.assertIn("mom-context-budgeting/SKILL.md", text)
        self.assertIn("回报同域样例、规则、自检和偏离说明", text)
        self.assertIn("先用 dbx MCP 做真实库只读调查", text)
        self.assertIn("dbx_list_connections", text)
        self.assertIn("dbx_list_tables", text)
        self.assertIn("dbx_execute_query", text)
        self.assertIn("默认只查 LOCAL/DEV", text)
        self.assertIn("本 workspace 本地数据库: connection=LOCAL, database=aotu_dev_local, schema=public", text)
        self.assertIn("每次查询前确认 current_database()", text)
        self.assertNotIn("dbx_get_schema_context", text)
        self.assertNotIn("dbx_describe_table", text)
        self.assertIn("数据口径结论必须回到真实库确认", text)
        self.assertIn("新需求使用 04-产出物/SQL/", text)
        self.assertIn("正式 Flyway 迁移目录只能在收尾环节", text)
        self.assertIn("task system -- code-graph check", text)
        self.assertIn("失败或过期时先运行 task system -- code-graph build", text)
        self.assertIn("不得仅因图谱过期直接降级为源码 grep", text)
        self.assertIn("证据化分析文件", text)

        main_section = text.split("角色 Agent 子任务上下文", maxsplit=1)[0]
        self.assertNotIn(".rule/README.md", main_section)
        self.assertNotIn(".skill/README.md", main_section)
        self.assertNotIn(".rule/global/05-需求文档组织规范.md", main_section)

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
