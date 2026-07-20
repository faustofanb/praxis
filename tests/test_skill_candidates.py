from __future__ import annotations

from pathlib import Path

from praxis.portraits.service import PortraitService
from praxis.skills.candidates import SkillCandidateService
from praxis.skills.registry import SkillRegistry
from praxis.workspace.service import Project, WorkspaceService


def test_business_skill_requires_review_before_catalog_promotion(tmp_path: Path) -> None:
    repo = tmp_path / "app"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='app'\n")
    WorkspaceService(tmp_path).init(
        "demo", "ifc-manufacturing", "knowledge", [Project("app", "python", "app", "main")]
    )
    PortraitService(tmp_path).scan("app")
    service = SkillCandidateService(tmp_path)

    candidate = service.generate("app")
    catalog = tmp_path / "catalog"
    candidate_id = "business.demo.app.development"
    blocked = service.promote(candidate_id, catalog, approved=False)

    assert candidate.ok
    assert candidate.data["status"] == "pending-review"
    assert blocked.code == "SKILL_REVIEW_REQUIRED"
    assert not catalog.exists()

    promoted = service.promote(candidate_id, catalog, approved=True)
    skill = SkillRegistry(catalog).inspect(candidate_id)
    assert promoted.ok
    assert skill.type == "business"
    assert skill.source.startswith("portrait:")
    assert "## 十二、知识来源" in skill.path.read_text()


def test_business_skill_collects_existing_rules_and_skills_as_references(tmp_path: Path) -> None:
    repo = tmp_path / "app"
    (repo / ".cursor" / "rules").mkdir(parents=True)
    (repo / "apps" / "web" / ".cursor" / "rules").mkdir(parents=True)
    (repo / "skills" / "validate-order").mkdir(parents=True)
    (repo / "pyproject.toml").write_text("[project]\nname='app'\n")
    (repo / ".cursor" / "rules" / "business.mdc").write_text("订单必须绑定工厂。\n")
    (repo / "apps" / "web" / ".cursor" / "rules" / "ui.mdc").write_text(
        "页面使用统一组件。\n"
    )
    (repo / "skills" / "validate-order" / "SKILL.md").write_text("# 校验订单\n")
    WorkspaceService(tmp_path).init(
        "demo", "ifc-manufacturing", "knowledge", [Project("app", "python", "app", "main")]
    )

    service = SkillCandidateService(tmp_path)
    candidate = service.generate("app")
    promoted = service.promote(candidate.data["id"], tmp_path / "catalog", approved=True)
    skill_root = Path(promoted.data["path"])

    assert candidate.data["source_files"] == [
        ".cursor/rules/business.mdc",
        "apps/web/.cursor/rules/ui.mdc",
        "skills/validate-order/SKILL.md",
    ]
    assert (skill_root / "references" / ".cursor" / "rules" / "business.mdc").is_file()
    assert (skill_root / "references" / "skills" / "validate-order" / "SKILL.md").is_file()
    assert ".cursor/rules/business.mdc" in (skill_root / "SKILL.md").read_text()
