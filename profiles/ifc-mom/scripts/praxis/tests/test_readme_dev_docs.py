from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


ROOT = Path(__file__).resolve().parents[3]


class ReadmeDevDocsTest(unittest.TestCase):
    def assert_readme_dev(self, relative: str, required_sections: list[str]) -> None:
        project_dir = ROOT / relative
        if not project_dir.is_dir():
            self.skipTest(f"project repository is not present in this worktree: {project_dir}")
        path = project_dir / "README.dev.md"
        self.assertTrue(path.is_file(), f"missing {path}")
        text = path.read_text(encoding="utf-8")
        for section in required_sections:
            self.assertIn(section, text)

    def test_backend_has_minimal_onboarding_readme(self) -> None:
        self.assert_readme_dev(
            "ifc-mom-column-max",
            ["# IFC MOM 后端开发指南", "## 项目职责", "## 常用目录", "## 最小验证", "## 禁止事项", "## 常见坑"],
        )

    def test_web_has_minimal_onboarding_readme(self) -> None:
        self.assert_readme_dev(
            "ifc-web-mom-max",
            ["# IFC MOM Web 开发指南", "## 项目职责", "## 常用目录", "## 最小验证", "## 禁止事项", "## 常见坑"],
        )

    def test_pda_projects_have_shared_minimal_onboarding_readme(self) -> None:
        for relative in ["ifc-mes-pad", "ifc-mes-pda", "ifc-tpm-pda", "ifc-qms-pad"]:
            with self.subTest(relative=relative):
                self.assert_readme_dev(
                    relative,
                    ["# IFC MOM PDA/PAD 开发指南", "## 项目职责", "## 常用目录", "## 最小验证", "## 禁止事项", "## 常见坑"],
                )


if __name__ == "__main__":
    unittest.main()
