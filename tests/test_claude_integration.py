from __future__ import annotations

import json
from pathlib import Path

from praxis.workspace.claude_integration import ClaudeIntegrationService
from praxis.workspace.service import Project, WorkspaceService

_BUSINESS_SKILL = (
    "---\n"
    "name: demo-business-skill\n"
    "description: 测试用业务技能。\n"
    "---\n\n"
    "# 测试\n"
)
_BUSINESS_TOML = (
    'id = "demo-business-skill"\n'
    'type = "business"\n'
    'version = "1.0.0"\n'
    'license = "Proprietary"\n'
    'source = "test"\n'
    'source_version = "1"\n'
    'risk = "none"\n'
    "context_budget = 500\n"
    "required_tools = []\n"
    "triggers = []\n"
    "systems = []\n"
    "projects = []\n"
    "repository_roles = []\n"
)


def _init_workspace(tmp_path: Path) -> None:
    WorkspaceService(tmp_path).init(
        "demo",
        "演示工作空间",
        projects=[
            Project("backend", "python-plugin", "backend", "main"),
            Project("docs", "docs", "docs", "main"),
        ],
    )
    business = tmp_path / "知识库" / "skills" / "business" / "demo-business-skill"
    business.mkdir(parents=True)
    (business / "SKILL.md").write_text(_BUSINESS_SKILL, encoding="utf-8")
    (business / "skill.toml").write_text(_BUSINESS_TOML, encoding="utf-8")
    (tmp_path / "backend").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / ".gitignore").write_text("/.praxis/\n", encoding="utf-8")


def test_install_creates_mcp_json_skills_and_hook_on_fresh_workspace(
    tmp_path: Path,
) -> None:
    _init_workspace(tmp_path)

    result = ClaudeIntegrationService(tmp_path).install()

    assert result.ok, result.to_dict()
    mcp_config = json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8"))
    assert mcp_config["mcpServers"]["praxis"]["command"] == "praxis"
    assert mcp_config["mcpServers"]["praxis"]["args"][:2] == ["--root", str(tmp_path)]

    linked = {p.name: p for p in (tmp_path / ".claude" / "skills").iterdir()}
    assert "ponytail" in linked, "bundled first-party skill must be linked"
    assert linked["ponytail"].is_symlink()
    assert (linked["ponytail"] / "SKILL.md").is_file()
    assert "demo-business-skill" in linked, "workspace-local business skill must be linked"

    guard_script = tmp_path / ".claude" / "hooks" / "praxis-binding-guard.sh"
    assert guard_script.is_file()
    guard_body = guard_script.read_text(encoding="utf-8")
    assert "backend" in guard_body
    assert "docs" not in guard_body.split("PROTECTED_REPOS=(")[1].split(")")[0]

    settings = json.loads(
        (tmp_path / ".claude" / "settings.local.json").read_text(encoding="utf-8")
    )
    pre_tool_use = settings["hooks"]["PreToolUse"]
    assert len(pre_tool_use) == 1
    assert pre_tool_use[0]["hooks"][0]["type"] == "command"
    assert pre_tool_use[0]["hooks"][0]["command"] == str(guard_script)

    gitignore = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert "/.praxis/" in gitignore
    assert "/.claude/skills/" in gitignore


def test_install_preserves_existing_mcp_servers_and_permissions(tmp_path: Path) -> None:
    _init_workspace(tmp_path)
    (tmp_path / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"codegraph": {"command": "codegraph"}}}), encoding="utf-8"
    )
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.local.json").write_text(
        json.dumps({"permissions": {"allow": ["Bash(git status *)"]}}), encoding="utf-8"
    )

    result = ClaudeIntegrationService(tmp_path).install()

    assert result.ok, result.to_dict()
    mcp_config = json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8"))
    assert mcp_config["mcpServers"]["codegraph"] == {"command": "codegraph"}
    assert mcp_config["mcpServers"]["praxis"]["command"] == "praxis"
    settings = json.loads(
        (tmp_path / ".claude" / "settings.local.json").read_text(encoding="utf-8")
    )
    assert settings["permissions"]["allow"] == ["Bash(git status *)"]
    assert len(settings["hooks"]["PreToolUse"]) == 1


def test_install_is_idempotent(tmp_path: Path) -> None:
    _init_workspace(tmp_path)

    first = ClaudeIntegrationService(tmp_path).install()
    second = ClaudeIntegrationService(tmp_path).install()

    assert first.ok and second.ok
    settings = json.loads(
        (tmp_path / ".claude" / "settings.local.json").read_text(encoding="utf-8")
    )
    assert len(settings["hooks"]["PreToolUse"]) == 1
