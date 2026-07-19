from __future__ import annotations

from pathlib import Path
from typing import Any

from .context import context_command, verify_command
from .docs import doc_init, update_context_index
from .git_worktree import create_worktree, is_development_branch
from .names import safe_branch_leaf
from .paths import ROOT_DIR
from .process import capture, fail


def assert_requirement_binding(config: dict[str, Any], requirement_name: str, req_dir: Path, worktree_path: Path | None = None) -> None:
    """阻止需求目录、工作树和分支绑定到不同需求。"""
    resolved_name = req_dir.name[11:] if req_dir.name[:10].count("-") == 2 else requirement_name
    if resolved_name != requirement_name:
        fail(
            f"禁止自动跨名称复用：用户请求 `{requirement_name}`，最终需求 `{resolved_name}`；"
            "请使用同名需求，或显式进入旧需求继续迭代"
        )
    if worktree_path is None:
        return
    current_branch = capture(["git", "-C", str(worktree_path), "branch", "--show-current"], ROOT_DIR)
    expected_suffix = f"-{safe_branch_leaf(requirement_name)}"
    if worktree_path.name != f"{req_dir.name}-dev" or not is_development_branch(config, current_branch) or not current_branch.endswith(expected_suffix):
        fail(
            f"需求工作树绑定不一致：需求 `{requirement_name}`，工作树 `{worktree_path}`，分支 `{current_branch}`"
        )


def start_requirement(config: dict[str, Any], project: str, requirement_name: str, raw_requirement: str = "") -> None:
    """初始化需求文档，并为代码项目创建需求 worktree。"""
    req_dir = doc_init(config, requirement_name, raw_requirement)
    assert_requirement_binding(config, requirement_name, req_dir)
    worktree_path = None
    if project != "docs":
        worktree_path = create_worktree(config, project, requirement_name, None)
        assert_requirement_binding(config, requirement_name, req_dir, worktree_path)
    update_context_index(req_dir, project, worktree_path)
    print()
    context_command(config, project, requirement_name)


def print_verification_hint(project: str, requirement_name: str) -> None:
    """打印需求 worktree 对应的推荐验证命令。"""
    print(f"Verification command: {verify_command(project, requirement_name)}")
