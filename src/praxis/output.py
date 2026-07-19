from __future__ import annotations

import json
import sys
from typing import Any


def envelope(
    command: str, data: Any | None = None, diagnostics: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    return {
        "ok": True,
        "command": command,
        "data": data if data is not None else {},
        "diagnostics": diagnostics or [],
    }


def error_envelope(
    command: str,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    diagnostics: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "ok": False,
        "command": command,
        "code": code,
        "message": message,
        "details": details or {},
        "diagnostics": diagnostics or [],
    }


def emit(payload: dict[str, Any], *, as_json: bool = True) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    elif payload.get("ok"):
        print(payload.get("data") or payload.get("message") or "完成")
    else:
        print(payload.get("message", "失败"), file=sys.stderr)
