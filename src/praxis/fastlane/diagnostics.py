from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

Diagnostic = tuple[str, str, str]

_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_TYPESCRIPT = re.compile(
    r"^(?P<path>.+?)\((?P<line>\d+),(?P<column>\d+)\):\s*"
    r"(?:error|warning)\s+(?P<code>[A-Za-z]*\d+):\s*(?P<message>.+)$"
)
_PYTHON = re.compile(
    r"^(?P<path>.+?):(?P<line>\d+):(?P<column>\d+):\s*"
    r"(?:error|warning|note):\s*(?P<message>.+?)"
    r"(?:\s+\[(?P<code>[^\]]+)\])?$"
)
_GENERIC = re.compile(
    r"^(?P<path>.+?):(?P<line>\d+)(?::(?P<column>\d+))?:\s*"
    r"(?P<code>[A-Za-z][A-Za-z0-9_-]*):\s*(?P<message>.+)$"
)
_TY_HEADER = re.compile(
    r"^(?:error|warning|note)(?:\[(?P<bracket_code>[^\]]+)\])?:\s*"
    r"(?P<message>.+?)(?:\s+\[(?P<trailing_code>[^\]]+)\])?$"
)
_TY_LOCATION = re.compile(
    r"^(?:-->)?\s*(?P<path>.+?):(?P<line>\d+):(?P<column>\d+)\s*$"
)
_CONFIG_FILES = (
    "package.json",
    "tsconfig.json",
    "tsconfig.app.json",
    "pyproject.toml",
    "ty.toml",
    "mypy.ini",
    ".mypy.ini",
)
_LOCK_FILES = (
    "pnpm-lock.yaml",
    "package-lock.json",
    "yarn.lock",
    "bun.lock",
    "bun.lockb",
    "uv.lock",
    "poetry.lock",
    "Pipfile.lock",
)


def _relative_path(value: str, root: Path) -> str:
    candidate = Path(value)
    if candidate.is_absolute():
        try:
            return candidate.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            parts = candidate.parts
            for marker in ("src", "tests", "test"):
                if marker in parts:
                    return Path(*parts[parts.index(marker) :]).as_posix()
    return value.replace("\\", "/").removeprefix("./")


def _message(value: str) -> str:
    return " ".join(value.strip().split())


def normalize_diagnostics(output: str, root: Path | str) -> Counter[Diagnostic]:
    """Parse common type-check diagnostics while deliberately ignoring line/column."""
    base = Path(root)
    diagnostics: Counter[Diagnostic] = Counter()
    pending_ty: tuple[str, str] | None = None
    for raw in _ANSI.sub("", output).splitlines():
        line = raw.strip()
        match = _TYPESCRIPT.match(line) or _PYTHON.match(line) or _GENERIC.match(line)
        if match:
            groups = match.groupdict()
            code = (groups.get("code") or "type-error").strip()
            diagnostics[
                (
                    _relative_path(groups["path"].strip(), base),
                    code,
                    _message(groups["message"]),
                )
            ] += 1
            continue
        header = _TY_HEADER.match(line)
        if header:
            pending_ty = (
                header.group("bracket_code")
                or header.group("trailing_code")
                or "type-error",
                _message(header.group("message")),
            )
            continue
        location = _TY_LOCATION.match(line.removeprefix("-->").strip())
        if location and pending_ty:
            diagnostics[
                (
                    _relative_path(location.group("path").strip(), base),
                    pending_ty[0],
                    pending_ty[1],
                )
            ] += 1
            pending_ty = None
    return diagnostics


def compare_diagnostics(
    baseline_output: str,
    current_output: str,
    root: Path | str,
    *,
    baseline_root: Path | str | None = None,
) -> dict[str, object]:
    baseline = normalize_diagnostics(baseline_output, baseline_root or root)
    current = normalize_diagnostics(current_output, root)
    delta = current - baseline
    introduced = [
        {"path": path, "code": code, "message": message, "count": count}
        for (path, code, message), count in sorted(delta.items())
    ]
    if introduced:
        status = "failed_new_diagnostics"
    elif baseline:
        status = "incremental_passed_baseline_failed"
    else:
        status = "passed"
    return {
        "status": status,
        "new_diagnostics": introduced,
        "baseline_count": sum(baseline.values()),
        "current_count": sum(current.values()),
    }


def baseline_fingerprint(
    project_id: str,
    template_sha: str,
    argv: tuple[str, ...],
    repository: Path | str,
) -> str:
    root = Path(repository)
    files: dict[str, str] = {}
    excluded = {".git", ".venv", "node_modules", "dist", "build", ".worktrees"}
    for name in (*_LOCK_FILES, *_CONFIG_FILES):
        for path in sorted(root.rglob(name)):
            relative = path.relative_to(root)
            if path.is_file() and not excluded.intersection(relative.parts):
                files[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    payload = {
        "project_id": project_id,
        "template_sha": template_sha,
        "argv": list(argv),
        "toolchain": files,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
