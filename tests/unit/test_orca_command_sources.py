from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_orca_manifest_points_to_real_command_sources() -> None:
    payload = json.loads((ROOT / ".orca-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert payload["id"] == "com.fausto.praxis-next"
    assert payload["main"] == "main.js"
    assert payload["commandsDir"] == "../commands"
    assert (ROOT / ".orca-plugin" / "main.js").is_file()


def test_platform_manifests_and_commands_are_generated_together() -> None:
    codex = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    claude = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    orca = json.loads((ROOT / ".orca-plugin" / "plugin.json").read_text(encoding="utf-8"))
    expected_commands = ["/praxis-help", "/praxis-check", "/praxis-quick", "/praxis-start"]

    assert codex["commands"] == expected_commands
    assert claude["commands"] == expected_commands
    assert orca["commandsDir"] == "../commands"
    assert (ROOT / ".claude-plugin" / "marketplace.json").is_file()


def test_orca_canonical_command_files_exist() -> None:
    expected = {
        "praxis-help.toml",
        "praxis-check.toml",
        "praxis-quick.toml",
        "praxis-start.toml",
        "praxis-verify.toml",
        "praxis-setup.toml",
        "praxis-doctor.toml",
        "praxis-tolaria-check.toml",
    }
    actual = {path.name for path in (ROOT / "commands").glob("*.toml")}
    assert expected <= actual


def test_orca_generated_markdown_is_projected_from_toml() -> None:
    help_md = (ROOT / "commands" / "praxis-help.md").read_text(encoding="utf-8")
    tolaria_md = (ROOT / "commands" / "praxis-tolaria-check.md").read_text(encoding="utf-8")
    assert "Generated from commands/praxis-help.toml by adapters/render.mjs" in help_md
    assert "Praxis Next 快速参考" in help_md
    assert "不要伪造 changed-file" in tolaria_md
    assert "capability_not_enabled" in tolaria_md
    assert "{{args}}" not in tolaria_md
    assert "$ARGUMENTS" not in tolaria_md
