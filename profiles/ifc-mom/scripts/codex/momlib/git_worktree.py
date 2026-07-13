from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from .config import project_config, project_dir
from .docs import find_requirement_dir
from .names import branch_today, safe_branch_leaf, safe_path_leaf
from .paths import ROOT_DIR
from .process import capture, fail, run_checked


WEB_LOCAL_CONFIG_NAMES = {".env", ".env.local", ".env.development", ".npmrc"}


def is_web_local_config(path: str) -> bool:
    """判断 Web worktree 需要从主工作区同步的被忽略本地配置。"""
    name = Path(path).name
    return name in WEB_LOCAL_CONFIG_NAMES or name.startswith(".env.")


def sync_web_local_configs(repo_dir: Path, worktree_dir: Path) -> list[Path]:
    """把 Web 主工作区被 Git 忽略的本地运行配置复制到新 worktree。"""
    ignored = capture(["git", "-C", str(repo_dir), "ls-files", "--others", "--ignored", "--exclude-standard"], ROOT_DIR)
    copied: list[Path] = []
    for relative in sorted(line for line in ignored.splitlines() if is_web_local_config(line)):
        source = repo_dir / relative
        target = worktree_dir / relative
        if not source.is_file():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append(target)
    return copied


def parse_worktrees(repo_dir: Path) -> list[dict[str, str]]:
    """解析 `git worktree list --porcelain`，避免依赖人类可读输出格式。"""
    output = capture(["git", "-C", str(repo_dir), "worktree", "list", "--porcelain"], ROOT_DIR)
    worktrees: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in output.splitlines():
        if not line:
            if current:
                worktrees.append(current)
                current = {}
            continue
        key, _, value = line.partition(" ")
        current[key] = value
    if current:
        worktrees.append(current)
    return worktrees


def project_worktree_dir(config: dict[str, Any], project: str, requirement_name: str) -> Path:
    """Find the existing codex worktree for a requirement.

    Stale Git worktree entries are ignored because the directory no longer exists.
    """
    matches = project_worktree_dirs(config, project, requirement_name, include_feature=False)
    if not matches:
        fail(f"cannot find existing worktree for project {project} and requirement {requirement_name}")
    return sorted(matches, key=lambda path: path.name)[-1]


def project_worktree_dirs(config: dict[str, Any], project: str, requirement_name: str, include_feature: bool) -> list[Path]:
    """Find registered worktrees for one requirement.

    Branch matching keeps compatibility with old docs-local worktree paths while
    allowing the current centralized .worktrees layout.
    """
    repo_dir = project_dir(config, project)
    suffix = f"-{safe_branch_leaf(requirement_name)}"
    feature_branch = f"refs/heads/feature/{safe_branch_leaf(requirement_name)}"
    matches: list[Path] = []
    for item in parse_worktrees(repo_dir):
        branch = item.get("branch", "")
        path = item.get("worktree")
        if not path:
            continue
        worktree_path = Path(path)
        if not worktree_path.is_dir():
            continue
        if branch.startswith("refs/heads/codex/") and branch.endswith(suffix):
            matches.append(worktree_path)
        elif include_feature and branch == feature_branch:
            matches.append(worktree_path)
    return sorted(matches, key=lambda path: str(path))


def action_repo_dir(config: dict[str, Any], project: str, args: list[str]) -> Path:
    """解析命令实际操作的仓库目录。

    status/verify/run/shell 追加需求名时，自动切换到该需求 worktree；
    不追加需求名时，操作主工作区中的项目目录。
    """
    return project_worktree_dir(config, project, args[0]) if args else project_dir(config, project)


def worktree_root(config: dict[str, Any]) -> Path:
    """解析兼容 worktree 根目录，支持 MOM_WORKTREE_ROOT 环境变量覆盖。"""
    configured = os.environ.get("MOM_WORKTREE_ROOT") or config.get("worktreeRoot") or ".worktrees"
    root = Path(configured)
    return root if root.is_absolute() else ROOT_DIR / root


def new_worktree_path(config: dict[str, Any], name: str, task_name: str) -> Path:
    """返回新需求 worktree 路径。

    默认把工作树集中放在工作区根目录 `.worktrees/<project>/` 下，
    并用需求目录名加用途后缀区分 dev/feature。
    `MOM_WORKTREE_ROOT` 仅作为人工覆盖入口保留。
    """
    project = project_config(config, name)
    project_path = project.get("path")
    if not project_path:
        fail(f"project has no path: {name}")
    requirement_leaf = find_requirement_dir(config, task_name).name
    return worktree_root(config) / safe_path_leaf(project_path) / f"{requirement_leaf}-dev"


def sync_default_branch_from_upstream(repo_dir: Path, default_branch: str, upstream_branch: str | None) -> None:
    """创建需求 worktree 前，把本地基座分支快进到对应上游分支。

    PDA 等本地基座分支可能包含联调配置提交，和上游发布分支不是
    快进关系；这里显式把上游合并进本地基座，冲突时由 Git 失败并
    要求人工处理。
    """
    if not upstream_branch:
        print(f"No upstreamBranch configured; skip syncing {default_branch}.")
        return

    print(f"Sync base branch before worktree: origin/{upstream_branch} -> {default_branch}")
    run_checked(["git", "-C", str(repo_dir), "fetch", "origin", upstream_branch], ROOT_DIR)
    run_checked(["git", "-C", str(repo_dir), "switch", default_branch], ROOT_DIR)
    run_checked(["git", "-C", str(repo_dir), "merge", "--no-edit", f"origin/{upstream_branch}"], ROOT_DIR)


def assert_main_worktree_clean(repo_dir: Path, project_name: str) -> None:
    """创建需求 worktree 前确认主项目仓库没有未提交变更。

    主仓库存在脏改动时继续同步、切分支或手工创建 worktree，容易把
    用户改动混入基座判断。这里直接中止，让主对话先报告用户。
    """
    status = capture(["git", "-C", str(repo_dir), "status", "--short"], ROOT_DIR)
    if not status:
        return
    changed = "\n".join(f"  {line}" for line in status.splitlines()[:20])
    fail(
        f"主项目仓库存在未提交变更，已暂停为 {project_name} 创建 worktree；"
        f"请先报告用户并确认处理方式:\n{changed}"
    )


def create_worktree(config: dict[str, Any], name: str, task_name: str, base_branch: str | None) -> Path:
    """从项目默认基座分支创建需求 worktree。

    默认基座通常是 local，用来继承本地启动配置；真正交付时再从 develop
    创建 feature 分支并 cherry-pick 需求提交。
    """
    project = project_config(config, name)
    repo_dir = project_dir(config, name)
    project_path = project.get("path")
    if not project_path:
        fail(f"project has no path: {name}")

    existing = project_worktree_dirs(config, name, task_name, include_feature=False)
    if existing:
        path = existing[-1]
        print(f"Reusing worktree: {path}")
        return path

    if not base_branch:
        base_branch = project.get("defaultBranch")
    if not base_branch:
        base_branch = capture(["git", "-C", str(repo_dir), "branch", "--show-current"], ROOT_DIR)
    if not base_branch:
        fail("cannot determine base branch")
    assert_main_worktree_clean(repo_dir, name)
    if project.get("defaultBranch") == base_branch:
        sync_default_branch_from_upstream(repo_dir, base_branch, project.get("upstreamBranch"))

    branch = f"codex/{branch_today()}-{safe_branch_leaf(task_name)}"
    path = new_worktree_path(config, name, task_name)

    print(f"Project: {name}")
    print(f"Repo: {repo_dir}")
    print(f"Base: {base_branch}")
    print(f"Branch: {branch}")
    print(f"Worktree: {path}")
    print()

    path.parent.mkdir(parents=True, exist_ok=True)
    run_checked(["git", "-C", str(repo_dir), "worktree", "add", str(path), "-b", branch, base_branch], ROOT_DIR)
    if project.get("kind") == "pnpm-web":
        copied = sync_web_local_configs(repo_dir, path)
        if copied:
            print("Synced local Web config files:")
            for item in copied:
                print(f"  {item}")
        else:
            print("No ignored local Web config files found to sync.")
    return path
