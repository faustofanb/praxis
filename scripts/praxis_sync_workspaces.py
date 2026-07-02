#!/usr/bin/env python3
"""Sync a packaged Praxis profile into every registered workspace."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent


def _load_sync_profile_module():
    module_name = "praxis_sync_profile"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT_DIR / "praxis_sync_profile.py")
    if spec is None or spec.loader is None:
        raise ImportError("cannot load praxis_sync_profile.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_SYNC_PROFILE = _load_sync_profile_module()
PROFILE_ROOT = _SYNC_PROFILE.PROFILE_ROOT
sync_profile = _SYNC_PROFILE.sync_profile


def default_registry_path(profile: str) -> Path:
    return PROFILE_ROOT / profile / "workspaces.json"


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
) -> list[dict[str, Any]]:
    registry = load_registry(registry_path or default_registry_path(profile))
    results: list[dict[str, Any]] = []
    for workspace in profile_workspaces(profile, registry):
        files = sync_profile(workspace["path"], profile, force=force, dry_run=dry_run)
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
    parser.add_argument("profile", help="Packaged profile name")
    parser.add_argument("--registry", help="Workspace registry JSON path")
    parser.add_argument("--force", action="store_true", help="Overwrite existing profile files")
    parser.add_argument("--dry-run", action="store_true", help="List files without writing")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    args = parser.parse_args(argv)

    results = sync_workspaces(args.profile, registry_path=args.registry, force=args.force, dry_run=args.dry_run)
    if args.json:
        print(json.dumps({"profile": args.profile, "workspaces": results}, ensure_ascii=False, indent=2))
        return 0

    action = "would write" if args.dry_run else "written"
    for result in results:
        print(f"{result['name']}: {action} {len(result['files'])} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
