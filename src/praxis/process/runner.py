from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CommandResult:
    args: list[str]
    returncode: int
    stdout: str = ""
    stderr: str = ""
    diagnostics: list[dict[str, Any]] = field(default_factory=list)


def run_command(
    args: list[str], env: dict[str, str] | None = None, machine_output: bool = False
) -> CommandResult:
    merged = os.environ.copy()
    if env:
        path = env.get("PATH")
        if path:
            merged["PATH"] = path
        for key, value in env.items():
            if key != "PATH":
                merged[key] = value
    diagnostics: list[dict[str, Any]] = []
    executable_args = list(args)
    if args and args[0] == "git" and not machine_output:
        rtk = shutil.which("rtk", path=merged.get("PATH"))
        if rtk:
            executable_args = [rtk, *args]
        else:
            diagnostics.append(
                {"code": "RTK_FALLBACK", "message": "未找到 RTK，已直接运行原命令。"}
            )
    proc = subprocess.run(executable_args, text=True, capture_output=True, env=merged, check=False)
    return CommandResult(
        args=executable_args,
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        diagnostics=diagnostics,
    )
