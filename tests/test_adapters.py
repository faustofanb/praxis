from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_codex_manifest_exposes_single_skill_source_and_mcp() -> None:
    manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text())
    assert manifest["name"] == "praxis-next"
    assert manifest["version"] == "2.0.0"
    assert manifest["skills"] == "./skills/"
    assert (ROOT / "skills" / "dbx-database-investigation").resolve() == (
        ROOT / "assets" / "skills" / "system" / "dbx-database-investigation"
    )
    assert manifest["mcpServers"] == "./.mcp.json"


def test_platform_adapters_are_thin_and_no_legacy_platform_exists() -> None:
    for platform in ("codex", "claude-code", "omp"):
        source = (ROOT / "adapters" / platform / "index.mjs").read_text()
        assert "PRAXIS_BIN" in source
    assert not (ROOT / "adapters" / "orca").exists()


def test_pi_package_exposes_the_thin_extension_and_shared_skills() -> None:
    manifest = json.loads((ROOT / "package.json").read_text())

    assert manifest["pi"] == {
        "extensions": ["pi-extension/index.js"],
        "skills": ["skills"],
    }
    assert (ROOT / "pi-extension" / "index.js").is_file()
    assert not (ROOT / "profiles").exists()
    assert not (ROOT / "capabilities").exists()


def test_mcp_companion_starts_only_praxis_gateway() -> None:
    config = json.loads((ROOT / ".mcp.json").read_text())
    assert config == {
        "mcpServers": {
            "praxis": {"command": "./scripts/praxis-mcp", "args": []},
        }
    }
