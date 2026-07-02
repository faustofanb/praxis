from __future__ import annotations

import importlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class PraxisTemplatesTest(unittest.TestCase):
    def test_template_report_validates_rule_skill_and_template_contracts(self) -> None:
        spec = importlib.util.find_spec("momlib.praxis_templates")
        self.assertIsNotNone(spec)
        assert spec is not None
        module = importlib.import_module("momlib.praxis_templates")

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            repo_root = Path(__file__).resolve().parents[3]
            template_dir = root / ".praxis" / "templates"
            template_dir.mkdir(parents=True)
            for source in ["rule.md.tpl", "skill.md.tpl", "schema.json"]:
                source_path = repo_root / ".praxis" / "templates" / source
                (template_dir / source).write_text(source_path.read_text(encoding="utf-8"), encoding="utf-8")
            (root / ".rule" / "global").mkdir(parents=True)
            (root / ".rule" / "global" / "demo.md").write_text("# Demo\n\nbody\n", encoding="utf-8")
            skill_dir = root / ".skill" / "global" / "demo"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "---\nname: demo\ndescription: Demo skill.\n---\n\n# Demo\n",
                encoding="utf-8",
            )

            rendered_rule = root / ".rule" / "global" / "generated.md"
            rendered_skill = root / ".skill" / "global" / "generated" / "SKILL.md"
            module.render_template(
                root=root,
                kind="rule",
                slug="generated-rule",
                title="Generated Rule",
                description="Generated rule description.",
                output=rendered_rule,
            )
            module.render_template(
                root=root,
                kind="skill",
                slug="generated-skill",
                title="Generated Skill",
                description="Generated skill description.",
                output=rendered_skill,
            )
            report_path = module.write_template_report(root)

            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["templates"], [".praxis/templates/rule.md.tpl", ".praxis/templates/skill.md.tpl"])
            self.assertEqual(report["counts"]["rules"], 2)
            self.assertEqual(report["counts"]["skills"], 2)
            self.assertIn("# Generated Rule", rendered_rule.read_text(encoding="utf-8"))
            self.assertIn("name: generated-skill", rendered_skill.read_text(encoding="utf-8"))

    def test_templates_render_required_structured_sections(self) -> None:
        module = importlib.import_module("momlib.praxis_templates")

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            template_dir = root / ".praxis" / "templates"
            template_dir.mkdir(parents=True)
            repo_root = Path(__file__).resolve().parents[3]
            for source in ["rule.md.tpl", "skill.md.tpl", "schema.json"]:
                source_path = repo_root / ".praxis" / "templates" / source
                (template_dir / source).write_text(source_path.read_text(encoding="utf-8"), encoding="utf-8")
            (root / ".praxis" / "rules").mkdir(parents=True)
            (root / ".praxis" / "skills").mkdir(parents=True)

            rule = module.render_template(
                root=root,
                kind="rule",
                slug="routing-rule",
                title="Routing Rule",
                description="Route tasks by project facts.",
                output=root / ".praxis" / "rules" / "routing-rule.md",
            )
            skill = module.render_template(
                root=root,
                kind="skill",
                slug="routing-skill",
                title="Routing Skill",
                description="Route tasks by project facts.",
                output=root / ".praxis" / "skills" / "routing-skill" / "SKILL.md",
            )
            report = module.template_report(root)

            for path in [rule, skill]:
                text = path.read_text(encoding="utf-8")
                for heading in [
                    "## Metadata",
                    "## Scope",
                    "## Triggers",
                    "## Inputs",
                    "## Outputs",
                    "## Workflow",
                    "## Validation",
                    "## Evidence",
                    "## Failure Modes",
                    "## Examples",
                    "## References",
                    "## Compatibility",
                    "## Version",
                ]:
                    self.assertIn(heading, text)
                self.assertNotRegex(text, r"{{[^}]+}}")
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["schema"], ".praxis/templates/schema.json")


if __name__ == "__main__":
    unittest.main()
