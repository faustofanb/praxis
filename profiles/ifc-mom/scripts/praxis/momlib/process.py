from __future__ import annotations

import os
import re
import subprocess
import shutil
import sys
from pathlib import Path


SYSTEM_GIT = Path("/usr/bin/git")
ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$")


def fail(message: str) -> None:
    """输出统一错误格式并终止当前脚本。"""
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def split_command_env(command: list[str]) -> tuple[dict[str, str], list[str]]:
    """Split leading KEY=VALUE arguments from a shell-free command vector."""
    overrides: dict[str, str] = {}
    index = 0
    while index < len(command) and ENV_ASSIGNMENT.match(command[index]):
        key, value = command[index].split("=", 1)
        overrides[key] = value
        index += 1
    return overrides, command[index:]


def command_argv(command: list[str]) -> list[str]:
    """Resolve workflow Git commands through RTK when available.

    RTK is an optimization layer. When it is missing, keep the previous macOS
    system Git fallback for CodeUp HTTPS credentials.
    """
    _, argv = split_command_env(command)
    if argv and argv[0] == "git":
        rtk = shutil.which("rtk")
        if rtk:
            return [rtk, *argv]
        return [str(SYSTEM_GIT), *argv[1:]]
    return argv


def machine_command_argv(command: list[str]) -> list[str]:
    """Bypass RTK filtering when callers parse command stdout."""
    _, argv = split_command_env(command)
    if argv and argv[0] == "git":
        return [str(SYSTEM_GIT), *argv[1:]]
    return argv


def command_env(command: list[str]) -> dict[str, str] | None:
    """Return environment overrides for subprocesses launched by workflow scripts."""
    overrides, argv = split_command_env(command)
    if not argv:
        return None
    env: dict[str, str] | None = None
    if argv[0] == "git":
        env = os.environ.copy()
        # Git fsmonitor can emit IPC warnings in Codex sandboxes; disable only for workflow subprocesses.
        env["GIT_CONFIG_COUNT"] = "1"
        env["GIT_CONFIG_KEY_0"] = "core.fsmonitor"
        env["GIT_CONFIG_VALUE_0"] = "false"
    if overrides:
        if env is None:
            env = os.environ.copy()
        env.update(overrides)
    return env


def run_exit(command: list[str], cwd: Path) -> None:
    """Run a command and use its exit code as the current script exit code."""
    completed = run_command(command, cwd)
    raise SystemExit(completed.returncode)


def run_checked(command: list[str], cwd: Path) -> None:
    """Run a command that must succeed before the workflow can continue."""
    completed = run_command(command, cwd)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def run_command(command: list[str], cwd: Path, **kwargs: object) -> subprocess.CompletedProcess:
    """Run a workflow command through the shared command resolver."""
    env = kwargs.pop("env", None) or command_env(command)
    return subprocess.run(command_argv(command), cwd=cwd, env=env, **kwargs)


def command_succeeds(command: list[str], cwd: Path) -> bool:
    """Run a command quietly and return whether it succeeds."""
    completed = run_command(
        command,
        cwd=cwd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return completed.returncode == 0


def capture(command: list[str], cwd: Path) -> str:
    completed = subprocess.run(
        machine_command_argv(command),
        cwd=cwd,
        env=command_env(command),
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return completed.stdout.rstrip("\r\n")
