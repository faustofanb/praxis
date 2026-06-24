#!/usr/bin/env python3
"""Check whether a workspace has the thin Praxis entry files."""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


REQUIRED_FILES = (
    "AGENTS.md",
    "praxis.toml",
    "praxis.projects.toml",
    ".praxis/core.toml",
    ".praxis/project-adapter.toml",
    ".praxis/contracts/agents/turn.schema.json",
)


@dataclass
class WorkspaceReport:
    workspace: str
    ok: bool
    missing_files: list[str] = field(default_factory=list)
    projects: list[dict[str, str | None]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def analyze_workspace(workspace: str | Path) -> WorkspaceReport:
    root = Path(workspace).expanduser().resolve()
    missing = [path for path in REQUIRED_FILES if not (root / path).is_file()]
    errors: list[str] = []
    warnings: list[str] = []
    projects: list[dict[str, str | None]] = []

    project_index = root / "praxis.projects.toml"
    if project_index.is_file():
        try:
            payload = tomllib.loads(project_index.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            errors.append(f"praxis.projects.toml is not readable TOML: {exc}")
        else:
            projects, project_errors = collect_projects(payload)
            errors.extend(project_errors)

    workflow_rule = root / ".praxis" / "rules" / "praxis-workflow.md"
    if not workflow_rule.is_file():
        warnings.append(".praxis/rules/praxis-workflow.md is absent; plugin skill will supply shared guidance")

    ok = not missing and not errors
    return WorkspaceReport(
        workspace=str(root),
        ok=ok,
        missing_files=missing,
        projects=projects,
        warnings=warnings,
        errors=errors,
    )


def collect_projects(payload: dict[str, Any]) -> tuple[list[dict[str, str | None]], list[str]]:
    raw_projects = payload.get("projects")
    if not isinstance(raw_projects, dict) or not raw_projects:
        return [], ["praxis.projects.toml must define at least one [projects.<name>] entry"]

    projects: list[dict[str, str | None]] = []
    errors: list[str] = []
    for name, raw_project in sorted(raw_projects.items()):
        if not isinstance(raw_project, dict):
            errors.append(f"project {name!r} must be a table")
            continue
        project = {
            "name": str(name),
            "path": string_or_none(raw_project.get("path")),
            "kind": string_or_none(raw_project.get("kind")),
            "defaultBranch": string_or_none(raw_project.get("defaultBranch")),
            "upstreamBranch": string_or_none(raw_project.get("upstreamBranch")),
        }
        for field_name in ("path", "kind", "defaultBranch"):
            if not project[field_name]:
                errors.append(f"project {name!r} is missing {field_name}")
        projects.append(project)
    return projects, errors


def string_or_none(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None


def report_to_json(report: WorkspaceReport) -> str:
    return json.dumps(asdict(report), ensure_ascii=False, indent=2)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", nargs="?", default=".", help="Workspace root to check")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    args = parser.parse_args(argv)

    report = analyze_workspace(args.workspace)
    if args.json:
        print(report_to_json(report))
    else:
        print(f"Praxis workspace: {report.workspace}")
        print(f"status: {'ok' if report.ok else 'failed'}")
        if report.missing_files:
            print("missing files:")
            for path in report.missing_files:
                print(f"  - {path}")
        if report.errors:
            print("errors:")
            for error in report.errors:
                print(f"  - {error}")
        if report.warnings:
            print("warnings:")
            for warning in report.warnings:
                print(f"  - {warning}")
        if report.projects:
            print("projects:")
            for project in report.projects:
                print(
                    "  - {name}: path={path}, kind={kind}, defaultBranch={defaultBranch}, "
                    "upstreamBranch={upstreamBranch}".format(**project)
                )
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
