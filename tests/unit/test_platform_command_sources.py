from __future__ import annotations

import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMANDS = ROOT / "commands"


def _toml_payload(path: Path) -> dict[str, str]:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _projected_markdown(source: Path) -> str:
    payload = _toml_payload(source)
    relative = source.relative_to(ROOT).as_posix()
    prompt = payload["prompt"].replace("{{args}}", "$ARGUMENTS")
    return (
        f"---\ndescription: {payload['description']}\n---\n"
        f"<!-- Generated from {relative} by adapters/render.mjs; do not edit. -->\n\n"
        f"{prompt}\n"
    )


def test_platform_manifests_expose_same_commands_without_orca() -> None:
    codex = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text())
    claude = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    expected = ["/praxis-help", "/praxis-check", "/praxis-quick", "/praxis-start"]

    assert codex["commands"] == expected
    assert claude["commands"] == expected
    assert not (ROOT / ".orca-plugin").exists()
    assert not (ROOT / "orca.yaml").exists()
    assert not (ROOT / "adapters" / "orca").exists()


def test_generated_markdown_matches_toml_and_contains_no_orca() -> None:
    for source in sorted(COMMANDS.glob("*.toml")):
        target = source.with_suffix(".md")
        assert target.read_text(encoding="utf-8") == _projected_markdown(source)
        assert "orca" not in source.read_text(encoding="utf-8").lower()
