from __future__ import annotations

import fnmatch
import re
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath

from praxis.domain.process import CommandIntent, ProcessRequest
from praxis.result import Result

_SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)\b(?:password|secret|token)\s*=\s*['\"][^'\"]+['\"]"),
)


def allowed_paths_gate(
    changed_paths: Sequence[str],
    allowed_paths: Sequence[str],
    forbidden_paths: Sequence[str] = (),
) -> Result:
    blocked = []
    for raw in changed_paths:
        path = PurePosixPath(raw.replace("\\", "/"))
        unsafe = path.is_absolute() or ".." in path.parts
        forbidden = any(_path_matches(path, rule) for rule in forbidden_paths)
        allowed = any(_path_matches(path, rule) for rule in allowed_paths)
        if unsafe or forbidden or not allowed:
            blocked.append(raw)
    return Result(
        not blocked,
        "OK" if not blocked else "GATE_PATH_OUT_OF_SCOPE",
        data={"blocked_paths": blocked},
    )


def command_policy_gate(
    request: ProcessRequest,
    registered_roots: Sequence[Path],
    allowed_environment: frozenset[str] = frozenset(),
) -> Result:
    if not request.argv or not request.argv[0]:
        return Result(False, "GATE_COMMAND_EMPTY")
    cwd = request.cwd.resolve()
    if not any(cwd.is_relative_to(root.resolve()) for root in registered_roots):
        return Result(False, "GATE_COMMAND_CWD_OUT_OF_SCOPE", data={"cwd": str(cwd)})
    unknown_environment = sorted(set(request.environment or {}) - allowed_environment)
    if unknown_environment:
        return Result(
            False,
            "GATE_COMMAND_ENVIRONMENT_DENIED",
            data={"variables": unknown_environment},
        )
    if request.intent in {CommandIntent.DATABASE_WRITE, CommandIntent.DEPLOY}:
        return Result(False, "GATE_APPROVAL_REQUIRED", data={"intent": request.intent.value})
    return Result(True)


def secret_gate(files: Mapping[str, str]) -> Result:
    findings = [
        {"path": path, "pattern": pattern.pattern}
        for path, content in files.items()
        for pattern in _SECRET_PATTERNS
        if pattern.search(content)
    ]
    return Result(
        not findings,
        "OK" if not findings else "GATE_SECRET_DETECTED",
        data={"findings": findings},
    )


def _path_matches(path: PurePosixPath, rule: str) -> bool:
    normalized = rule.replace("\\", "/").rstrip("/")
    value = path.as_posix()
    return value == normalized or value.startswith(normalized + "/") or fnmatch.fnmatch(value, rule)
