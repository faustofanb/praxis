from __future__ import annotations

from conftest import read_json, run_praxis


def test_end_to_end_cli_flow_in_temp_workspace(tmp_path):
    (tmp_path / "app").mkdir()
    assert (
        run_praxis(
            "workspace",
            "init",
            "--profile",
            "java-vue",
            "--project",
            "app:java-maven:app",
            "--json",
            cwd=tmp_path,
        ).returncode
        == 0
    )
    assert run_praxis("workspace", "check", "--json", cwd=tmp_path).returncode == 0
    assert (
        run_praxis(
            "task", "quick-start", "--id", "q1", "--title", "普通任务", "--json", cwd=tmp_path
        ).returncode
        == 0
    )
    assert run_praxis("task", "resume", "q1", "--json", cwd=tmp_path).returncode == 0
    assert run_praxis("task", "quick-check", "q1", "--json", cwd=tmp_path).returncode == 0
    assert (
        run_praxis(
            "task", "formal-start", "--id", "f1", "--title", "正式任务", "--json", cwd=tmp_path
        ).returncode
        == 0
    )
    assert (
        run_praxis(
            "requirement",
            "create",
            "--id",
            "r1",
            "--task",
            "f1",
            "--title",
            "正式需求",
            "--json",
            cwd=tmp_path,
        ).returncode
        == 0
    )
    assert (
        run_praxis(
            "requirement", "transition", "r1", "--status", "approved", "--json", cwd=tmp_path
        ).returncode
        == 0
    )
    classify = read_json(
        run_praxis(
            "verify",
            "run",
            "--changed-file",
            "backend/src/main/resources/db/migration/V3__x.sql",
            "--json",
            cwd=tmp_path,
        )
    )["data"]["classification"]
    assert classify["risk"] == "formal_required"
    assert run_praxis("verify", "run", "--json", cwd=tmp_path).returncode == 0
    assert run_praxis("delivery", "prepare", "--json", cwd=tmp_path).returncode == 0


def test_required_verification_failure_blocks_delivery(tmp_path):
    run_praxis("workspace", "init", "--profile", "base", "--json", cwd=tmp_path)
    proc = run_praxis("delivery", "prepare", "--require-check", "missing", "--json", cwd=tmp_path)
    assert proc.returncode != 0
    assert read_json(proc)["code"] == "DELIVERY_BLOCKED"
