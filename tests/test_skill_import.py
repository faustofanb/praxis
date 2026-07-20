from __future__ import annotations

from pathlib import Path

from praxis.skills.importer import SkillImportService
from praxis.workspace.service import WorkspaceService


def test_legacy_skill_import_groups_duplicates_and_preserves_sources(tmp_path: Path) -> None:
    WorkspaceService(tmp_path).init("demo", "演示工作空间")
    legacy = tmp_path / "legacy"
    for name, content in (
        ("report-v1", "# 报表开发\n\n核对业务口径。\n"),
        ("report-v2", "# 报表开发\n\n核对业务口径。\n"),
        ("inventory", "# 库存开发\n\n校验库存数量。\n"),
    ):
        path = legacy / name
        path.mkdir(parents=True)
        (path / "SKILL.md").write_text(content)

    result = SkillImportService(tmp_path).import_legacy(legacy, "ifc-mom")

    assert result.ok
    assert result.data["discovered"] == 3
    assert result.data["candidates"] == 2
    assert result.data["duplicate_groups"] == 1
    candidate_files = list((tmp_path / "知识库" / "技能候选" / "导入").glob("*.toml"))
    assert len(candidate_files) == 2
    merged = next(path for path in candidate_files if "report" in path.name)
    text = merged.read_text()
    assert "pending-review" in text
    assert "report-v1/SKILL.md" in text
    assert "report-v2/SKILL.md" in text
