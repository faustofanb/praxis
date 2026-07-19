from __future__ import annotations

import os
import subprocess

from conftest import ROOT


def init_git_repo(path):
    subprocess.run(["git", "init"], cwd=path, check=True, stdout=subprocess.PIPE)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    (path / "README.md").write_text("fixture")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, stdout=subprocess.PIPE)


def test_worktree_service_create_reuse_and_safe_cleanup(tmp_path):
    from praxis.tasks.service import TaskService
    from praxis.workspace.service import WorkspaceService
    from praxis.worktrees.service import WorktreeService

    repo = tmp_path / "repo"
    repo.mkdir()
    init_git_repo(repo)
    WorkspaceService(tmp_path).init(
        profile_id="base", projects=[{"id": "repo", "type": "java-maven", "path": "repo"}]
    )
    TaskService(tmp_path).quick_start({"id": "t1", "title": "工作树任务"})
    service = WorktreeService(tmp_path)
    created = service.create(project_id="repo", task_id="t1")
    reused = service.reuse(project_id="repo", task_id="t1")
    assert created.path == reused.path
    (created.path / "dirty.txt").write_text("dirty")
    blocked = service.cleanup(project_id="repo", task_id="t1")
    assert blocked.ok is False
    assert blocked.code == "WORKTREE_DIRTY"


def test_process_runner_rtk_fallback_and_machine_git_bypass(tmp_path):
    from praxis.process.runner import run_command

    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    git_log = tmp_path / "git.log"
    rtk_log = tmp_path / "rtk.log"
    (fakebin / "git").write_text(f"#!/bin/sh\necho git:$@ >> {git_log}\nexit 0\n")
    (fakebin / "git").chmod(0o755)
    env = {"PATH": str(fakebin), "PRAXIS_TEST_RTK_LOG": str(rtk_log)}
    missing = run_command(["git", "status"], env=env)
    assert any(d["code"] == "RTK_FALLBACK" for d in missing.diagnostics)
    assert "status" in git_log.read_text()
    (fakebin / "rtk").write_text(f'#!/bin/sh\necho rtk:$@ >> {rtk_log}\nshift\nexec git "$@"\n')
    (fakebin / "rtk").chmod(0o755)
    run_command(["git", "status"], env=env)
    assert "rtk:git status" in rtk_log.read_text()
    run_command(["git", "status"], env=env, machine_output=True)
    assert rtk_log.read_text().count("rtk:git status") == 1


def test_platform_adapters_call_same_runtime_and_propagate_exit(tmp_path):
    fake = tmp_path / "praxis"
    capture = tmp_path / "argv.txt"
    fake.write_text(f"#!/bin/sh\nprintf '%s\\n' \"$@\" >> {capture}\nexit 7\n")
    fake.chmod(0o755)
    env = os.environ.copy()
    env["PRAXIS_BIN"] = str(fake)
    for adapter in ["codex", "claude-code", "omp"]:
        proc = subprocess.run(
            [
                "node",
                str(ROOT / "adapters" / adapter / "index.mjs"),
                "workspace",
                "check",
                "--json",
            ],
            env=env,
            text=True,
        )
        assert proc.returncode == 7
    assert capture.read_text().count("workspace") == 3
