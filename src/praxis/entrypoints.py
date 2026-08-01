from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path
from typing import Any


def diagnose(current: str = "auto") -> dict[str, Any]:
    """Report the available Praxis transports and the entrypoint in use."""
    cli_path = _cli_path()
    mcp_available = _mcp_server_available()
    cli = {
        "available": cli_path is not None,
        "path": str(cli_path) if cli_path else "",
        "command": "praxis",
        "fallback": True,
    }
    mcp = {
        "available": mcp_available,
        "server_capability": mcp_available,
        "command": [sys.executable, "-m", "praxis", "mcp", "serve"],
    }
    normalized = (current or "auto").strip().lower()
    if normalized == "cli":
        selected = {
            "kind": "CLI",
            "path": cli["path"],
            "available": cli["available"],
        }
    elif normalized == "mcp":
        selected = {
            "kind": "MCP",
            "path": "",
            "available": mcp["available"],
        }
    elif normalized == "internal":
        selected = {"kind": "内部服务", "path": "", "available": True}
    else:
        selected = {
            "kind": "自动选择",
            "path": cli["path"] if cli["available"] else "",
            "available": cli["available"] or mcp["available"],
        }
    return {
        "current": selected,
        "cli": cli,
        "mcp": mcp,
        "fallback": {
            "available": cli["available"],
            "path": cli["path"],
            "message": (
                f"MCP 不可用时使用 CLI：{cli['path']}"
                if cli["available"]
                else "未解析到 praxis CLI；请检查 PATH 或安装入口。"
            ),
        },
    }


def _cli_path() -> Path | None:
    resolved = shutil.which("praxis")
    if resolved:
        path = Path(resolved).resolve()
        return path
    argv = Path(sys.argv[0]) if sys.argv else Path()
    if argv.name == "praxis" and argv.is_file():
        return argv.resolve()
    return None


def _mcp_server_available() -> bool:
    try:
        return importlib.util.find_spec("mcp") is not None
    except (ImportError, ValueError):
        return False
