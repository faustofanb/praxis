from __future__ import annotations

import shlex
from typing import Any

from .config import project_config
from .git_worktree import action_repo_dir
from .paths import ROOT_DIR
from .process import fail, run_exit


def list_projects(config: dict[str, Any]) -> None:
    """打印可被 task.py 分发的项目短名。"""
    for name, project in config.get("projects", {}).items():
        print(f"{name}  {project.get('label', '')}  {project.get('path', '')}")


def status_project(config: dict[str, Any], name: str, args: list[str]) -> None:
    """打印项目或需求 worktree 的 Git 状态。"""
    repo_dir = action_repo_dir(config, name, args)
    run_exit(["git", "-C", str(repo_dir), "status", "--short", "--branch"], ROOT_DIR)


def require_requirement_name_for_code_action(config: dict[str, Any], name: str, action: str, args: list[str]) -> None:
    """防止会进入或启动项目的动作在业务主仓执行。"""
    project = project_config(config, name)
    if project.get("kind") == "docs" or args:
        return
    fail(
        f"project {action} for code project {name} requires a requirement name; "
        f"run `task project -- start {name} <需求名> <用户原始需求原文>` first, "
        f"then retry `task project -- {action} {name} <需求名>`"
    )


def verify_project(config: dict[str, Any], name: str, args: list[str]) -> None:
    # verify.py 接收 --repo，这样同一个项目既能验证主工作区，也能验证需求 worktree。
    repo_dir = action_repo_dir(config, name, args)
    run_exit(["uv", "run", str(ROOT_DIR / "scripts" / "codex" / "verify.py"), name, "--repo", str(repo_dir)], ROOT_DIR)


def run_project(config: dict[str, Any], name: str, args: list[str]) -> None:
    """运行项目启动/交互脚本；后端会委托给 backend_run.py。"""
    require_requirement_name_for_code_action(config, name, "run", args)
    project = project_config(config, name)
    repo_dir = action_repo_dir(config, name, args)
    if name == "backend":
        run_exit(["uv", "run", str(ROOT_DIR / "scripts" / "codex" / "backend_run.py"), name, "--repo", str(repo_dir)], ROOT_DIR)

    run_command = project.get("run")
    if not run_command:
        fail(f"project has no run command: {name}")
    run_exit(shlex.split(run_command), repo_dir)


def shell_project(config: dict[str, Any], name: str, args: list[str]) -> None:
    """输出 cd 命令，方便用户进入项目或需求 worktree。"""
    require_requirement_name_for_code_action(config, name, "shell", args)
    print(f"cd {action_repo_dir(config, name, args)}")
