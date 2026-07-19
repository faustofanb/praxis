from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from momlib.docs import doc_init  # noqa: E402
from momlib.etl import create_etl_topic, ensure_etl_init, print_etl_tree  # noqa: E402


class EtlCommandTest(unittest.TestCase):
    def config(self, tmp_dir: str) -> dict:
        return {
            "projects": {
                "docs": {"path": str(Path(tmp_dir) / "docs")},
            }
        }

    def test_init_creates_app_and_mes_module_skeleton(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self.config(tmp_dir)

            with redirect_stdout(io.StringIO()) as output:
                root = ensure_etl_init(config)
                ensure_etl_init(config)

            self.assertTrue((root / "运营平台").is_dir())
            self.assertTrue((root / "生产制造" / "MES" / "00-系统业务建模").is_dir())
            self.assertTrue((root / "生产制造" / "MES" / "04-工厂建模" / "06-班次信息").is_dir())
            self.assertTrue(
                (
                    root
                    / "生产制造"
                    / "MES"
                    / "24-生产报表"
                    / "01-投入产出"
                    / "03-挤压产出汇总"
                ).is_dir()
            )
            self.assertIn("ETL root:", output.getvalue())

    def test_subject_creates_templates_and_requirement_backlink(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self.config(tmp_dir)
            req_dir = doc_init(config, "领导驾驶舱挤压产出口径修正", "用户要求：完整保留原始需求。")

            with redirect_stdout(io.StringIO()) as output:
                topic_dir = create_etl_topic(
                    config,
                    "生产制造",
                    "MES",
                    "生产报表/投入产出/挤压产出汇总",
                    "领导驾驶舱质量分析挤压产出",
                    requirement_name="领导驾驶舱挤压产出口径修正",
                    menu_code="mes:chart",
                    menu_name="生产报表",
                )

            self.assertTrue((topic_dir / "README.md").is_file())
            readme = (topic_dir / "README.md").read_text(encoding="utf-8")
            metric_card = (topic_dir / "指标口径卡.md").read_text(encoding="utf-8")
            requirement_link = (req_dir / "04-产出物" / "ETL资产链接.md").read_text(encoding="utf-8")
            self.assertIn("24-生产报表/01-投入产出/03-挤压产出汇总", topic_dir.as_posix())
            self.assertTrue((topic_dir / "指标口径卡.md").is_file())
            self.assertTrue((topic_dir / "ETL草案.sql").is_file())
            self.assertIn("fn_rpt_api_", (topic_dir / "ETL草案.sql").read_text(encoding="utf-8"))
            self.assertIn('type: "etl-asset"', readme)
            self.assertIn("- 当前资产：[[领导驾驶舱质量分析挤压产出]]", readme)
            self.assertIn('type: "etl-metric-card"', metric_card)
            self.assertIn("- ETL资产：[[领导驾驶舱质量分析挤压产出]]", metric_card)
            self.assertIn("必须下推到源表过滤", metric_card)
            self.assertTrue((req_dir / "04-产出物" / "ETL资产链接.md").is_file())
            self.assertIn('type: "requirement-etl-link"', requirement_link)
            self.assertIn("[领导驾驶舱质量分析挤压产出]", requirement_link)
            self.assertIn("ETL topic:", output.getvalue())

    def test_subject_uses_deep_menu_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self.config(tmp_dir)

            topic_dir = create_etl_topic(
                config,
                "生产制造",
                "MES",
                "工厂建模/班次信息",
                "班次产能指标",
                menu_code="mes:base:shift",
                menu_name="班次信息",
            )

            self.assertEqual(topic_dir.name, "班次产能指标")
            self.assertEqual(topic_dir.parent.name, "06-班次信息")
            self.assertEqual(topic_dir.parent.parent.name, "04-工厂建模")
            self.assertIn("菜单路径：工厂建模/班次信息", (topic_dir / "README.md").read_text(encoding="utf-8"))
            self.assertIn("菜单路径：工厂建模/班次信息", (topic_dir / "指标口径卡.md").read_text(encoding="utf-8"))

    def test_tree_prints_existing_etl_structure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self.config(tmp_dir)
            ensure_etl_init(config)

            with redirect_stdout(io.StringIO()) as output:
                print_etl_tree(config, max_depth=2)

        text = output.getvalue()
        self.assertIn("03-etl", text)
        self.assertIn("生产制造/", text)


if __name__ == "__main__":
    unittest.main()
