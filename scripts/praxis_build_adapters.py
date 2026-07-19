#!/usr/bin/env python3
"""Build thin platform adapter files from praxis.plugin.toml."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import tomllib
from pathlib import Path
from typing import Any

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
METADATA_PATH = PLUGIN_ROOT / "praxis.plugin.toml"
GENERATED_COMMENT = "<!-- Generated from {source} by scripts/praxis_build_adapters.py; do not edit. -->"


def load_metadata() -> dict[str, Any]:
    metadata = tomllib.loads(METADATA_PATH.read_text(encoding="utf-8"))
    required = {
        "schema_version",
        "name",
        "version",
        "description",
        "author",
        "license",
        "platforms",
        "ponytail_version",
        "rtk_missing",
    }
    missing = sorted(required - metadata.keys())
    if missing:
        raise ValueError(f"missing plugin metadata fields: {', '.join(missing)}")
    if metadata["schema_version"] != 1:
        raise ValueError("unsupported praxis.plugin.toml schema_version")
    return metadata


def codex_plugin(metadata: dict[str, Any]) -> str:
    payload = {
        "name": metadata["name"],
        "version": metadata["version"],
        "description": metadata["description"],
        "author": {"name": metadata["author"]},
        "license": metadata["license"],
        "keywords": ["praxis", "workflow", "codex", "worktree", "requirements"],
        "skills": "./skills/",
        "interface": {
            "displayName": "Praxis Workflow",
            "shortDescription": "Praxis startup gates, templates, profiles, and sync scripts.",
            "longDescription": "Praxis Workflow packages portable guidance, workspace templates, helper scripts, optional RTK command policy, embedded Ponytail assets, and syncable IFC MOM/AOTU profile assets while project facts stay in each workspace.",
            "developerName": metadata["author"],
            "category": "Productivity",
            "capabilities": ["Workflow", "Guidance", "Templates", "Profiles", "Scripts"],
            "defaultPrompt": [
                "Apply Praxis startup gates in this workspace.",
                "Check whether this task needs a requirement dir and worktree.",
                "Explain the Praxis project config boundary.",
            ],
        },
    }
    return dumps_json(payload)


def claude_plugin(metadata: dict[str, Any]) -> str:
    payload = {
        "name": metadata["name"],
        "version": metadata["version"],
        "description": metadata["description"],
        "author": {"name": metadata["author"]},
        "hooks": "./hooks/hooks.json",
    }
    return dumps_json(payload)


def claude_marketplace(metadata: dict[str, Any]) -> str:
    payload = {
        "$schema": "https://anthropic.com/claude-code/marketplace.schema.json",
        "name": metadata["name"],
        "description": metadata["description"],
        "owner": {"name": metadata["author"]},
        "plugins": [
            {
                "name": metadata["name"],
                "description": metadata["description"],
                "source": "./",
                "category": "productivity",
            }
        ],
    }
    return dumps_json(payload)


def package_json(metadata: dict[str, Any]) -> str:
    payload = {
        "name": metadata["name"],
        "version": metadata["version"],
        "description": metadata["description"],
        "license": metadata["license"],
        "private": True,
        "omp": {
            "extensions": [
                "./adapters/omp/ponytail-extension.mjs",
                "./adapters/omp/praxis-auto-sync.mjs",
            ],
            "skills": ["./skills"],
        },
    }
    return dumps_json(payload)


def command_markdown(source: Path) -> str:
    payload = tomllib.loads(source.read_text(encoding="utf-8"))
    description = str(payload.get("description", "")).strip()
    prompt = str(payload.get("prompt", "")).replace("{{args}}", "$ARGUMENTS").rstrip()
    if not description or not prompt:
        raise ValueError(f"command requires description and prompt: {source.relative_to(PLUGIN_ROOT)}")
    relative = source.relative_to(PLUGIN_ROOT).as_posix()
    return f"---\ndescription: {description}\n---\n{GENERATED_COMMENT.format(source=relative)}\n\n{prompt}\n"


def skill_names() -> set[str]:
    return {
        path.parent.name
        for path in (PLUGIN_ROOT / "skills").glob("*/SKILL.md")
    }


def generated_command_files() -> set[Path]:
    generated: set[Path] = set()
    for path in (PLUGIN_ROOT / "commands").glob("*.md"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if "Generated from commands/" in text and "praxis_build_adapters.py" in text:
            generated.add(path)
    return generated


def combined_hooks() -> str:
    source = PLUGIN_ROOT / "hooks" / "claude-codex-hooks.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["hooks"].setdefault("SessionStart", []).append(
        {
            "matcher": "startup|resume|clear|compact",
            "hooks": [
                {
                    "type": "command",
                    "command": 'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/praxis_auto_sync.py" || true',
                    "commandWindows": (
                        'if (Get-Command py -ErrorAction SilentlyContinue) { '
                        'py -3 "$env:CLAUDE_PLUGIN_ROOT\\scripts\\praxis_auto_sync.py" }; exit 0'
                    ),
                    "timeout": 15,
                    "statusMessage": "Synchronizing Praxis profile...",
                }
            ],
        }
    )
    return dumps_json(payload)


def expected_files(metadata: dict[str, Any]) -> dict[Path, str]:
    files = {
        PLUGIN_ROOT / ".codex-plugin" / "plugin.json": codex_plugin(metadata),
        PLUGIN_ROOT / ".claude-plugin" / "plugin.json": claude_plugin(metadata),
        PLUGIN_ROOT / ".claude-plugin" / "marketplace.json": claude_marketplace(metadata),
        PLUGIN_ROOT / "package.json": package_json(metadata),
        PLUGIN_ROOT / "hooks" / "hooks.json": combined_hooks(),
    }
    existing_skills = skill_names()
    for command in sorted((PLUGIN_ROOT / "commands").glob("*.toml")):
        if command.stem not in existing_skills:
            files[command.with_suffix(".md")] = command_markdown(command)
    return files


def dumps_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(content)
        temp_name = handle.name
    os.replace(temp_name, path)


def check(files: dict[Path, str]) -> list[str]:
    drift: list[str] = []
    expected_paths = set(files)
    for path, expected in sorted(files.items()):
        try:
            actual = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            drift.append(f"missing: {path.relative_to(PLUGIN_ROOT).as_posix()}")
            continue
        if actual != expected:
            drift.append(f"drift: {path.relative_to(PLUGIN_ROOT).as_posix()}")
    for path in sorted(generated_command_files() - expected_paths):
        drift.append(f"unexpected: {path.relative_to(PLUGIN_ROOT).as_posix()}")
    return drift


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Report generated file drift without writing")
    args = parser.parse_args(argv)

    metadata = load_metadata()
    files = expected_files(metadata)
    if args.check:
        drift = check(files)
        if drift:
            for entry in drift:
                print(entry)
            return 1
        print("adapter generated files are up to date")
        return 0

    expected_paths = set(files)
    for path in sorted(generated_command_files() - expected_paths):
        path.unlink()
        print(f"removed: {path.relative_to(PLUGIN_ROOT).as_posix()}")

    for path, content in sorted(files.items()):
        write_atomic(path, content)
        print(f"written: {path.relative_to(PLUGIN_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
