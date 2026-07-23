from __future__ import annotations

import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from time import sleep

from praxis.agents.lifecycle import AgentLifecycle
from praxis.agents.service import AgentSessionService
from praxis.artifacts.service import ArtifactService
from praxis.mcp.broker import McpBrokerService
from praxis.result import Result
from praxis.storage.sqlite import StateStore
from praxis.workspace.service import Project, WorkspaceService


def _workspace(root: Path) -> str:
    WorkspaceService(root).init("demo", "演示工作空间")
    requirement = StateStore(root).create_requirement("报表查询优化", "原始需求", [], [])
    return requirement["requirement_id"]


def test_mcp_grants_are_session_scoped_and_apply_risk_policy(tmp_path: Path) -> None:
    requirement_id = _workspace(tmp_path)
    broker = McpBrokerService(tmp_path)

    grant = broker.grant(
        "SES-TEST",
        "database",
        ["requirement.read", "database.query", "database.write", "deployment.execute"],
        requirement_id=requirement_id,
        worktree="req/example",
        approved_external=False,
    )

    assert grant.data["allowed_capabilities"] == ["database.query", "requirement.read"]
    assert grant.data["denied_capabilities"] == ["database.write", "deployment.execute"]


def test_mcp_registry_renders_only_approved_session_capabilities(tmp_path: Path) -> None:
    requirement_id = _workspace(tmp_path)
    broker = McpBrokerService(tmp_path)
    broker.grant(
        "SES-READ",
        "investigator",
        ["database.query"],
        requirement_id=requirement_id,
    )
    broker.register_server(
        "dbx",
        ["dbx"],
        ["database.query", "database.write"],
        "external_write",
        approved=True,
    )

    rendered = broker.render("SES-READ")

    assert rendered.ok
    assert rendered.data["servers"]["dbx"]["capabilities"] == ["database.query"]
    assert Path(rendered.data["path"]).is_file()


def test_mcp_broker_blocks_ungranted_invocation_before_dispatch(tmp_path: Path) -> None:
    requirement_id = _workspace(tmp_path)
    calls: list[tuple[str, dict[str, object]]] = []

    def execute(operation: str, arguments: dict[str, object]) -> Result:
        calls.append((operation, arguments))
        return Result(True, data={"operation": operation})

    broker = McpBrokerService(tmp_path, execute=execute)
    broker.grant(
        "SES-TEST",
        "investigator",
        ["requirement.read"],
        requirement_id=requirement_id,
    )

    blocked = broker.invoke("SES-TEST", "database.write", {"sql": "update x set y=1"})
    allowed = broker.invoke(
        "SES-TEST", "requirement.read", {"requirement_id": requirement_id}
    )

    assert blocked.code == "MCP_CAPABILITY_DENIED"
    assert allowed.ok
    assert calls == [("requirement.show", {"requirement_id": requirement_id})]


def test_skill_capabilities_cannot_cross_requirement_scope(tmp_path: Path) -> None:
    requirement_id = _workspace(tmp_path)
    other = StateStore(tmp_path).create_requirement("另一个需求", "隔离范围", [], [])
    broker = McpBrokerService(tmp_path)
    broker.grant(
        "SES-SKILL",
        "investigator",
        ["skill.plan", "skill.invoke", "skill.complete", "skill.gate"],
        requirement_id=requirement_id,
    )

    result = broker.authorize(
        "SES-SKILL",
        "skill.plan",
        {"requirement_id": other["requirement_id"], "node": "investigating"},
    )

    assert result.code == "MCP_REQUIREMENT_SCOPE_MISMATCH"


def test_database_write_grant_still_cannot_bypass_sql_gate(tmp_path: Path) -> None:
    requirement_id = _workspace(tmp_path)
    store = StateStore(tmp_path)
    store.set(
        "worktree",
        "req/database",
        {
            "requirement_id": requirement_id,
            "stage": "database",
            "allowed_paths": ["**"],
            "forbidden_paths": [".env"],
        },
    )
    broker = McpBrokerService(tmp_path)
    broker.grant(
        "SES-DB",
        "database",
        ["database.write"],
        requirement_id=requirement_id,
        worktree="req/database",
        approved_external=True,
    )

    result = broker.authorize(
        "SES-DB", "database.write", {"sql": "delete from orders"}
    )

    assert result.code == "SQL_WHERE_REQUIRED"


def test_agent_configs_are_thin_and_share_session_grant(tmp_path: Path) -> None:
    requirement_id = _workspace(tmp_path)
    store = StateStore(tmp_path)
    store.set("context", "CTX-TEST", {"context_id": "CTX-TEST", "path": "context.md"})
    store.set(
        "worktree",
        "req/example",
        {
            "requirement_id": requirement_id,
            "branch": "req/example",
            "path": str(tmp_path / "worktree"),
        },
    )
    sessions = AgentSessionService(tmp_path)

    for agent_type in ("codex", "claude-code", "oh-my-pi"):
        started = sessions.start(
            agent_type,
            "coder",
            requirement_id,
            "CTX-TEST",
            "req/example",
            ["requirement.read", "artifact.register"],
        )
        rendered = sessions.render(started.data["session_id"])
        content = Path(rendered.data["files"][0]).read_text()
        assert started.ok and rendered.ok
        assert started.data["grant_id"]
        assert "Praxis" in content or "praxis" in content
        assert "SQL_WHERE_REQUIRED" not in content
        assert "GATE_PATH_OUT_OF_SCOPE" not in content

        receipt = sessions.receipt(
            started.data["session_id"],
            changed_paths=["src/app.py", "src/app.py"],
            decisions=["复用现有服务"],
            blockers=[],
            follow_up="父会话继续门禁",
        )
        assert receipt.ok
        assert receipt.data["changed_paths"] == ["src/app.py"]


def test_agent_install_and_safe_launch_create_workspace_owned_descriptors(
    tmp_path: Path,
) -> None:
    requirement_id = _workspace(tmp_path)
    store = StateStore(tmp_path)
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    store.set("context", "CTX-TEST", {"context_id": "CTX-TEST", "path": "context.md"})
    store.set(
        "worktree",
        "req/example",
        {
            "requirement_id": requirement_id,
            "branch": "req/example",
            "path": str(worktree),
        },
    )
    sessions = AgentSessionService(tmp_path)

    installed = sessions.install("codex")
    started = sessions.start(
        "codex",
        "coder",
        requirement_id,
        "CTX-TEST",
        "req/example",
        ["requirement.read"],
    )
    launched = sessions.launch(started.data["session_id"])

    assert installed.ok
    assert Path(installed.data["path"]).is_file()
    assert launched.ok
    assert launched.data["executed"] is False
    assert launched.data["command"][0] == "codex"
    assert "handoff" in launched.data["command"][1]
    assert launched.data["cwd"] == str(worktree)
    assert launched.data["config_files"]
    stored = store.get("agent_session", started.data["session_id"])
    assert stored and stored["status"] == "ready"


def test_agent_start_infers_project_and_builds_context_when_context_is_omitted(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "backend"
    repository.mkdir()
    WorkspaceService(tmp_path).init(
        "demo",
        "演示工作空间",
        projects=[
            Project(
                "backend",
                "python",
                "backend",
                "main",
                database_connections=("dbx://LOCAL/demo",),
            )
        ],
    )
    requirement_id = StateStore(tmp_path).create_requirement(
        "自动上下文", "Agent 必须读取数据库事实", ["demo"], []
    )["requirement_id"]
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    store = StateStore(tmp_path)
    store.set(
        "worktree",
        "WT-AUTO",
        {
            "binding_id": "WT-AUTO",
            "requirement_id": requirement_id,
            "repository_id": "backend",
            "stage": "development",
            "branch": "req/auto",
            "path": str(worktree),
            "allowed_paths": ["**"],
            "forbidden_paths": [".env"],
        },
    )

    sessions = AgentSessionService(tmp_path)
    started = sessions.start(
        "codex",
        "coder",
        requirement_id,
        "",
        "WT-AUTO",
        ["requirement.read"],
        intent="修复上下文自动消费",
    )
    rendered = sessions.render(started.data["session_id"])
    handoff = Path(rendered.data["files"][1]).read_text()

    assert started.ok
    context = store.get("context", started.data["context_id"])
    assert context and context["project_id"] == "backend"
    assert "dbx://LOCAL/demo" in handoff
    assert "critical_facts" in handoff


def test_agent_lifecycle_delegates_authorization_and_records_completion(tmp_path: Path) -> None:
    requirement_id = _workspace(tmp_path)
    store = StateStore(tmp_path)
    store.set(
        "worktree",
        "req/example",
        {
            "requirement_id": requirement_id,
            "path": str(tmp_path / "worktree"),
            "allowed_paths": ["src/**"],
            "forbidden_paths": [".env"],
        },
    )
    store.set("agent_session", "SES-HOOK", {"session_id": "SES-HOOK", "status": "ready"})
    McpBrokerService(tmp_path).grant(
        "SES-HOOK",
        "coder",
        ["artifact.register"],
        requirement_id=requirement_id,
        worktree="req/example",
    )
    lifecycle = AgentLifecycle(tmp_path)

    allowed = lifecycle.run(
        "before-tool",
        {
            "session_id": "SES-HOOK",
            "capability": "artifact.register",
            "arguments": {"paths": ["src/report.py"]},
        },
    )
    blocked = lifecycle.run(
        "before-tool",
        {
            "session_id": "SES-HOOK",
            "capability": "artifact.register",
            "arguments": {"paths": [".env"]},
        },
    )
    completed = lifecycle.run(
        "after-tool",
        {"session_id": "SES-HOOK", "capability": "artifact.register", "code": "OK"},
    )
    stopped = lifecycle.run("session-stop", {"session_id": "SES-HOOK"})

    assert allowed.ok
    assert blocked.code == "GATE_PATH_OUT_OF_SCOPE"
    assert completed.data["audit_id"].startswith("AUD-")
    assert stopped.data["status"] == "completed"


def test_artifact_registration_indexes_and_verifies_content(tmp_path: Path) -> None:
    requirement_id = _workspace(tmp_path)
    report = tmp_path / "test-report.txt"
    report.write_text("108 tests passed")
    artifacts = ArtifactService(tmp_path)

    added = artifacts.add(requirement_id, "test-report", report, stage="verify")

    assert added.ok
    report.write_text("109 tests passed")
    refreshed = artifacts.add(requirement_id, "test-report", report, stage="verify")
    assert refreshed.code == "ARTIFACT_REFRESHED"
    assert refreshed.data["artifact_id"] == added.data["artifact_id"]
    assert artifacts.list(requirement_id).data["artifacts"][0]["artifact_id"] == added.data[
        "artifact_id"
    ]
    assert artifacts.verify(added.data["artifact_id"]).ok
    report.write_text("tampered")
    verified = artifacts.verify(added.data["artifact_id"])
    assert verified.ok
    assert verified.data["source_status"] == "changed"
    archived = Path(added.data["archived_path"])
    assert archived.read_text() == "109 tests passed"
    report.unlink()
    assert artifacts.verify(added.data["artifact_id"]).ok
    index = next((tmp_path / "知识库" / "需求").rglob("09-产出物清单.yaml"))
    assert added.data["artifact_id"] in index.read_text()
    assert str(archived) in index.read_text()


def test_code_change_artifact_captures_git_diff_and_changed_file_hashes(
    tmp_path: Path,
) -> None:
    requirement_id = _workspace(tmp_path)
    subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "praxis@example.invalid"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Praxis Tests"], cwd=tmp_path, check=True
    )
    source = tmp_path / "service.py"
    source.write_text("value = 1\n")
    subprocess.run(["git", "add", "service.py"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "baseline"], cwd=tmp_path, check=True)
    source.write_text("value = 2\n")

    added = ArtifactService(tmp_path).add(
        requirement_id, "code-change", source, stage="development"
    )

    assert added.ok
    change = added.data["metadata"]["code_change"]
    assert change["repository"] == str(tmp_path.resolve())
    assert change["branch"] == "main"
    assert change["diff"] == {"files": 1, "insertions": 1, "deletions": 1}
    assert change["files"] == [
        {
            "path": "service.py",
            "content_hash": added.data["content_hash"],
        }
    ]
    manifest = Path(added.data["archived_path"])
    assert manifest.parent.name == "代码变更"
    assert manifest.suffix == ".json"
    assert '"repository"' in manifest.read_text()


def test_audit_events_can_be_listed_shown_and_chain_verified(tmp_path: Path) -> None:
    _workspace(tmp_path)
    store = StateStore(tmp_path)
    audit_id = store.audit("demo.event", "OK", {"value": 1})
    event = store.audit_event(audit_id)

    assert event and event["event"] == "demo.event"
    assert any(item["audit_id"] == audit_id for item in store.audit_events())
    assert store.verify_audit_chain()


def test_concurrent_audit_appends_preserve_single_hash_chain(
    tmp_path: Path, monkeypatch
) -> None:
    _workspace(tmp_path)
    original_hash = StateStore._event_hash
    first_call = True
    first_call_lock = Lock()

    def delay_first_append(
        previous_hash: str | None,
        event: str,
        code: str,
        details: str,
        created_at: str,
    ) -> str:
        nonlocal first_call
        delay = False
        if event == "concurrent.event":
            with first_call_lock:
                if first_call:
                    first_call = False
                    delay = True
        if delay:
            sleep(0.1)
        return original_hash(previous_hash, event, code, details, created_at)

    monkeypatch.setattr(StateStore, "_event_hash", staticmethod(delay_first_append))

    with ThreadPoolExecutor(max_workers=2) as executor:
        audit_ids = list(
            executor.map(
                lambda value: StateStore(tmp_path).audit(
                    "concurrent.event", "OK", {"value": value}
                ),
                range(2),
            )
        )

    assert len(set(audit_ids)) == 2
    assert StateStore(tmp_path).verify_audit_chain()
