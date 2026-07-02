from __future__ import annotations

from typing import Any

from .context import context_command, verify_command
from .docs import doc_init, update_context_index
from .git_worktree import create_worktree


def start_requirement(config: dict[str, Any], project: str, requirement_name: str, raw_requirement: str = "") -> None:
    """初始化需求文档，并为代码项目创建需求 worktree。"""
    req_dir = doc_init(config, requirement_name, raw_requirement)
    worktree_path = None
    if project != "docs":
        worktree_path = create_worktree(config, project, requirement_name, None)
    update_context_index(req_dir, project, worktree_path)
    print()
    context_command(config, project, requirement_name)


def print_verification_hint(project: str, requirement_name: str) -> None:
    """打印需求 worktree 对应的推荐验证命令。"""
    print(f"Verification command: {verify_command(project, requirement_name)}")
