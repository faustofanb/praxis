#!/usr/bin/env python3
"""Sync a packaged Praxis profile into a workspace."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
PROFILE_ROOT = PLUGIN_ROOT / "profiles"
PROFILE_METADATA_FILES = {"workspaces.json"}
PROFILE_IGNORED_PARTS = {"__pycache__"}
PROFILE_IGNORED_SUFFIXES = {".pyc"}


def _should_sync(relative_path: Path) -> bool:
    return (
        relative_path.as_posix() not in PROFILE_METADATA_FILES
        and not any(part in PROFILE_IGNORED_PARTS for part in relative_path.parts)
        and relative_path.suffix not in PROFILE_IGNORED_SUFFIXES
    )


def sync_profile(
    workspace: str | Path,
    profile: str,
    *,
    force: bool = False,
    dry_run: bool = False,
) -> list[str]:
    root = Path(workspace).expanduser().resolve()
    source_root = PROFILE_ROOT / profile
    if not source_root.is_dir():
        raise ValueError(f"unknown Praxis profile: {profile}")

    written: list[str] = []
    for source_path in sorted(path for path in source_root.rglob("*") if path.is_file()):
        relative_path = source_path.relative_to(source_root)
        if not _should_sync(relative_path):
            continue
        target_path = root / relative_path
        if target_path.exists() and not force:
            continue
        written.append(relative_path.as_posix())
        if dry_run:
            continue
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)
    return written


def available_profiles() -> list[str]:
    if not PROFILE_ROOT.is_dir():
        return []
    return sorted(path.name for path in PROFILE_ROOT.iterdir() if path.is_dir())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", help="Workspace root to update")
    parser.add_argument("profile", choices=available_profiles(), help="Packaged profile name")
    parser.add_argument("--force", action="store_true", help="Overwrite existing profile files")
    parser.add_argument("--dry-run", action="store_true", help="List files without writing")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    args = parser.parse_args(argv)

    written = sync_profile(args.workspace, args.profile, force=args.force, dry_run=args.dry_run)
    if args.json:
        print(json.dumps({"profile": args.profile, "written": written}, ensure_ascii=False, indent=2))
    elif written:
        action = "would write" if args.dry_run else "written"
        print(f"{action}:")
        for path in written:
            print(f"  - {path}")
    else:
        print("no files written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
