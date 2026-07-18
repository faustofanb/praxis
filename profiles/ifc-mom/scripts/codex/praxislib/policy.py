from __future__ import annotations

import json
import time
import tomllib
from pathlib import Path
from subprocess import PIPE
from typing import Any

from momlib.process import run_command


POLICY_REPORT = ".praxis/out/policy-report.json"
ROOT_PLATFORM_DIRS = [".github", ".opencode", ".vscode", ".worktree", ".worktrees"]


def _check(status: bool, policy_id: str, message: str) -> dict[str, str]:
    return {"id": policy_id, "status": "PASS" if status else "FAIL", "message": message}


def _commands(root: Path) -> list[dict[str, Any]]:
    commands: list[dict[str, Any]] = []
    for path in [root / ".praxis" / "commands.toml", *sorted((root / ".praxis" / "extensions").glob("*/commands.toml"))]:
        if not path.is_file():
            continue
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
        for command in payload.get("command", []):
            if isinstance(command, dict):
                command = {**command, "_source": path.relative_to(root).as_posix()}
                commands.append(command)
    return commands


def _has_git_metadata(root: Path) -> bool:
    completed = run_command(
        ["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
        root,
        text=True,
        stdout=PIPE,
        stderr=PIPE,
        check=False,
    )
    return completed.returncode == 0


def _path_is_committed_or_present(root: Path, relative: str) -> bool:
    if not _has_git_metadata(root):
        return (root / relative).exists()
    completed = run_command(
        ["git", "-C", str(root), "ls-files", "--", relative],
        root,
        text=True,
        stdout=PIPE,
        stderr=PIPE,
        check=False,
    )
    return bool(completed.stdout.strip())


def policy_report(root: Path) -> dict[str, Any]:
    """Evaluate portable Praxis policy checks with a no-dependency fallback."""
    checks: list[dict[str, str]] = []
    checks.append(
        _check(
            (root / "praxis.projects.toml").is_file(),
            "project-index-at-root",
            "praxis.projects.toml must exist at the repository root",
        )
    )
    for directory in ROOT_PLATFORM_DIRS:
        checks.append(
            _check(
                not _path_is_committed_or_present(root, directory),
                "no-core-platform-directory",
                f"{directory} must be generated from a platform template, not committed as Praxis core",
            )
        )
    checks.append(
        _check(
            not (root / ".codex" / "agent-contracts").exists(),
            "codex-thin-entry",
            ".codex/agent-contracts must move to .praxis/contracts/agents",
        )
    )
    for command in _commands(root):
        risk = command.get("risk")
        if risk in {"destructive", "delivery", "commit"}:
            checks.append(
                _check(
                    command.get("requires_confirmation") is True,
                    "confirmed-protected-command",
                    f"{command.get('id', '<unknown>')} {risk} commands require confirmation",
                )
            )
    failed = sum(1 for item in checks if item["status"] == "FAIL")
    return {
        "schemaVersion": 1,
        "generatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "status": "PASS" if failed == 0 else "FAIL",
        "engine": "python",
        "summary": {"total": len(checks), "failed": failed},
        "checks": checks,
    }


def write_policy_report(root: Path) -> Path:
    """Write the Praxis policy report."""
    report = policy_report(root)
    path = root / POLICY_REPORT
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Praxis policy check: {report['status']}")
    print(f"  report: {path}")
    if report["status"] != "PASS":
        print("Policy failures:")
        for item in report["checks"]:
            if item["status"] == "FAIL":
                print(f"  - {item['message']}")
    return path
