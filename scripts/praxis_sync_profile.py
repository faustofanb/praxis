#!/usr/bin/env python3
"""Sync a packaged Praxis profile into a workspace."""

from __future__ import annotations

import argparse
import json
import shutil
import tomllib
from pathlib import Path
from typing import Any


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
PROFILE_ROOT = PLUGIN_ROOT / "profiles"
PROFILE_METADATA_FILES = {"profile.toml", "workspaces.json"}
PROFILE_IGNORED_PARTS = {".DS_Store", "__pycache__"}
PROFILE_IGNORED_SUFFIXES = {".pyc"}
SHARED_RUNTIME_ROOT = PLUGIN_ROOT / "runtime" / "praxis_core"
SHARED_RUNTIME_TARGET = Path("scripts/praxis/praxis_core")


class ProfileMetadata:
    def __init__(
        self,
        *,
        id: str,
        version: str,
        source_root: Path,
        extension_root: Path,
        managed_roots: tuple[Path, ...],
        obsolete_roots: tuple[Path, ...],
        project_kinds: tuple[str, ...],
    ) -> None:
        self.id = id
        self.version = version
        self.source_root = source_root
        self.extension_root = extension_root
        self.managed_roots = managed_roots
        self.obsolete_roots = obsolete_roots
        self.project_kinds = project_kinds


def _should_sync(relative_path: Path) -> bool:
    return (
        relative_path.as_posix() not in PROFILE_METADATA_FILES
        and not any(part in PROFILE_IGNORED_PARTS for part in relative_path.parts)
        and relative_path.suffix not in PROFILE_IGNORED_SUFFIXES
    )


def load_profile_metadata(source_root: Path) -> ProfileMetadata | None:
    metadata_path = source_root / "profile.toml"
    if not metadata_path.is_file():
        return None
    try:
        payload = tomllib.loads(metadata_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"invalid profile metadata: {metadata_path}: {exc}") from exc
    if payload.get("schema_version") != 1:
        raise ValueError(f"unsupported profile metadata schema: {metadata_path}")

    profile_id = _required_string(payload, "id", metadata_path)
    version = _required_string(payload, "version", metadata_path)
    extension_root = Path(_required_string(payload, "extension_root", metadata_path))
    managed_roots = _required_path_list(payload, "managed_roots", metadata_path)
    obsolete_roots = _required_path_list(payload, "obsolete_roots", metadata_path)
    project_kinds = tuple(_required_string_list(payload, "project_kinds", metadata_path))
    return ProfileMetadata(
        id=profile_id,
        version=version,
        source_root=source_root,
        extension_root=extension_root,
        managed_roots=tuple(managed_roots),
        obsolete_roots=tuple(obsolete_roots),
        project_kinds=project_kinds,
    )


def _required_string(payload: dict[str, Any], key: str, metadata_path: Path) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"profile metadata requires string {key}: {metadata_path}")
    return value.strip()


def _required_string_list(payload: dict[str, Any], key: str, metadata_path: Path) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"profile metadata requires string list {key}: {metadata_path}")
    return [item.strip() for item in value]


def _required_path_list(payload: dict[str, Any], key: str, metadata_path: Path) -> list[Path]:
    return [Path(item) for item in _required_string_list(payload, key, metadata_path)]


def profile_metadata(profile: str) -> ProfileMetadata:
    matches = []
    if PROFILE_ROOT.is_dir():
        for source_root in sorted(path for path in PROFILE_ROOT.iterdir() if path.is_dir()):
            metadata = load_profile_metadata(source_root)
            if metadata is not None and metadata.id == profile:
                matches.append(metadata)
    if not matches:
        raise ValueError(f"unknown Praxis profile: {profile}")
    if len(matches) > 1:
        raise ValueError(f"duplicate Praxis profile id: {profile}")
    return matches[0]


def sync_sources(metadata: ProfileMetadata) -> dict[Path, Path]:
    """Map workspace-relative targets to canonical profile and shared-core sources."""
    sources: dict[Path, Path] = {}
    for source_path in sorted(path for path in metadata.source_root.rglob("*") if path.is_file()):
        relative_path = source_path.relative_to(metadata.source_root)
        if _should_sync(relative_path):
            sources[relative_path] = source_path
    if SHARED_RUNTIME_ROOT.is_dir():
        for source_path in sorted(path for path in SHARED_RUNTIME_ROOT.rglob("*") if path.is_file()):
            relative_path = source_path.relative_to(SHARED_RUNTIME_ROOT)
            if _should_sync(relative_path):
                target = SHARED_RUNTIME_TARGET / relative_path
                if target in sources:
                    raise ValueError(f"profile file conflicts with shared Praxis core: {target}")
                sources[target] = source_path
    return sources


def sync_profile(
    workspace: str | Path,
    profile: str,
    *,
    force: bool = False,
    dry_run: bool = False,
    prune: bool = False,
) -> list[str]:
    root = Path(workspace).expanduser().resolve()
    metadata = profile_metadata(profile)
    sources = sync_sources(metadata)

    if prune:
        _prune_managed_files(root, metadata, dry_run=dry_run)

    written: list[str] = []
    for relative_path, source_path in sorted(sources.items()):
        target_path = root / relative_path
        if target_path.exists() and not force:
            continue
        written.append(relative_path.as_posix())
        if dry_run:
            continue
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)
    return written


def _prune_managed_files(root: Path, metadata: ProfileMetadata, *, dry_run: bool) -> None:
    expected_files = set(sync_sources(metadata))
    for relative_root in metadata.managed_roots:
        source_managed_root = metadata.source_root / relative_root
        target_root = root / relative_root
        if not source_managed_root.is_dir() or not target_root.is_dir():
            continue
        for target in sorted((path for path in target_root.rglob("*") if path.is_file()), reverse=True):
            relative_file = target.relative_to(root)
            if relative_file not in expected_files and not dry_run:
                target.unlink()
        _remove_empty_dirs(target_root, dry_run=dry_run)


    for relative_root in metadata.obsolete_roots:
        target_root = root / relative_root
        if not target_root.exists():
            continue
        if dry_run:
            continue
        if target_root.is_dir():
            shutil.rmtree(target_root)
        else:
            target_root.unlink()


def _remove_empty_dirs(root: Path, *, dry_run: bool) -> None:
    if dry_run:
        return
    for path in sorted((path for path in root.rglob("*") if path.is_dir()), reverse=True):
        try:
            path.rmdir()
        except OSError:
            pass


def available_profiles() -> list[str]:
    if not PROFILE_ROOT.is_dir():
        return []
    profiles: list[str] = []
    for path in sorted(source for source in PROFILE_ROOT.iterdir() if source.is_dir()):
        metadata = load_profile_metadata(path)
        if metadata is not None:
            profiles.append(metadata.id)
    return sorted(profiles)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", help="Workspace root to update")
    parser.add_argument("profile", choices=available_profiles(), help="Packaged profile id")
    parser.add_argument("--force", action="store_true", help="Overwrite existing profile files")
    parser.add_argument("--dry-run", action="store_true", help="List files without writing")
    parser.add_argument("--prune", action="store_true", help="Remove stale files from profile-managed directories")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    args = parser.parse_args(argv)

    written = sync_profile(args.workspace, args.profile, force=args.force, dry_run=args.dry_run, prune=args.prune)
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
