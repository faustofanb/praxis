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
