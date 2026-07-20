from __future__ import annotations

from pathlib import Path

from praxis.domains.service import DomainService
from praxis.knowledge.requirements import RequirementService
from praxis.workspace.service import WorkspaceService


def test_domain_registry_adds_lists_and_merges_requirement_links(tmp_path: Path) -> None:
    workspace = WorkspaceService(tmp_path)
    workspace.init("demo", "演示工作空间")
    workspace.add_system("demo-system", "演示系统")
    domains = DomainService(tmp_path)

    assert domains.add("demo-system", "legacy-production", "旧生产域").ok
    assert domains.add("demo-system", "production", "生产管理").ok
    requirement = RequirementService(tmp_path).create(
        "生产报表优化", "优化生产报表", ["demo-system"], ["legacy-production"]
    )
    merged = domains.merge("legacy-production", "production")

    assert merged.ok
    assert merged.data["updated_requirements"] == 1
    assert [item["domain_id"] for item in domains.list().data["domains"]] == ["production"]
    current = RequirementService(tmp_path).show(requirement.data["requirement_id"])
    assert current.data["domains"] == ["production"]
    document = tmp_path / "知识库" / "业务域" / "production.md"
    assert "业务域名称: 生产管理" in document.read_text()
