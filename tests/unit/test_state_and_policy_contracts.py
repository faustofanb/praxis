from __future__ import annotations

from conftest import read_json, run_praxis


def test_quick_task_lifecycle_persists_state_and_rejects_duplicate_ids(tmp_path):
    run_praxis("workspace", "init", "--profile", "base", "--json", cwd=tmp_path)
    first = run_praxis(
        "task", "quick-start", "--id", "q1", "--title", "修复按钮", "--json", cwd=tmp_path
    )
    assert first.returncode == 0
    duplicate = run_praxis(
        "task", "quick-start", "--id", "q1", "--title", "重复", "--json", cwd=tmp_path
    )
    assert duplicate.returncode != 0
    assert read_json(duplicate)["code"] == "TASK_CONFLICT"
    resumed = read_json(run_praxis("task", "resume", "q1", "--json", cwd=tmp_path))["data"]
    checked = read_json(run_praxis("task", "quick-check", "q1", "--json", cwd=tmp_path))["data"]
    assert resumed["id"] == checked["id"] == "q1"


def test_formal_requirement_lifecycle_and_transition(tmp_path):
    run_praxis("workspace", "init", "--profile", "base", "--json", cwd=tmp_path)
    formal = read_json(
        run_praxis(
            "task", "formal-start", "--id", "f1", "--title", "数据库变更", "--json", cwd=tmp_path
        )
    )["data"]
    req = read_json(
        run_praxis(
            "requirement",
            "create",
            "--id",
            "r1",
            "--task",
            formal["id"],
            "--title",
            "补充索引",
            "--json",
            cwd=tmp_path,
        )
    )["data"]
    assert req["status"] == "draft"
    transitioned = read_json(
        run_praxis(
            "requirement", "transition", "r1", "--status", "approved", "--json", cwd=tmp_path
        )
    )["data"]
    closed = read_json(run_praxis("requirement", "close", "r1", "--json", cwd=tmp_path))["data"]
    assert transitioned["status"] == "approved"
    assert closed["status"] == "closed"


def test_changed_file_classification_and_migration_upgrade():
    from praxis.changes.classifier import classify_paths

    payload = classify_paths(
        ["backend/src/main/resources/db/migration/V2__add.sql", "web/src/App.vue", "docs/a.md"]
    )
    assert payload["risk"] == "formal_required"
    assert "migration" in payload["categories"]
    assert "frontend" in payload["categories"]
    assert "docs" in payload["categories"]
