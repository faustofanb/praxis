from __future__ import annotations

import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import task as task_module  # noqa: E402
from momlib.docs import classify_business_domain, doc_init, doc_iter, tolaria_check, tolaria_publish, write_domain_candidates, write_domain_index, write_requirement_global_index  # noqa: E402
from momlib.workflow_checks import docs_index  # noqa: E402


class DocsInitTest(unittest.TestCase):
    def test_docs_init_rejects_missing_raw_requirement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = {"projects": {"docs": {"path": tmp_dir}}}

            with self.assertRaises(SystemExit):
                doc_init(config, "深加工AI无识别", "")

    def test_docs_init_rejects_placeholder_raw_requirement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = {"projects": {"docs": {"path": tmp_dir}}}

            with self.assertRaises(SystemExit):
                doc_init(config, "深加工AI无识别", "用户原始需求")

    def test_docs_init_rejects_non_chinese_or_generic_requirement_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = {"projects": {"docs": {"path": tmp_dir}}}

            with self.assertRaises(SystemExit):
                doc_init(config, "task", "用户要求：这是完整保留的原始需求描述。")
            with self.assertRaises(SystemExit):
                doc_init(config, "tmp-123", "用户要求：这是完整保留的原始需求描述。")

    def test_docs_init_preserves_long_raw_requirement_verbatim(self) -> None:
        raw = """用户要求：
1. 调整领导驾驶舱 MagicAPI 取数逻辑。
2. 保留 SQL：
select id, name
from mes_demo
where status = 'FAIL';
3. 附件未落盘原因：当前对话无法取得截图二进制，请用户补传本地路径。
"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = {"projects": {"docs": {"path": tmp_dir}}}

            req_dir = doc_init(config, "领导驾驶舱取数逻辑", raw)
            raw_files = sorted((req_dir / "00-原始需求").glob("*.md"))
            raw_text = raw_files[0].read_text(encoding="utf-8")

        self.assertIn(raw, raw_text)
        self.assertIn("```text", raw_text)
        self.assertIn('type: "requirement-original"', raw_text)
        self.assertIn('requirement: "领导驾驶舱取数逻辑"', raw_text)

    def test_docs_init_readme_uses_control_plane_rule_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = {"projects": {"docs": {"path": tmp_dir}}}

            req_dir = doc_init(config, "深加工AI无识别", "用户要求：深加工 AI 无识别预警需要保留原始描述。")
            readme = (req_dir / "README.md").read_text(encoding="utf-8")

        self.assertIn("`AGENTS.md`", readme)
        self.assertIn('type: "requirement"', readme)
        self.assertIn("- 当前需求：[[深加工AI无识别]]", readme)
        self.assertIn("## Tolaria 知识链接", readme)
        self.assertIn("Tolaria frontmatter、H1、wikilink 和 saved views", readme)
        self.assertNotIn("`.rule/README.md`", readme)
        self.assertNotIn("`.skill/README.md`", readme)
        self.assertNotIn("`.rule/global/05-需求文档组织规范.md`", readme)
        self.assertNotIn("`.rule/projects/backend/README.md`", readme)

    def test_doc_iter_writes_lightweight_phase_templates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = {"projects": {"docs": {"path": tmp_dir}}}
            doc_init(config, "模板优化", "用户要求：模板优化需要验证阶段文件字段。")

            analysis = doc_iter(config, "模板优化", "analysis", "证据化分析")
            plan = doc_iter(config, "模板优化", "plan", "实施规划")
            progress = doc_iter(config, "模板优化", "progress", "开发进度")

            analysis_text = analysis.read_text(encoding="utf-8")
            plan_text = plan.read_text(encoding="utf-8")
            progress_text = progress.read_text(encoding="utf-8")

        self.assertIn("## 用户原始需求", analysis_text)
        self.assertIn('type: "requirement-analysis"', analysis_text)
        self.assertIn('requirement: "模板优化"', analysis_text)
        self.assertIn("## 证据来源", analysis_text)
        self.assertIn("来源证据", analysis_text)
        self.assertIn('type: "requirement-plan"', plan_text)
        self.assertIn("## 决策", plan_text)
        self.assertIn('type: "requirement-progress"', progress_text)
        self.assertIn("## 待验证项", progress_text)
        for text in (analysis_text, plan_text, progress_text):
            self.assertIn("## 推荐下一步", text)
            self.assertIn("- [推荐]", text)

    def test_docs_index_writes_recommended_next_steps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = {"projects": {"docs": {"path": tmp_dir}}}
            doc_init(config, "模板优化", "用户要求：模板优化需要 README 推荐下一步。")
            doc_iter(config, "模板优化", "analysis", "证据化分析")

            docs_index(config, "模板优化")
            readme = next(Path(tmp_dir).glob("02-req/2026-07/*模板优化/README.md"))
            readme_text = readme.read_text(encoding="utf-8")

        self.assertIn("## 推荐下一步", readme_text)
        self.assertIn("- [推荐]", readme_text)
        self.assertIn("task req -- iter 模板优化 plan", readme_text)

    def test_doc_iter_can_write_explicit_body_without_placeholders(self) -> None:
        body = """# 证据化分析

## 用户原始需求

用户要求：记录流程演练证据。

## 当前结论

已完成流程验证。

## 证据来源

- 来源证据：task gate -- ready 输出。
- 源码路径：scripts/codex/task.py。
- 表字段/接口/页面：不涉及。
- 样例数据/日志/复现条件：模拟需求流程。

## 明确结论

可直接通过正文创建无占位阶段文件。
"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = {"projects": {"docs": {"path": tmp_dir}}}
            doc_init(config, "正文优化", "用户要求：正文优化需要验证阶段文件正文。")

            analysis = doc_iter(config, "正文优化", "analysis", "证据化分析", body)
            text = analysis.read_text(encoding="utf-8")

        self.assertEqual(text, body.rstrip() + "\n")
        self.assertNotIn("待补充", text)

    def test_write_requirement_global_index_collects_requirement_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = {"projects": {"docs": {"path": tmp_dir}}}
            req_dir = doc_init(config, "设备采购流程优化", "用户要求：设备采购流程优化需要保留原始描述。")
            analysis = doc_iter(
                config,
                "设备采购流程优化",
                "analysis",
                "证据化分析",
                """# 证据化分析

## 来源证据

- 源码路径：lamp-tpm/TpmPurchaseRequisitionService.java
- 表字段：tpm_purchase_requisition.status

## 明确结论

涉及设备采购申请和 SAP 接口。
""",
            )
            (req_dir / "README.md").write_text(
                f"""# 设备采购流程优化

## 基本信息

- 需求名称：设备采购流程优化
- 目标项目：backend, web
- 当前状态：已完成

## 最新结论

- 需求分析：`{analysis.relative_to(req_dir).as_posix()}`
""",
                encoding="utf-8",
            )

            index_md, index_json = write_requirement_global_index(config)

            md_text = index_md.read_text(encoding="utf-8")
            json_text = index_json.read_text(encoding="utf-8")

        self.assertIn("设备采购流程优化", md_text)
        self.assertIn("backend, web", md_text)
        self.assertIn("设备采购申请", json_text)
        self.assertIn("SAP接口", json_text)

    def test_write_domain_index_groups_requirements_by_business_aggregate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = {"projects": {"docs": {"path": tmp_dir}}}
            doc_init(config, "设备采购SAP接口优化", "用户要求：设备采购申请需要优化 SAP 接口字段映射。")

            index_md, index_json = write_domain_index(config)

            md_text = index_md.read_text(encoding="utf-8")
            json_text = index_json.read_text(encoding="utf-8")
            aggregate = Path(tmp_dir) / "01-domain" / "purchase" / "purchase-requisition.md"
            aggregate_text = aggregate.read_text(encoding="utf-8")

        self.assertIn("purchase / purchase-requisition", md_text)
        self.assertIn("设备采购SAP接口优化", aggregate_text)
        self.assertIn('"boundedContext": "purchase"', json_text)
        self.assertIn('"aggregate": "purchase-requisition"', json_text)

    def test_domain_index_reclassifies_default_uncategorized_frontmatter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            docs_root = Path(tmp_dir)
            req_dir = docs_root / "02-req" / "2026-07" / "2026-07-07-WMS_PDA盘点清单排序规则"
            req_dir.mkdir(parents=True)
            (req_dir / "README.md").write_text(
                """---
type: "requirement"
title: "WMS_PDA盘点清单排序规则"
created: "2026-07-07-0943"
status: "已初始化"
bounded_context: "uncategorized"
aggregate: "general"
capability: "待归类"
tags:
  - "ifc-mom/requirement"
---

# WMS_PDA盘点清单排序规则
""",
                encoding="utf-8",
            )

            _, index_json = write_domain_index({"projects": {"docs": {"path": tmp_dir}}})
            json_text = index_json.read_text(encoding="utf-8")

        self.assertIn('"boundedContext": "wms"', json_text)
        self.assertIn('"aggregate": "wms-pda"', json_text)

    def test_domain_dictionary_drives_business_classification(self) -> None:
        domain = classify_business_domain("用户要求：挤压合金产出和金属平衡口径需要统一。")

        self.assertEqual(domain["boundedContext"], "mes-extrusion")
        self.assertEqual(domain["aggregate"], "metal-balance")

    def test_domain_dictionary_covers_wms_pda_requirements(self) -> None:
        domain = classify_business_domain("用户要求：WMS_PDA 盘点清单排序规则需要调整。")

        self.assertEqual(domain["boundedContext"], "wms")
        self.assertEqual(domain["aggregate"], "wms-pda")

    def test_docs_init_frontmatter_includes_business_domain_tags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = {"projects": {"docs": {"path": tmp_dir}}}

            req_dir = doc_init(config, "WMS盘点清单排序", "用户要求：WMS_PDA 盘点清单排序规则需要调整。")
            readme = (req_dir / "README.md").read_text(encoding="utf-8")

        self.assertIn('  - "domain/wms"', readme)
        self.assertIn('  - "aggregate/wms-pda"', readme)
        self.assertIn('  - "object/盘点清单"', readme)

    def test_docs_init_refreshes_domain_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = {"projects": {"docs": {"path": tmp_dir}}}

            doc_init(config, "主报表金属平衡氧化数据自动获取", "用户要求：主报表金属平衡氧化数据自动获取。")

            index = Path(tmp_dir) / "01-domain" / "INDEX.md"
            aggregate = Path(tmp_dir) / "01-domain" / "mes-extrusion" / "metal-balance.md"
            index_exists = index.is_file()
            aggregate_exists = aggregate.is_file()

        self.assertTrue(index_exists)
        self.assertTrue(aggregate_exists)

    def test_docs_init_reuses_active_requirement_in_same_aggregate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = {"projects": {"docs": {"path": tmp_dir}}}
            existing = doc_init(config, "设备采购流程优化", "用户要求：设备采购申请字段需要优化。")

            with redirect_stdout(StringIO()) as output:
                reused = doc_init(config, "设备采购字段调整", "用户要求：设备采购申请字段继续调整。")

        self.assertEqual(reused, existing)
        self.assertIn("Requirement docs reused", output.getvalue())
        self.assertIn(existing.name, output.getvalue())

    def test_write_domain_candidates_extracts_terms_from_uncategorized_research_docs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            docs_root = Path(tmp_dir)
            config = {"projects": {"docs": {"path": tmp_dir}}}
            req_dir = docs_root / "02-req" / "2026-07" / "2026-07-07-盘点清单排序规则"
            research_dir = req_dir / "04-产出物" / "关联信息调查"
            research_dir.mkdir(parents=True)
            (req_dir / "README.md").write_text(
                """---
type: "requirement"
title: "盘点清单排序规则"
bounded_context: "uncategorized"
aggregate: "general"
capability: "待归类"
---

# 盘点清单排序规则
""",
                encoding="utf-8",
            )
            (research_dir / "01-调查.md").write_text(
                """# 关联信息调查

WMS_PDA 盘点清单排序规则涉及库存盘点页面、wms_inventory_task 表和 inventory/list 接口。
""",
                encoding="utf-8",
            )

            markdown_path, json_path = write_domain_candidates(config)
            report = json.loads(json_path.read_text(encoding="utf-8"))
            markdown = markdown_path.read_text(encoding="utf-8")

        self.assertEqual(report["candidateCount"], 1)
        self.assertEqual(report["candidates"][0]["title"], "盘点清单排序规则")
        self.assertIn("WMS_PDA", report["candidates"][0]["terms"])
        self.assertIn("盘点清单", report["candidates"][0]["terms"])
        self.assertIn("domain/wms", report["candidates"][0]["suggestedTags"])
        self.assertIn("aggregate/wms-pda", report["candidates"][0]["suggestedTags"])
        self.assertIn("object/盘点清单", report["candidates"][0]["suggestedTags"])
        self.assertIn("盘点清单排序规则", markdown)

    def test_domain_candidates_action_is_available_through_docs_dispatcher(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = {"projects": {"docs": {"path": tmp_dir}}}
            code = task_module.run_praxis_docs_action(config, ["domain-candidates"])
            report = Path(tmp_dir) / ".praxis" / "out" / "domain-candidates.json"
            report_exists = report.is_file()

        self.assertEqual(code, 0)
        self.assertTrue(report_exists)

    def test_doc_iter_refreshes_domain_candidates_from_analysis_body(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            docs_root = Path(tmp_dir)
            config = {"projects": {"docs": {"path": tmp_dir}}}
            req_dir = docs_root / "02-req" / "2026-07" / "2026-07-07-盘点清单排序规则"
            req_dir.mkdir(parents=True)
            (req_dir / "README.md").write_text(
                """---
type: "requirement"
title: "盘点清单排序规则"
bounded_context: "uncategorized"
aggregate: "general"
capability: "待归类"
---

# 盘点清单排序规则
""",
                encoding="utf-8",
            )

            doc_iter(
                config,
                "盘点清单排序规则",
                "analysis",
                "关联信息调查",
                "WMS_PDA 盘点清单排序规则涉及 inventory/list 接口。",
            )
            report = json.loads((docs_root / ".praxis" / "out" / "domain-candidates.json").read_text(encoding="utf-8"))

        self.assertEqual(report["candidateCount"], 1)
        self.assertIn("WMS_PDA", report["candidates"][0]["terms"])

    def test_tolaria_check_reports_missing_metadata_without_writing_docs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            docs_root = Path(tmp_dir)
            config = {"projects": {"docs": {"path": tmp_dir}}}
            req_dir = docs_root / "02-req" / "2026-07" / "2026-07-01-数采表优化"
            req_dir.mkdir(parents=True)
            readme = req_dir / "README.md"
            readme.write_text("# 数采表优化\n\n旧需求正文。\n", encoding="utf-8")

            report_path = tolaria_check(config, ["数采表优化"])

            report_text = report_path.read_text(encoding="utf-8")
            readme_text = readme.read_text(encoding="utf-8")

        self.assertIn('"target": "数采表优化"', report_text)
        self.assertIn('"missing_frontmatter"', report_text)
        self.assertEqual(readme_text, "# 数采表优化\n\n旧需求正文。\n")

    def test_tolaria_publish_writes_types_views_and_requirement_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            docs_root = Path(tmp_dir)
            config = {"projects": {"docs": {"path": tmp_dir}}}
            req_dir = doc_init(config, "数采表优化", "用户要求：数采表优化需要进入 Tolaria 知识库。")

            index_path = tolaria_publish(config, ["数采表优化"])

            index_text = index_path.read_text(encoding="utf-8")
            requirement_type = docs_root / "types" / "requirement.md"
            active_view = docs_root / "views" / "active-requirements.yml"
            requirement_type_text = requirement_type.read_text(encoding="utf-8")
            active_view_text = active_view.read_text(encoding="utf-8")
            domain_type = docs_root / "types" / "domain-aggregate.md"
            domain_view = docs_root / "views" / "domain-aggregates.yml"
            domain_type_text = domain_type.read_text(encoding="utf-8")
            domain_view_text = domain_view.read_text(encoding="utf-8")

        self.assertIn('type: "tolaria-knowledge-index"', index_text)
        self.assertIn("[[数采表优化]]", index_text)
        self.assertIn("type: Type", requirement_type_text)
        self.assertIn("field: type", active_view_text)
        self.assertIn("Domain Aggregate", domain_type_text)
        self.assertIn("domain-aggregate", domain_view_text)

    def test_tolaria_actions_are_available_through_requirement_dispatcher(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            docs_root = Path(tmp_dir)
            config = {"projects": {"docs": {"path": tmp_dir}}}
            doc_init(config, "数采表优化", "用户要求：数采表优化需要发布 Tolaria 索引。")

            check_code = task_module.run_praxis_requirement_action(config, ["tolaria-check", "数采表优化"])
            publish_code = task_module.run_praxis_requirement_action(config, ["tolaria-publish", "数采表优化"])

            report = docs_root / ".praxis" / "out" / "tolaria" / "tolaria-check.json"
            index = next((docs_root / "02-req").glob("2026-07/*数采表优化/04-产出物/Tolaria知识索引.md"))
            report_exists = report.is_file()
            index_exists = index.is_file()

        self.assertEqual(check_code, 0)
        self.assertEqual(publish_code, 0)
        self.assertTrue(report_exists)
        self.assertTrue(index_exists)


if __name__ == "__main__":
    unittest.main()
