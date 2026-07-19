from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any


def load_toml(path: Path) -> dict[str, Any]:
    return tomllib.loads(path.read_text())


def dumps_toml(data: dict[str, Any]) -> str:
    lines: list[str] = []
    for key, value in data.items():
        if isinstance(value, dict):
            lines.append(f"[{key}]")
            for k, v in value.items():
                lines.append(f"{k} = {format_value(v)}")
            lines.append("")
        else:
            lines.append(f"{key} = {format_value(value)}")
    return "\n".join(lines).rstrip() + "\n"


def format_value(value: Any) -> str:
    if isinstance(value, str):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(format_value(v) for v in value) + "]"
    if value is None:
        return '""'
    return format_value(str(value))
