from __future__ import annotations

from pathlib import Path

from praxis.skills.routing import NodeSkillRouter, NodeSkillRoutingRequest
from praxis.workspace.service import WorkspaceService

_EXPECTED_MATT_ROUTING: dict[str, set[str]] = {
    "code-review": {"verifying"},
    "implement": {"in_progress"},
    "diagnosing-bugs": {"investigating", "in_progress", "verifying"},
    "resolving-merge-conflicts": {"in_progress"},
    "ask-matt": {"captured", "investigating"},
}


def test_installed_matt_skills_have_conditional_routing_policies() -> None:
    policies = {policy.id: policy for policy in NodeSkillRouter.policies()}

    for skill_id, nodes in _EXPECTED_MATT_ROUTING.items():
        assert skill_id in policies, skill_id
        policy = policies[skill_id]
        assert set(policy.nodes) == nodes, skill_id
        assert policy.mode == "conditional", skill_id
        assert policy.intent_triggers, skill_id


def test_route_returns_matt_skills_for_matching_intent(tmp_path: Path) -> None:
    WorkspaceService(tmp_path).init("demo", "演示工作空间")

    result = NodeSkillRouter(tmp_path).route(
        NodeSkillRoutingRequest(node="verifying", intent="最终 diff 需要代码审查 review")
    )

    assert result.ok
    decisions = {decision["id"]: decision for decision in result.data["decisions"]}
    assert "code-review" in decisions
