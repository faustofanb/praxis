from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from praxis.documents.atomic_writer import atomic_write_text
from praxis.result import Result

Runner = Callable[[list[str], Path], subprocess.CompletedProcess[str]]
Compressor = Callable[[str, Path], str]

_SECRET = re.compile(
    r'(?i)(["\']?(?:password|token|secret|api[_-]?key)["\']?\s*[:=]\s*["\']?)'
    r'([^"\'\s,}]+)'
)
_SECRET_OPTIONS = {"--password", "--token", "--secret", "--api-key"}


class ProcessRunner:
    def __init__(
        self,
        cwd: Path | str,
        *,
        run: Runner | None = None,
        rtk_available: Callable[[], bool] | None = None,
        compress: Compressor | None = None,
        audit_root: Path | str | None = None,
    ):
        self.cwd = Path(cwd)
        self._run = run or self._default_run
        self._rtk_available = rtk_available or (lambda: shutil.which("rtk") is not None)
        self._compress = compress or self._default_compress
        self.audit_root = Path(audit_root) if audit_root else self.cwd

    @staticmethod
    def _default_run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(command, cwd=cwd, check=False, capture_output=True, text=True)

    @staticmethod
    def _default_compress(output: str, cwd: Path) -> str:
        process = subprocess.run(
            ["rtk", "pipe", "--filter", "log"],
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            input=output,
        )
        return process.stdout if process.returncode == 0 else output

    def run(self, command: list[str], *, machine_output: bool) -> Result:
        started_at = datetime.now(UTC)
        started = time.monotonic()
        try:
            process = self._run(command, self.cwd)
        except FileNotFoundError:
            return Result(False, "COMMAND_NOT_AVAILABLE", data={"command": command[0]})
        elapsed_ms = round((time.monotonic() - started) * 1000, 3)
        stdout = process.stdout
        stderr = process.stderr
        rtk_applied = not machine_output and self._rtk_available()
        if rtk_applied:
            stdout = self._compress("\n".join(part for part in (stdout, stderr) if part), self.cwd)
            stderr = ""
        raw_log = self._write_raw_log(
            command,
            process,
            started_at,
            elapsed_ms,
            rtk_output=stdout if rtk_applied else None,
        )
        return Result(
            process.returncode == 0,
            "OK" if process.returncode == 0 else "COMMAND_FAILED",
            data={
                "stdout": stdout,
                "stderr": stderr,
                "command": command,
                "raw_log": str(raw_log),
                "elapsed_ms": elapsed_ms,
            },
        )

    def _write_raw_log(
        self,
        command: list[str],
        process: subprocess.CompletedProcess[str],
        started_at: datetime,
        elapsed_ms: float,
        *,
        rtk_output: str | None,
    ) -> Path:
        log_id = f"LOG-{started_at:%Y%m%dT%H%M%S}-{uuid4().hex[:8].upper()}"
        path = self.audit_root / ".praxis" / "raw-logs" / f"{log_id}.json"
        payload = {
            "log_id": log_id,
            "started_at": started_at.isoformat(),
            "cwd": str(self.cwd.resolve()),
            "command": _redact_command(command),
            "exit_code": process.returncode,
            "stdout": _redact(process.stdout),
            "stderr": _redact(process.stderr),
            "rtk_output": _redact(rtk_output) if rtk_output is not None else None,
            "redacted": _redact(process.stdout) != process.stdout
            or _redact(process.stderr) != process.stderr,
            "elapsed_ms": elapsed_ms,
        }
        atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        return path


def _redact(value: str) -> str:
    return _SECRET.sub(r"\1[已脱敏]", value)


def _redact_command(command: list[str]) -> list[str]:
    redacted = list(command)
    for index, argument in enumerate(redacted[:-1]):
        if argument.lower() in _SECRET_OPTIONS:
            redacted[index + 1] = "[已脱敏]"
    return [_redact(argument) for argument in redacted]
