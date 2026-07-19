#!/usr/bin/env python3
"""Sync a packaged Praxis profile into every registered workspace."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from praxis_sync_profile import sync_profile  # noqa: E402

REGISTRY_ENV = "PRAXIS_WORKSPACES_REGISTRY"
LOCAL_REGISTRY_NAME = "workspaces.local.json"


def default_registry_path(registry_path: str | Path | None = None) -> Path:
    if registry_path is not None:
        return Path(registry_path).expanduser().resolve()

    env_path = os.environ.get(REGISTRY_ENV)
    if env_path:
        return Path(env_path).expanduser().resolve()

    local_registry = PLUGIN_ROOT / LOCAL_REGISTRY_NAME
    if local_registry.is_file():
        return local_registry

    raise FileNotFoundError(
        "workspace registry not configured; provide --registry, set "
        f"{REGISTRY_ENV}, or create {local_registry}"
    )


def load_registry(path: str | Path) -> dict[str, Any]:
    registry_path = Path(path).expanduser().resolve()
    if not registry_path.is_file():
        raise FileNotFoundError(f"workspace registry not found: {registry_path}")
    return json.loads(registry_path.read_text(encoding="utf-8"))


def profile_workspaces(profile: str, registry: dict[str, Any]) -> list[dict[str, str]]:
    profile_config = registry.get("profiles", {}).get(profile)
    if not profile_config:
        raise ValueError(f"profile not found in workspace registry: {profile}")

    workspaces = profile_config.get("workspaces", [])
    if not isinstance(workspaces, list):
        raise ValueError(f"profile workspaces must be a list: {profile}")

    normalized: list[dict[str, str]] = []
    for index, workspace in enumerate(workspaces):
        if not isinstance(workspace, dict):
            raise ValueError(f"workspace entry must be an object: {profile}[{index}]")
        name = str(workspace.get("name") or "").strip()
        path = str(workspace.get("path") or "").strip()
        if not name or not path:
            raise ValueError(f"workspace entry requires name and path: {profile}[{index}]")
        normalized.append({"name": name, "path": path})
    return normalized


def sync_workspaces(
    profile: str,
    *,
    registry_path: str | Path | None = None,
    force: bool = False,
    dry_run: bool = False,
    prune: bool = False,
) -> list[dict[str, Any]]:
    registry = load_registry(default_registry_path(registry_path))
    results: list[dict[str, Any]] = []
    for workspace in profile_workspaces(profile, registry):
        files = sync_profile(workspace["path"], profile, force=force, dry_run=dry_run, prune=prune)
        results.append(
            {
                "name": workspace["name"],
                "path": str(Path(workspace["path"]).expanduser()),
                "status": "would-write" if dry_run else "written",
                "files": files,
            }
        )
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", help="Packaged profile id")
    parser.add_argument("--registry", help="Workspace registry JSON path")
    parser.add_argument("--force", action="store_true", help="Overwrite existing profile files")
    parser.add_argument("--dry-run", action="store_true", help="List files without writing")
    parser.add_argument("--prune", action="store_true", help="Remove stale files from profile-managed directories")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    args = parser.parse_args(argv)

    try:
        results = sync_workspaces(
            args.profile,
            registry_path=args.registry,
            force=args.force,
            dry_run=args.dry_run,
            prune=args.prune,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps({"profile": args.profile, "workspaces": results}, ensure_ascii=False, indent=2))
        return 0

    action = "would write" if args.dry_run else "written"
    for result in results:
        print(f"{result['name']}: {action} {len(result['files'])} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
