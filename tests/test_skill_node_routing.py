from __future__ import annotations

from pathlib import Path

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
