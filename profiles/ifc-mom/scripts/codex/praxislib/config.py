from __future__ import annotations

from pathlib import Path
from typing import Any

from momlib.paths import ROOT_DIR
from momlib.process import fail
from praxislib.project_index import read_project_index


def load_config() -> dict[str, Any]:
    """Load the Praxis project index from the repository root."""
    try:
        payload, _source = read_project_index(ROOT_DIR)
    except FileNotFoundError as exc:
        fail(str(exc))
    return payload


def projects(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return project short names to project configuration."""
    return config.get("projects", {})


def project_config(config: dict[str, Any], name: str) -> dict[str, Any]:
    """Read a project config by short name."""
    project = projects(config).get(name)
    if not project:
        fail(f"unknown project: {name}")
    return project


def project_dir(config: dict[str, Any], name: str) -> Path:
    """Resolve a project path relative to the workspace root."""
    project = project_config(config, name)
    path = project.get("path")
    if not path:
        fail(f"project has no path: {name}")
    repo_dir = ROOT_DIR / path
    if not repo_dir.is_dir():
        fail(f"project path not found: {path}")
    return repo_dir
