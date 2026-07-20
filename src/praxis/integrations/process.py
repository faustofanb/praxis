from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from praxis.result import Result

Runner = Callable[[list[str], Path], subprocess.CompletedProcess[str]]


class ProcessRunner:
    def __init__(
        self,
        cwd: Path | str,
        *,
        run: Runner | None = None,
        rtk_available: Callable[[], bool] | None = None,
    ):
        self.cwd = Path(cwd)
        self._run = run or self._default_run
        self._rtk_available = rtk_available or (lambda: shutil.which("rtk") is not None)

    @staticmethod
    def _default_run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(command, cwd=cwd, check=False, capture_output=True, text=True)

    def run(self, command: list[str], *, machine_output: bool) -> Result:
        executed = command
        if not machine_output and self._rtk_available():
            executed = ["rtk", *command]
        try:
            process = self._run(executed, self.cwd)
        except FileNotFoundError:
            return Result(False, "COMMAND_NOT_AVAILABLE", data={"command": command[0]})
        return Result(
            process.returncode == 0,
            "OK" if process.returncode == 0 else "COMMAND_FAILED",
            data={"stdout": process.stdout, "stderr": process.stderr, "command": executed},
        )
