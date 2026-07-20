from __future__ import annotations

from pathlib import Path

from praxis.skills.registry import SkillRegistry


def test_dbx_skill_is_routed_only_for_database_intent() -> None:
    registry = SkillRegistry.bundled()

    routed = registry.route("调查报表 SQL 错误并核对表结构")
    ordinary = registry.route("修改 WMS 页面按钮颜色")

    assert [skill.id for skill in routed] == ["dbx-database-investigation"]
    assert ordinary == []
    assert registry.route("debug failing tests", budget=100) == []


def test_dbx_skill_metadata_and_resource_contract() -> None:
    registry = SkillRegistry.bundled()
    skill = registry.inspect("dbx-database-investigation")

    assert skill.type == "system"
    assert skill.source == "praxis"
    assert skill.risk == "database-read"
    assert skill.required_tools == (
        "dbx_list_connections",
        "dbx_list_tables",
        "dbx_describe_table",
        "dbx_get_schema_context",
        "dbx_execute_query",
    )
    resource = registry.resource("praxis://skills/system/dbx-database-investigation")
    assert "未找到匹配 connection" in resource
    assert "dbx_add_connection" in resource
    assert "禁止" in resource


def test_skill_hash_changes_with_content(tmp_path: Path) -> None:
    root = tmp_path / "workflow" / "example"
    root.mkdir(parents=True)
    (root / "skill.toml").write_text(
        'id = "example"\ntype = "workflow"\nversion = "1.0.0"\n'
        'license = "MIT"\nrisk = "none"\ncontext_budget = 100\nrequired_tools = []\n'
        'source = "test"\nsource_version = "1"\ntriggers = ["example"]\n'
    )
    (root / "SKILL.md").write_text("first")
    first = SkillRegistry(tmp_path).inspect("example").content_hash
    (root / "SKILL.md").write_text("second")
    second = SkillRegistry(tmp_path).inspect("example").content_hash
    assert first != second
