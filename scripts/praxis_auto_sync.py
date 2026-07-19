#!/usr/bin/env python3
"""Synchronize an installed Praxis profile at session start when a workspace opts in."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

LOCK_GRACE_SECONDS = 30


@dataclass(frozen=True)
class AutoSyncResult:
    status: str
    workspace: str | None = None
    profile: str | None = None
    files: int = 0
    message: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            key: value
            for key, value in {
                "status": self.status,
                "workspace": self.workspace,
                "profile": self.profile,
                "files": self.files,
                "message": self.message,
            }.items()
            if value is not None
        }


def find_workspace(start: str | Path) -> Path | None:
    candidate = Path(start).expanduser().resolve()
    if candidate.is_file():
        candidate = candidate.parent
    for root in (candidate, *candidate.parents):
        if (root / "praxis.toml").is_file() and (root / "praxis.projects.toml").is_file():
            return root
    return None


def load_sync_module(plugin_root: Path) -> ModuleType:
    script = plugin_root / "scripts" / "praxis_sync_profile.py"
    spec = importlib.util.spec_from_file_location("praxis_auto_sync_profile", script)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load profile sync module: {script}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def configured_profile(workspace: Path, plugin_root: Path) -> tuple[str | None, bool]:
    marker = workspace / ".praxis" / "plugin-sync.toml"
    if marker.is_file():
        payload = tomllib.loads(marker.read_text(encoding="utf-8"))
        enabled = bool(payload.get("auto_sync", True))
        profile = str(payload.get("id") or "").strip() or None
        return profile, enabled

    installed: list[str] = []
    extension_root = workspace / ".praxis" / "extensions"
    if extension_root.is_dir():
        for extension in sorted(extension_root.glob("*/extension.toml")):
            fallback = extension.parent.name
            try:
                payload = tomllib.loads(extension.read_text(encoding="utf-8"))
            except (OSError, tomllib.TOMLDecodeError):
                payload = {}
            profile = str(payload.get("id") or fallback).strip()
            packaged = plugin_root / "profiles" / profile / "profile.toml"
            if profile and packaged.is_file():
                installed.append(profile)
    unique = sorted(set(installed))
    return (unique[0], True) if len(unique) == 1 else (None, True)


def assert_safe_managed_targets(workspace: Path, metadata: Any, sync_module: ModuleType) -> None:
    relative_paths = [
        *sync_module.sync_sources(metadata),
        *metadata.managed_roots,
        *metadata.obsolete_roots,
    ]
    checked: set[Path] = set()
    for relative_path in relative_paths:
        current = workspace
        for part in Path(relative_path).parts:
            current = current / part
            if current in checked:
                continue
            checked.add(current)
            if current.is_symlink():
                raise RuntimeError(f"managed Praxis path must not be a symlink: {current}")

    for relative_root in metadata.managed_roots:
        target_root = workspace / relative_root
        if not target_root.is_dir():
            continue
        for target in target_root.rglob("*"):
            if target.is_symlink():
                raise RuntimeError(f"managed Praxis path must not be a symlink: {target}")


def profile_is_current(workspace: Path, metadata: Any, sync_module: ModuleType) -> bool:
    sources = sync_module.sync_sources(metadata)
    expected = set(sources)
    for relative_path, source_path in sources.items():
        target = workspace / relative_path
        if not target.is_file() or target.read_bytes() != source_path.read_bytes():
            return False

    for relative_root in metadata.managed_roots:
        target_root = workspace / relative_root
        if not target_root.is_dir():
            continue
        for target in (path for path in target_root.rglob("*") if path.is_file()):
            relative_file = target.relative_to(workspace)
            if relative_file in expected:
                continue
            if any(part in sync_module.PROFILE_IGNORED_PARTS for part in relative_file.parts):
                continue
            if relative_file.suffix in sync_module.PROFILE_IGNORED_SUFFIXES:
                continue
            return False

    return not any((workspace / relative_root).exists() for relative_root in metadata.obsolete_roots)


def pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def acquire_lock(workspace: Path) -> tuple[int, Path] | None:
    lock_path = workspace / ".praxis" / "profile-sync.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            try:
                os.write(descriptor, f"{os.getpid()}\n".encode())
                os.fsync(descriptor)
            except BaseException:
                os.close(descriptor)
                lock_path.unlink(missing_ok=True)
                raise
            return descriptor, lock_path
        except FileExistsError:
            try:
                owner = int(lock_path.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                owner = -1
                try:
                    if time.time() - lock_path.stat().st_mtime < LOCK_GRACE_SECONDS:
                        return None
                except FileNotFoundError:
                    continue
            if pid_is_running(owner):
                return None
            lock_path.unlink(missing_ok=True)
    return None


def auto_sync(plugin_root: str | Path, workspace_start: str | Path) -> AutoSyncResult:
    plugin = Path(plugin_root).expanduser().resolve()
    workspace = find_workspace(workspace_start)
    if workspace is None:
        return AutoSyncResult(status="not-praxis")

    profile, enabled = configured_profile(workspace, plugin)
    if not enabled:
        return AutoSyncResult(status="disabled", workspace=str(workspace), profile=profile)
    if profile is None:
        return AutoSyncResult(status="no-profile", workspace=str(workspace))

    sync_module = load_sync_module(plugin)
    metadata = sync_module.profile_metadata(profile)
    assert_safe_managed_targets(workspace, metadata, sync_module)
    if profile_is_current(workspace, metadata, sync_module):
        return AutoSyncResult(status="current", workspace=str(workspace), profile=profile)

    lock = acquire_lock(workspace)
    if lock is None:
        return AutoSyncResult(status="busy", workspace=str(workspace), profile=profile)
    descriptor, lock_path = lock
    try:
        if profile_is_current(workspace, metadata, sync_module):
            return AutoSyncResult(status="current", workspace=str(workspace), profile=profile)
        written = sync_module.sync_profile(workspace, profile, force=True, prune=True)
        return AutoSyncResult(status="synced", workspace=str(workspace), profile=profile, files=len(written))
    finally:
        os.close(descriptor)
        lock_path.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plugin-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--workspace", default=os.getcwd())
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = auto_sync(args.plugin_root, args.workspace)
    except Exception as exc:
        result = AutoSyncResult(status="error", message=str(exc))
        exit_code = 1
    else:
        exit_code = 0

    if args.json:
        print(json.dumps(result.as_dict(), ensure_ascii=False))
    elif not args.quiet and result.status not in {"not-praxis", "no-profile"}:
        detail = f" ({result.profile})" if result.profile else ""
        print(f"Praxis profile auto-sync: {result.status}{detail}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
