from __future__ import annotations

import sqlite3
import tomllib
from contextlib import closing
from pathlib import Path

from praxis.knowledge.requirements import RequirementService
from praxis.storage.sqlite import StateStore
from praxis.workspace.service import Project, WorkspaceService


def test_workspace_init_writes_only_schema_v2_facts(tmp_path: Path) -> None:
    result = WorkspaceService(tmp_path).init(
        workspace_id="aotu",
        product_family="ifc-manufacturing",
        vault="knowledge",
        projects=[Project("backend", "java-maven", "../backend", "main")],
    )

    assert result.ok
    payload = tomllib.loads((tmp_path / "praxis.toml").read_text())
    assert payload == {
        "schema_version": 2,
        "workspace_id": "aotu",
        "product_family": "ifc-manufacturing",
        "vault": "knowledge",
        "projects": [
            {
                "id": "backend",
                "kind": "java-maven",
                "path": "../backend",
                "default_branch": "main",
            }
        ],
    }
    assert not (tmp_path / ".praxis" / "state.db").exists()


def test_state_store_uses_sqlite_for_runtime_and_audit(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    store.set("workspace", "bootstrap", {"ready": True})
    store.audit("workspace.bootstrap", "OK", {"project": "backend"})

    assert store.get("workspace", "bootstrap") == {"ready": True}
    with closing(sqlite3.connect(tmp_path / ".praxis" / "state.db")) as database:
        tables = {row[0] for row in database.execute("select name from sqlite_master")}
        assert {"runtime_state", "audit_log"} <= tables


def test_requirement_template_preserves_request_and_context_sections(tmp_path: Path) -> None:
    WorkspaceService(tmp_path).init("aotu", "ifc-manufacturing", "knowledge", [])
    result = RequirementService(tmp_path).create(
        requirement_id="REQ-42",
        title="优化工序报表",
        request="用户原始要求：修正合金产出口径。",
        domain_tags=["manufacturing", "reporting"],
    )

    assert result.ok
    root = tmp_path / "knowledge" / "requirements" / "REQ-42"
    assert (root / "request.md").read_text().endswith("用户原始要求：修正合金产出口径。\n")
    assert 'type: "Requirement"' in (root / "request.md").read_text()
    assert "[[domains/manufacturing]]" in (root / "request.md").read_text()
    assert "manufacturing" in (root / "requirement.toml").read_text()
    assert {path.name for path in root.iterdir()} == {
        "requirement.toml",
        "request.md",
        "analysis.md",
        "plan.md",
        "progress.md",
        "artifacts",
    }
