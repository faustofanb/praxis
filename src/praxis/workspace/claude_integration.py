from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from praxis.documents.atomic_writer import atomic_write_text
from praxis.result import Result
from praxis.skills.registry import SkillRegistry
from praxis.storage.sqlite import StateStore
from praxis.workspace.service import WorkspaceService

_GUARD_SCRIPT_NAME = "praxis-binding-guard.sh"
_GITIGNORE_ENTRIES = ("/.claude/skills/", f"/.claude/hooks/{_GUARD_SCRIPT_NAME}")


class ClaudeIntegrationService:
    """Deploys Praxis's Skill catalog, MCP registration, and PreToolUse guard into the
    paths Claude Code actually reads for a given workspace root."""

    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.store = StateStore(self.root)

    def install(self) -> Result:
        workspace = WorkspaceService(self.root).load()
        mcp_result = self._write_mcp_json()
        skills_result = self._link_skills()
        guard_result = self._write_guard_script(workspace["projects"])
        settings_result = self._merge_settings_local(guard_result.data["path"])
        gitignore_result = self._extend_gitignore()
        data = {
            "mcp_json": mcp_result.data,
            "skills": skills_result.data,
            "guard_script": guard_result.data,
            "settings_local": settings_result.data,
            "gitignore": gitignore_result.data,
        }
        audit_id = self.store.audit("claude.integration_installed", "OK", data)
        return Result(True, data={**data, "audit_id": audit_id})

    def _write_mcp_json(self) -> Result:
        path = self.root / ".mcp.json"
        config: dict[str, Any] = {}
        if path.exists():
            try:
                config = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return Result(False, "CLAUDE_MCP_JSON_INVALID", data={"path": str(path)})
        servers = config.setdefault("mcpServers", {})
        added = "praxis" not in servers
        if added:
            servers["praxis"] = {
                "command": "praxis",
                "args": ["--root", str(self.root.resolve()), "mcp", "serve"],
            }
            atomic_write_text(path, json.dumps(config, ensure_ascii=False, indent=2) + "\n")
        return Result(True, data={"path": str(path), "added": added})

    def _link_skills(self) -> Result:
        target_dir = self.root / ".claude" / "skills"
        target_dir.mkdir(parents=True, exist_ok=True)
        linked: list[str] = []
        skipped: list[str] = []
        for skill in SkillRegistry.workspace(self.root).all():
            link = target_dir / skill.id
            source = skill.path.parent.resolve()
            if link.is_symlink() or link.exists():
                if link.is_symlink() and link.resolve() == source:
                    linked.append(skill.id)
                else:
                    skipped.append(skill.id)
                continue
            link.symlink_to(source, target_is_directory=True)
            linked.append(skill.id)
        return Result(True, data={"path": str(target_dir), "linked": linked, "skipped": skipped})

    def _write_guard_script(self, projects: list[dict[str, Any]]) -> Result:
        path = self.root / ".claude" / "hooks" / _GUARD_SCRIPT_NAME
        repos = [p["path"] for p in projects if p.get("kind") != "docs" and p.get("path") != "."]
        guard_root_itself = any(p.get("path") == "." for p in projects)
        script = _render_guard_script(self.root.resolve(), repos, guard_root_itself)
        atomic_write_text(path, script)
        path.chmod(0o755)
        return Result(True, data={"path": str(path), "protected_repos": repos})

    def _merge_settings_local(self, guard_script_path: str) -> Result:
        path = self.root / ".claude" / "settings.local.json"
        config: dict[str, Any] = {}
        if path.exists():
            try:
                config = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return Result(False, "CLAUDE_SETTINGS_INVALID", data={"path": str(path)})
        pre_tool_use = config.setdefault("hooks", {}).setdefault("PreToolUse", [])
        already_present = any(
            entry.get("command") == guard_script_path
            for group in pre_tool_use
            for entry in group.get("hooks", [])
        )
        if not already_present:
            pre_tool_use.append(
                {"matcher": "*", "hooks": [{"type": "command", "command": guard_script_path}]}
            )
        atomic_write_text(path, json.dumps(config, ensure_ascii=False, indent=2) + "\n")
        return Result(True, data={"path": str(path), "added": not already_present})

    def _extend_gitignore(self) -> Result:
        path = self.root / ".gitignore"
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        lines = existing.splitlines()
        missing = [entry for entry in _GITIGNORE_ENTRIES if entry not in lines]
        if missing:
            updated = existing
            if updated and not updated.endswith("\n"):
                updated += "\n"
            updated += "\n".join(missing) + "\n"
            atomic_write_text(path, updated)
        return Result(True, data={"path": str(path), "added": missing})


def _render_guard_script(root: Path, repos: list[str], guard_root_itself: bool) -> str:
    repo_array = "\n".join(f"  {repo}" for repo in repos)
    return f"""#!/bin/bash
# Generated by `praxis workspace install-claude`. PreToolUse guard: block Edit/Write/git-commit
# against a repository's raw checkout at the workspace root when the path isn't inside a bound
# Praxis worktree (.worktrees/<REQ>__<slug>/...). Regenerate via `workspace install-claude`
# instead of hand-editing; re-running preserves this file's identity but overwrites its body.
set -euo pipefail

WORKSPACE_ROOT="{root}"
PROTECTED_REPOS=(
{repo_array}
)
GUARD_ROOT_ITSELF="{"true" if guard_root_itself else "false"}"

input="$(cat)"
tool_name="$(printf '%s' "$input" | jq -r '.tool_name // empty')"

find_blocking_repo() {{
  local path="$1"
  case "$path" in
    "$WORKSPACE_ROOT"/.worktrees/*) return 0 ;;
  esac
  for repo in "${{PROTECTED_REPOS[@]}}"; do
    case "$path" in
      "$WORKSPACE_ROOT/$repo"/* | "$WORKSPACE_ROOT/$repo")
        printf '%s' "$repo"
        return 0
        ;;
    esac
  done
  if [ "$GUARD_ROOT_ITSELF" = "true" ]; then
    case "$path" in
      "$WORKSPACE_ROOT"/*)
        printf '%s' "(workspace root)"
        return 0
        ;;
    esac
  fi
  return 0
}}

deny() {{
  local repo="$1"
  local scope="$2"
  jq -n --arg reason "路径直接位于仓库 '$repo' 的工作空间根目录副本（$scope），未绑定 Praxis 需求 worktree。请先用 'praxis worktree preview' / 'worktree ensure --confirm <preview_id>' 为需求创建工作树，在 .worktrees/ 下的绑定目录中修改业务代码。" \\
    '{{hookSpecificOutput: {{hookEventName: "PreToolUse", permissionDecision: "deny", permissionDecisionReason: $reason}}}}'
}}

case "$tool_name" in
  Edit|Write)
    file_path="$(printf '%s' "$input" | jq -r '.tool_input.file_path // empty')"
    [ -z "$file_path" ] && exit 0
    repo="$(find_blocking_repo "$file_path")"
    [ -n "$repo" ] && deny "$repo" "文件编辑" && exit 0
    ;;
  Bash)
    command_str="$(printf '%s' "$input" | jq -r '.tool_input.command // empty')"
    case "$command_str" in
      *"git commit"*)
        cwd="$(git rev-parse --show-toplevel 2>/dev/null || true)"
        [ -z "$cwd" ] && exit 0
        repo="$(find_blocking_repo "$cwd")"
        [ -n "$repo" ] && deny "$repo" "git commit" && exit 0
        ;;
    esac
    ;;
esac
exit 0
"""
