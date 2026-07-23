from __future__ import annotations

from pathlib import Path

from praxis.skills.registry import SkillRegistry, SkillRoutingContext


def test_dbx_skill_is_routed_only_for_database_intent() -> None:
    registry = SkillRegistry.bundled()

    routed = registry.route("调查报表 SQL 错误并核对表结构")
    ordinary = registry.route("修改 WMS 页面按钮颜色")

    assert [skill.id for skill in routed] == ["dbx-database-investigation"]
    assert [skill.id for skill in ordinary] == ["praxis-requirement-workflow"]
    assert registry.route("debug failing tests", budget=100) == []


def test_requirement_workflow_requires_documents_worktree_and_user_consent() -> None:
    skill = SkillRegistry.bundled().inspect("praxis-requirement-workflow")
    content = skill.path.read_text()

    assert skill.type == "workflow"
    assert "新建需求时不要创建工作树" in content
    assert "第一次代码编辑前" in content
    assert "默认执行 TDD" in content
    assert "完整回归、lint、format、typecheck" in content
    assert "独立验证授权" in content


def test_minimum_module_compile_is_a_bundled_workflow_skill() -> None:
    skill = SkillRegistry.bundled().inspect("minimum-module-compile")
    content = skill.path.read_text()

    assert skill.type == "workflow"
    assert skill.source == "praxis"
    assert skill.risk == "workspace-write"
    assert "最小受影响模块" in content
    assert "扩大为全仓" in content
    assert "exit code" in content
    assert "uv run --no-sync" in content
    assert "所有外部命令" in content
    assert "rtk proxy" in content
    assert "RTK 自身执行失败" in content
    assert "降级命令" in content


def test_codegraph_impact_analysis_requires_pre_edit_semantic_evidence() -> None:
    registry = SkillRegistry.bundled()
    assert "codegraph-impact-analysis" in {skill.id for skill in registry.all()}

    skill = registry.inspect("codegraph-impact-analysis")
    content = skill.path.read_text()

    assert skill.type == "workflow"
    assert skill.source == "praxis"
    assert "编辑前" in content
    assert "codegraph_explore" in content
    assert "调用路径" in content
    assert "Blast Radius" in content
    assert "rg_fallback" in content
    assert "连续错误" not in content


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


def test_structured_skill_routing_scores_business_facts_and_denied_risk(tmp_path: Path) -> None:
    root = tmp_path / "business" / "reporting"
    root.mkdir(parents=True)
    (root / "skill.toml").write_text(
        'id = "reporting"\ntype = "business"\nversion = "1.0.0"\n'
        'license = "Proprietary"\nrisk = "none"\ncontext_budget = 100\n'
        'required_tools = []\nsource = "verified-doc"\nsource_version = "1"\n'
        'triggers = ["报表"]\nsystems = ["ifc-mom"]\nbusiness_domains = ["production"]\n'
        'projects = ["backend"]\n'
        'repository_roles = ["java-backend"]\nstages = ["backend"]\n'
        'artifact_types = ["api"]\ndenied_risks = ["deployment"]\n'
    )
    (root / "SKILL.md").write_text("# 生产报表开发\n")
    registry = SkillRegistry(tmp_path)

    matched = registry.route_context(
        SkillRoutingContext(
            intent="生成报表",
            system_id="ifc-mom",
            project_id="backend",
            business_domains=("production",),
            repository_role="java-backend",
            stage="backend",
            artifact_types=("api",),
            risks=(),
            token_budget=200,
        )
    )
    denied = registry.route_context(
        SkillRoutingContext(
            system_id="ifc-mom",
            project_id="other",
            risks=("deployment",),
            token_budget=200,
        )
    )
    wrong_project = registry.route_context(
        SkillRoutingContext(system_id="ifc-mom", project_id="other", token_budget=200)
    )

    assert [skill.id for skill in matched] == ["reporting"]
    assert denied == []
    assert wrong_project == []


def test_skill_registry_reports_normalized_duplicates_without_deleting(tmp_path: Path) -> None:
    for skill_id in ("legacy-one", "legacy-two"):
        root = tmp_path / "business" / skill_id
        root.mkdir(parents=True)
        (root / "skill.toml").write_text(
            f'id = "{skill_id}"\ntype = "business"\nversion = "1.0.0"\n'
            'license = "Proprietary"\nrisk = "none"\ncontext_budget = 100\n'
            'required_tools = []\nsource = "legacy"\nsource_version = "1"\ntriggers = []\n'
        )
        (root / "SKILL.md").write_text("---\nname: legacy\n---\n\n# 生产报表\n\n核对业务口径。\n")

    registry = SkillRegistry(tmp_path)

    assert registry.verify().ok
    assert registry.duplicates().data["groups"] == [["legacy-one", "legacy-two"]]
    assert len(registry.all()) == 2
    assert [skill.id for skill in registry.search("生产报表")] == ["legacy-one", "legacy-two"]
