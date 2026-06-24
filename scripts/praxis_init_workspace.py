#!/usr/bin/env python3
"""Initialize a workspace with thin Praxis template files."""

from __future__ import annotations

import argparse
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = PLUGIN_ROOT / "templates"

TEMPLATE_MAP = {
    "AGENTS.md.tpl": "AGENTS.md",
    "praxis.toml.tpl": "praxis.toml",
    "praxis.projects.toml.tpl": "praxis.projects.toml",
    "core.toml.tpl": ".praxis/core.toml",
    "project-adapter.toml.tpl": ".praxis/project-adapter.toml",
    "turn.schema.json": ".praxis/contracts/agents/turn.schema.json",
}


def initialize_workspace(workspace: str | Path, *, name: str = "Praxis Workspace", force: bool = False) -> list[str]:
    root = Path(workspace).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    written: list[str] = []

    for template_name, relative_target in TEMPLATE_MAP.items():
        template_path = TEMPLATE_ROOT / template_name
        target_path = root / relative_target
        if target_path.exists() and not force:
            continue
        target_path.parent.mkdir(parents=True, exist_ok=True)
        rendered = render_template(template_path.read_text(encoding="utf-8"), name=name)
        target_path.write_text(rendered, encoding="utf-8")
        written.append(relative_target)
    return written


def render_template(template: str, *, name: str) -> str:
    return template.replace("{{ workspace_name }}", name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", help="Workspace root to initialize")
    parser.add_argument("--name", default="Praxis Workspace", help="Workspace display name")
    parser.add_argument("--force", action="store_true", help="Overwrite existing template files")
    args = parser.parse_args(argv)

    written = initialize_workspace(args.workspace, name=args.name, force=args.force)
    if written:
        print("written:")
        for path in written:
            print(f"  - {path}")
    else:
        print("no files written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
