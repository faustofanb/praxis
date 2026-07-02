from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any


TRACE_DIR = ".praxis/out/traces"
TRACE_LOG = "praxis-trace.jsonl"
TRACE_SUMMARY = "trace-summary.json"


def trace_dir(root: Path) -> Path:
    """Return the local trace output directory."""
    return root / TRACE_DIR


def _portable_value(root: Path, value: Any) -> Any:
    if isinstance(value, Path):
        try:
            return value.relative_to(root).as_posix()
        except ValueError:
            return str(value)
    if isinstance(value, str):
        try:
            path = Path(value)
            if path.is_absolute():
                return path.relative_to(root).as_posix()
        except (OSError, ValueError):
            return value
    if isinstance(value, dict):
        return {key: _portable_value(root, item) for key, item in value.items()}
    if isinstance(value, list):
        return [_portable_value(root, item) for item in value]
    return value


def write_trace_span(root: Path, *, command: str, status: str, attributes: dict[str, Any] | None = None) -> Path:
    """Append a local JSON span record for a Praxis command."""
    now = time.time()
    span = {
        "schemaVersion": 1,
        "traceId": uuid.uuid4().hex,
        "spanId": uuid.uuid4().hex[:16],
        "command": command,
        "status": status,
        "startedAtUnixNano": int(now * 1_000_000_000),
        "endedAtUnixNano": int(now * 1_000_000_000),
        "durationMs": 0,
        "attributes": _portable_value(root, attributes or {}),
    }
    directory = trace_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / TRACE_LOG
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(span, ensure_ascii=False) + "\n")
    return path


def _spans(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_trace_summary(root: Path) -> Path:
    """Write a compact local trace summary with OTLP configuration hints."""
    path = trace_dir(root) / TRACE_LOG
    spans = _spans(path)
    statuses: dict[str, int] = {}
    for span in spans:
        status = str(span.get("status", "UNKNOWN"))
        statuses[status] = statuses.get(status, 0) + 1
    summary = {
        "schemaVersion": 1,
        "generatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "summary": {
            "spanCount": len(spans),
            "statuses": statuses,
            "traceLog": f"{TRACE_DIR}/{TRACE_LOG}",
        },
        "otlp": {
            "endpoint": os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", ""),
            "protocol": os.environ.get("OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf"),
            "serviceName": os.environ.get("OTEL_SERVICE_NAME", "praxis"),
            "enabled": bool(os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")),
        },
    }
    output = trace_dir(root) / TRACE_SUMMARY
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Praxis trace summary: {output}")
    return output
