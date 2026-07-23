from __future__ import annotations

from pathlib import Path

from praxis.domain.requirement import RequirementStatus
from praxis.knowledge.requirements import RequirementService
from praxis.skills.routing import (
    NodeSkillRouter,
    NodeSkillRoutingRequest,
    SkillInvocationService,
)
from praxis.storage.sqlite import StateStore
from praxis.workspace.service import Project, WorkspaceService


def _workspace(root: Path) -> None:
    repository = root / "backend"
    repository.mkdir()
    WorkspaceService(root).init(
        "demo",
        "演示工作空间",
        projects=[
            Project(
                "backend",
                "java-maven",
                "backend",
                "local",
                template_branches=("develop",),
            )
        ],
    )


def test_investigating_node_routes_required_and_contextual_skills(tmp_path: Path) -> None:
    _workspace(tmp_path)

    result = NodeSkillRouter(tmp_path).route(
        NodeSkillRoutingRequest(
            node="investigating",
            intent="调查 Java 代码中的数据库 SQL 缺陷并定位影响范围",
            requirement_id="REQ-TEST",
            project_id="backend",
            system_id="demo",
            repository_kind="java-maven",
            agent_role="investigator",
            available_skills=(
                "brainstorming",
                "grilling",
                "file-search",
                "systematic-debugging",
            ),
            token_budget=5_000,
        )
    )

    assert result.ok
    decisions = {item["id"]: item for item in result.data["decisions"]}
    assert decisions["praxis-requirement-workflow"]["status"] == "available"
    assert decisions["brainstorming"]["mode"] == "required"
    assert decisions["grilling"]["mode"] == "required"
    assert decisions["ponytail"]["status"] == "available"
    assert decisions["file-search"]["reasons"] == [
        "node:investigating",
        "intent",
        "role:investigator",
    ]
    assert decisions["systematic-debugging"]["status"] == "available"
    assert decisions["dbx-database-investigation"]["status"] == "available"
    assert "code-quality-review" not in decisions


def test_node_alias_is_canonicalized_and_unknown_node_is_rejected(tmp_path: Path) -> None:
    _workspace(tmp_path)

    aliased = NodeSkillRouter(tmp_path).route(
        NodeSkillRoutingRequest(
            node="investigation",
            requirement_id="REQ-ALIAS",
            available_skills=("brainstorming", "grilling"),
            token_budget=4_000,
        )
    )
    unknown = NodeSkillRouter(tmp_path).route(
        NodeSkillRoutingRequest(node="invented", requirement_id="REQ-BAD")
    )

    assert aliased.ok
    assert aliased.data["node"] == "investigating"
    assert StateStore(tmp_path).get("skill_route", "REQ-ALIAS:investigating")
    required = {
        item["id"]
        for item in aliased.data["decisions"]
        if item["mode"] == "required"
    }
    completed = SkillInvocationService(tmp_path).complete_node(
        "REQ-ALIAS",
        "investigation",
        {skill_id: "alias completed" for skill_id in required},
    )
    assert completed.ok
    assert completed.data["node"] == "investigating"
    assert not unknown.ok
    assert unknown.code == "SKILL_NODE_INVALID"


def test_default_budget_reserves_context_for_matching_business_skill(tmp_path: Path) -> None:
    _workspace(tmp_path)
    skill = tmp_path / "知识库" / "skills" / "business" / "business.demo.backend.development"
    skill.mkdir(parents=True)
    (skill / "skill.toml").write_text(
        'id = "business.demo.backend.development"\n'
        'type = "business"\nversion = "1.0.0"\nlicense = "Proprietary"\n'
        'risk = "none"\ncontext_budget = 500\nrequired_tools = []\n'
        'source = "test"\nsource_version = "1"\ntriggers = ["backend"]\n'
        'systems = ["demo"]\nprojects = ["backend"]\n'
        'repository_roles = ["java-maven"]\n'
    )
    (skill / "SKILL.md").write_text("# Backend business context\n")

    result = NodeSkillRouter(tmp_path).route(
        NodeSkillRoutingRequest(
            node="investigating",
            intent="回归缺陷并定位代码",
            project_id="backend",
            system_id="demo",
            repository_kind="java-maven",
            agent_role="investigator",
            available_skills=(
                "brainstorming",
                "grilling",
                "systematic-debugging",
                "file-search",
            ),
            token_budget=4_000,
        )
    )

    decisions = {item["id"]: item for item in result.data["decisions"]}
    assert decisions["business.demo.backend.development"]["status"] == "available"
    assert decisions["file-search"]["status"] == "omitted_budget"
    assert result.data["used_budget"] == 4_000


def test_approved_and_required_skills_are_never_omitted_by_budget(
    tmp_path: Path,
) -> None:
    _workspace(tmp_path)

    result = NodeSkillRouter(tmp_path).route(
        NodeSkillRoutingRequest(
            node="in_progress",
            intent="编写测试并实现修复",
            requirement_id="REQ-BUDGET",
            available_skills=(
                "test-driven-development",
                "Testing Writing Guidelines",
            ),
            approved_skills=("Testing Writing Guidelines",),
            token_budget=100,
        )
    )

    decisions = {item["id"]: item for item in result.data["decisions"]}
    protected = {
        "praxis-requirement-workflow",
        "ponytail",
        "test-driven-development",
        "minimum-module-compile",
        "Testing Writing Guidelines",
    }
    assert {decisions[skill_id]["status"] for skill_id in protected} == {"available"}
    assert result.data["protected_budget"] > result.data["context_budget"]
    assert result.data["budget_shortfall"] == (
        result.data["protected_budget"] - result.data["context_budget"]
    )


def test_business_skill_requires_project_and_intent_but_development_stays_automatic(
    tmp_path: Path,
) -> None:
    _workspace(tmp_path)
    catalog = tmp_path / "知识库" / "skills" / "business"
    specialized = catalog / "business.demo.backend.uniapp-api-generation"
    specialized.mkdir(parents=True)
    (specialized / "skill.toml").write_text(
        'id = "business.demo.backend.uniapp-api-generation"\n'
        'type = "business"\nversion = "1.0.0"\nlicense = "Proprietary"\n'
        'risk = "generated-code"\ncontext_budget = 400\nrequired_tools = []\n'
        'source = "test"\nsource_version = "1"\n'
        'triggers = ["openapi", "接口生成"]\n'
        'systems = ["demo"]\nprojects = ["backend"]\n'
        'repository_roles = ["java-maven"]\n'
    )
    (specialized / "SKILL.md").write_text("# UniApp API generation\n")
    development = catalog / "business.demo.backend.development"
    development.mkdir(parents=True)
    (development / "skill.toml").write_text(
        'id = "business.demo.backend.development"\n'
        'type = "business"\nversion = "1.0.0"\nlicense = "Proprietary"\n'
        'risk = "none"\ncontext_budget = 400\nrequired_tools = []\n'
        'source = "test"\nsource_version = "1"\ntriggers = ["backend"]\n'
        'systems = ["demo"]\nprojects = ["backend"]\n'
        'repository_roles = ["java-maven"]\n'
    )
    (development / "SKILL.md").write_text("# Backend development\n")

    unrelated = NodeSkillRouter(tmp_path).route(
        NodeSkillRoutingRequest(
            node="in_progress",
            intent="调整页面布局",
            project_id="backend",
            system_id="demo",
            repository_kind="java-maven",
            token_budget=4_000,
        )
    )
    matching = NodeSkillRouter(tmp_path).route(
        NodeSkillRoutingRequest(
            node="in_progress",
            intent="根据 OpenAPI 完成接口生成",
            project_id="backend",
            system_id="demo",
            repository_kind="java-maven",
            token_budget=4_000,
        )
    )
    wrong_system = NodeSkillRouter(tmp_path).route(
        NodeSkillRoutingRequest(
            node="in_progress",
            intent="根据 OpenAPI 完成接口生成",
            project_id="backend",
            system_id="other",
            repository_kind="java-maven",
            token_budget=4_000,
        )
    )

    unrelated_decisions = {item["id"]: item for item in unrelated.data["decisions"]}
    matching_decisions = {item["id"]: item for item in matching.data["decisions"]}
    wrong_system_decisions = {
        item["id"]: item for item in wrong_system.data["decisions"]
    }
    assert "business.demo.backend.uniapp-api-generation" not in unrelated_decisions
    assert "business.demo.backend.development" in unrelated_decisions
    assert "business.demo.backend.uniapp-api-generation" not in wrong_system_decisions
    assert "business.demo.backend.development" not in wrong_system_decisions
    specialized_decision = matching_decisions[
        "business.demo.backend.uniapp-api-generation"
    ]
    assert specialized_decision["intent_triggers"] == ["openapi", "接口生成"]
    assert specialized_decision["reasons"] == ["business-context", "intent"]


def test_installed_skill_is_discovered_with_content_hash(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    skill = home / ".codex" / "skills" / "external-brainstorming" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: brainstorming\n---\n\n# Brainstorming\n")
    grilling = home / ".codex" / "skills" / "grilling" / "SKILL.md"
    grilling.parent.mkdir(parents=True)
    grilling.write_text("---\nname: grilling\n---\n\n# Grilling\n")
    monkeypatch.setattr(Path, "home", lambda: home)
    _workspace(tmp_path)

    result = NodeSkillRouter(tmp_path).route(
        NodeSkillRoutingRequest(
            node="investigating",
            requirement_id="REQ-TEST",
            token_budget=5_000,
        )
    )

    assert result.ok
    decision = next(
        item for item in result.data["decisions"] if item["id"] == "brainstorming"
    )
    assert decision["status"] == "available"
    assert decision["content_hash"]
    assert decision["installed_path"] == str(skill)


def test_skilldock_skill_is_discovered(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    skill = home / ".skilldock" / "skills" / "karpathy-guidelines" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: karpathy-guidelines\n---\n\n# Guidelines\n")
    monkeypatch.setattr(Path, "home", lambda: home)
    _workspace(tmp_path)

    result = NodeSkillRouter(tmp_path).route(
        NodeSkillRoutingRequest(
            node="in_progress",
            intent="修复 Python 实现",
            token_budget=5_000,
        )
    )

    decision = next(
        item for item in result.data["decisions"] if item["id"] == "karpathy-guidelines"
    )
    assert decision["status"] == "available"
    assert decision["installed_path"] == str(skill)


def test_development_routes_tdd_and_minimum_compile_as_required_by_default(
    tmp_path: Path,
) -> None:
    _workspace(tmp_path)

    result = NodeSkillRouter(tmp_path).route(
        NodeSkillRoutingRequest(
            node="in_progress",
            intent="实现订单状态修复",
            requirement_id="REQ-TDD",
            project_id="backend",
            available_skills=("test-driven-development",),
            token_budget=5_000,
        )
    )

    assert result.ok
    decision = next(
        item
        for item in result.data["decisions"]
        if item["id"] == "test-driven-development"
    )
    assert decision["mode"] == "required"
    assert decision["status"] == "available"
    assert decision["reasons"] == ["node:in_progress"]
    compile_decision = next(
        item
        for item in result.data["decisions"]
        if item["id"] == "minimum-module-compile"
    )
    assert compile_decision["mode"] == "required"
    assert compile_decision["status"] == "available"
    assert compile_decision["availability"] == "bundled"
    assert compile_decision["reasons"] == ["node:in_progress"]
    gate = SkillInvocationService(tmp_path).gate("REQ-TDD", "in_progress")
    assert "test-driven-development" in gate.data["missing"]
    assert "minimum-module-compile" in gate.data["missing"]


def test_high_risk_change_routes_codegraph_before_development(tmp_path: Path) -> None:
    _workspace(tmp_path)

    result = NodeSkillRouter(tmp_path).route(
        NodeSkillRoutingRequest(
            node="in_progress",
            intent="修改共享事务和锁，核对调用链影响范围",
            requirement_id="REQ-GRAPH",
            project_id="backend",
            repository_kind="java-maven",
            risks=("transaction", "shared-code"),
            available_skills=("test-driven-development",),
            token_budget=6_000,
        )
    )

    decisions = {item["id"]: item for item in result.data["decisions"]}
    assert "codegraph-impact-analysis" in decisions
    decision = decisions["codegraph-impact-analysis"]
    assert decision["mode"] == "conditional_required"
    assert decision["availability"] == "bundled"
    assert decision["status"] == "available"
    assert "intent" in decision["reasons"]
    assert "risk" in decision["reasons"]
    assert "codegraph-impact-analysis" in SkillInvocationService(
        tmp_path
    ).gate("REQ-GRAPH", "in_progress").data["missing"]


def test_skill_invocation_gate_requires_completed_evidence(tmp_path: Path) -> None:
    _workspace(tmp_path)
    router = NodeSkillRouter(tmp_path)
    route = router.route(
        NodeSkillRoutingRequest(
            node="investigating",
            intent="调查需求",
            requirement_id="REQ-TEST",
            available_skills=("brainstorming",),
            token_budget=5_000,
        )
    )
    assert route.ok
    invocations = SkillInvocationService(tmp_path)

    blocked = invocations.gate("REQ-TEST", "investigating")
    assert blocked.code == "SKILL_NODE_GATE_BLOCKED"
    assert blocked.data["missing"] == [
        "brainstorming",
        "grilling",
        "ponytail",
        "praxis-requirement-workflow",
    ]
    assert blocked.data["audit_id"]

    invocation_ids = []
    for skill_id in blocked.data["missing"]:
        started = invocations.start("REQ-TEST", "investigating", skill_id)
        assert started.ok
        invocation_ids.append(started.data["invocation_id"])
        completed = invocations.complete(
            started.data["invocation_id"], outcome="需求边界已逐项确认"
        )
        assert completed.ok
        assert completed.data["status"] == "completed"
        assert completed.data["outcome"] == "需求边界已逐项确认"

    passed = invocations.gate("REQ-TEST", "investigating")
    assert passed.ok
    assert passed.data["audit_id"]

    legacy = invocations.store.get("skill_invocation", invocation_ids[0])
    assert legacy is not None
    legacy["status"] = legacy.pop("outcome")
    invocations.store.set("skill_invocation", invocation_ids[0], legacy)
    assert invocations.gate("REQ-TEST", "investigating").ok


def test_complete_node_records_required_skill_lifecycle_in_one_call(tmp_path: Path) -> None:
    _workspace(tmp_path)
    route = NodeSkillRouter(tmp_path).route(
        NodeSkillRoutingRequest(
            node="investigating",
            intent="调查需求",
            requirement_id="REQ-TEST",
            available_skills=("brainstorming", "grilling"),
            token_budget=5_000,
        )
    )
    required = {
        item["id"]
        for item in route.data["decisions"]
        if item["mode"] == "required"
    }

    result = SkillInvocationService(tmp_path).complete_node(
        "REQ-TEST",
        "investigating",
        {skill_id: f"已使用 {skill_id} 完成调查" for skill_id in required},
    )

    assert result.ok
    assert {item["skill_id"] for item in result.data["completed"]} == required
    assert result.data["gate"]["missing"] == []


def test_lifecycle_complete_node_rolls_back_partial_skill_records(
    tmp_path: Path,
) -> None:
    _workspace(tmp_path)
    route = NodeSkillRouter(tmp_path).route(
        NodeSkillRoutingRequest(
            node="in_progress",
            intent="编写测试",
            requirement_id="REQ-ATOMIC",
            available_skills=(
                "test-driven-development",
                "Testing Writing Guidelines",
            ),
            token_budget=8_000,
        )
    )
    required = sorted(
        item["id"]
        for item in route.data["decisions"]
        if item["mode"] == "required"
    )
    results = {
        skill_id: {"result": "passed", "details": f"{skill_id} used"}
        for skill_id in required
    }
    results["Testing Writing Guidelines"] = {
        "result": "passed",
        "details": "approval was not supplied",
    }

    completed = SkillInvocationService(tmp_path).complete_node(
        "REQ-ATOMIC",
        "in_progress",
        results,
        structured=True,
        advance=True,
    )

    assert not completed.ok
    assert completed.code == "USER_APPROVAL_REQUIRED"
    assert [
        item
        for item in StateStore(tmp_path).list_scope("skill_invocation")
        if item.get("requirement_id") == "REQ-ATOMIC"
    ] == []


def test_approval_missing_keeps_implementation_complete_and_verification_pending(
    tmp_path: Path,
) -> None:
    _workspace(tmp_path)
    requirements = RequirementService(tmp_path)
    created = requirements.create("验证待批准", "实施完成但编译未获批准", [], [])
    requirement_id = created.data["requirement_id"]
    store = StateStore(tmp_path)
    for status in (
        RequirementStatus.INVESTIGATING,
        RequirementStatus.ANALYZED,
        RequirementStatus.PLANNED,
        RequirementStatus.READY,
        RequirementStatus.IN_PROGRESS,
    ):
        store.transition_requirement(requirement_id, status)
    requirements.record_implementation(requirement_id, "backend")
    route = NodeSkillRouter(tmp_path).route(
        NodeSkillRoutingRequest(
            node="in_progress",
            intent="实现代码",
            requirement_id=requirement_id,
            available_skills=("test-driven-development",),
            token_budget=8_000,
        )
    )
    required = {
        item["id"]
        for item in route.data["decisions"]
        if item["mode"] == "required"
    }
    results = {
        skill_id: {"result": "passed", "details": f"{skill_id} used"}
        for skill_id in required
    }
    results["minimum-module-compile"] = {
        "result": "approval_missing",
        "details": "compile command is awaiting approval",
    }

    completed = SkillInvocationService(tmp_path).complete_node(
        requirement_id,
        "in_progress",
        results,
        structured=True,
        advance=True,
    )

    assert completed.ok
    assert completed.code == "IMPLEMENTATION_COMPLETE_VERIFICATION_PENDING_APPROVAL"
    assert requirements.show(requirement_id).data["status"] == "implemented"
    assert completed.data["gate"]["approval_missing"] == ["minimum-module-compile"]
    invocation = next(
        item
        for item in store.list_scope("skill_invocation")
        if item["skill_id"] == "minimum-module-compile"
    )
    assert invocation["status"] == "approval_missing"
    assert "completed_at" not in invocation


def test_skill_gate_missing_route_is_audited(tmp_path: Path) -> None:
    _workspace(tmp_path)

    result = SkillInvocationService(tmp_path).gate("REQ-MISSING", "ready")

    assert not result.ok
    assert result.code == "SKILL_ROUTE_NOT_FOUND"
    assert result.data["audit_id"]
    event = StateStore(tmp_path).audit_events()[-1]
    assert event["event"] == "skill.gate"
    assert event["code"] == "SKILL_ROUTE_NOT_FOUND"
    assert event["details"]["requirement_id"] == "REQ-MISSING"


def test_java_standards_require_java_repository_and_code_change_intent(tmp_path: Path) -> None:
    _workspace(tmp_path)
    available = ("java-coding-standards",)

    workflow_only = NodeSkillRouter(tmp_path).route(
        NodeSkillRoutingRequest(
            node="in_progress",
            intent="重跑工作流门禁",
            repository_kind="java-maven",
            available_skills=available,
            token_budget=5_000,
        )
    )
    java_change = NodeSkillRouter(tmp_path).route(
        NodeSkillRoutingRequest(
            node="in_progress",
            intent="修改 Java 代码实现接口",
            repository_kind="java-maven",
            available_skills=available,
            token_budget=5_000,
        )
    )

    assert "java-coding-standards" not in {
        item["id"] for item in workflow_only.data["decisions"]
    }
    assert next(
        item for item in java_change.data["decisions"] if item["id"] == "java-coding-standards"
    )["reasons"] == ["node:in_progress", "intent", "repository:java-maven"]


def test_approval_skill_cannot_start_without_current_user_approval(tmp_path: Path) -> None:
    _workspace(tmp_path)
    route = NodeSkillRouter(tmp_path).route(
        NodeSkillRoutingRequest(
            node="verifying",
            intent="运行测试并进行代码审查",
            requirement_id="REQ-TEST",
            agent_role="reviewer",
            available_skills=(
                "Testing Writing Guidelines",
                "verification-before-completion",
                "code-quality-review",
                "requesting-code-review",
            ),
            token_budget=5_000,
        )
    )
    assert route.ok

    result = SkillInvocationService(tmp_path).start(
        "REQ-TEST", "verifying", "code-quality-review"
    )

    assert result.code == "USER_APPROVAL_REQUIRED"


def test_code_review_intent_routes_review_skill_for_coder_role(tmp_path: Path) -> None:
    _workspace(tmp_path)

    result = NodeSkillRouter(tmp_path).route(
        NodeSkillRoutingRequest(
            node="verifying",
            intent="只读检查最终 diff 和调用链，执行代码质量审查",
            agent_role="coder",
            available_skills=("code-quality-review",),
            token_budget=5_000,
        )
    )

    decision = next(
        item
        for item in result.data["decisions"]
        if item["id"] == "code-quality-review"
    )
    assert decision["status"] == "blocked_pending_approval"
    assert decision["reasons"] == ["node:verifying", "intent"]
    assert decision["recommended_agent_roles"] == ["reviewer"]


def test_shared_aotu_and_mom_business_skills_are_registered_by_intent(
    tmp_path: Path,
) -> None:
    _workspace(tmp_path)
    available = ("api-permission-migration", "uniapp-api-generation")

    permission = NodeSkillRouter(tmp_path).route(
        NodeSkillRoutingRequest(
            node="in_progress",
            intent="修复 MOM PDA 接口 11051 无此权限并生成 Flyway 权限迁移",
            system_id="mom",
            project_id="backend",
            available_skills=available,
            token_budget=5_000,
        )
    )
    generation = NodeSkillRouter(tmp_path).route(
        NodeSkillRoutingRequest(
            node="in_progress",
            intent="在 AOTU MES_PDA 中根据 OpenAPI 运行 alova-gen 生成接口",
            system_id="aotu",
            project_id="mes-pda",
            available_skills=available,
            token_budget=5_000,
        )
    )
    unrelated = NodeSkillRouter(tmp_path).route(
        NodeSkillRoutingRequest(
            node="in_progress",
            intent="调整移动端页面间距",
            system_id="mom",
            project_id="mes-pda",
            available_skills=available,
            token_budget=5_000,
        )
    )

    assert next(
        item
        for item in permission.data["decisions"]
        if item["id"] == "api-permission-migration"
    )["status"] == "available"
    assert next(
        item
        for item in generation.data["decisions"]
        if item["id"] == "uniapp-api-generation"
    )["status"] == "available"
    unrelated_ids = {item["id"] for item in unrelated.data["decisions"]}
    assert "api-permission-migration" not in unrelated_ids
    assert "uniapp-api-generation" not in unrelated_ids


def test_provider_diagnostics_separates_installation_policy_and_delegation(
    tmp_path: Path, monkeypatch
) -> None:
    home = tmp_path / "home"
    extra = home / ".codex" / "skills" / "unmanaged-helper" / "SKILL.md"
    extra.parent.mkdir(parents=True)
    extra.write_text("---\nname: unmanaged-helper\n---\n\n# Helper\n")
    review = home / ".codex" / "skills" / "code-quality-review" / "SKILL.md"
    review.parent.mkdir(parents=True)
    review.write_text("---\nname: code-quality-review\n---\n\n# Review\n")
    monkeypatch.setattr(Path, "home", lambda: home)
    _workspace(tmp_path)

    diagnostics = NodeSkillRouter(tmp_path).provider_diagnostics()

    assert diagnostics["installed"]["code-quality-review"]["registered"] is True
    assert diagnostics["installed"]["unmanaged-helper"]["registered"] is False
    assert "unmanaged-helper" in diagnostics["installed_without_policy"]
    assert "code-quality-review" not in diagnostics["policy_without_provider"]
    assert "api-permission-migration" not in diagnostics["delegate_without_policy"]
    assert "uniapp-api-generation" not in diagnostics["delegate_without_policy"]


def test_orca_and_obsidian_providers_are_never_discovered(
    tmp_path: Path, monkeypatch
) -> None:
    home = tmp_path / "home"
    for skill_id in ("orca-cli", "orca-per-workspace-env", "obsidian-markdown"):
        skill = home / ".codex" / "skills" / skill_id / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text(f"---\nname: {skill_id}\n---\n\n# Excluded\n")
    monkeypatch.setattr(Path, "home", lambda: home)
    _workspace(tmp_path)

    diagnostics = NodeSkillRouter(tmp_path).provider_diagnostics()

    assert diagnostics["installed"] == {}
    assert diagnostics["excluded_provider_ids"] == [
        "obsidian-markdown",
        "orca-cli",
        "orca-per-workspace-env",
    ]
