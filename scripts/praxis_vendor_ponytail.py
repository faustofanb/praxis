#!/usr/bin/env python3
"""Vendor the allowed Ponytail 4.8.4 runtime surface into this plugin."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tomllib
from pathlib import Path
from typing import Iterable

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
PONYTAIL_VERSION = "4.8.4"
PONYTAIL_SOURCE = "https://github.com/DietrichGebert/ponytail"
LOCK_PATH = PLUGIN_ROOT / "vendor" / "ponytail.lock.json"
LICENSE_TARGET = PLUGIN_ROOT / "vendor" / "ponytail" / "LICENSE"
SKILL_NAMES = (
    "ponytail",
    "ponytail-audit",
    "ponytail-debt",
    "ponytail-gain",
    "ponytail-help",
    "ponytail-review",
)
COMMAND_NAMES = (
    "ponytail.toml",
    "ponytail-audit.toml",
    "ponytail-debt.toml",
    "ponytail-gain.toml",
    "ponytail-help.toml",
    "ponytail-review.toml",
)
HOOK_FILES = (
    "claude-codex-hooks.json",
    "ponytail-activate.js",
    "ponytail-subagent.js",
    "ponytail-mode-tracker.js",
    "ponytail-config.js",
    "ponytail-instructions.js",
    "ponytail-runtime.js",
)


def allowed_file_map(source_root: Path) -> dict[Path, Path]:
    mapping: dict[Path, Path] = {}
    for skill in SKILL_NAMES:
        source = source_root / "skills" / skill / "SKILL.md"
        mapping[source] = PLUGIN_ROOT / "skills" / skill / "SKILL.md"
    for command in COMMAND_NAMES:
        source = source_root / "commands" / command
        mapping[source] = PLUGIN_ROOT / "commands" / command
    mapping[source_root / "hooks" / "claude-codex-hooks.json"] = PLUGIN_ROOT / "hooks" / "claude-codex-hooks.json"
    for hook in HOOK_FILES[1:]:
        mapping[source_root / "hooks" / hook] = PLUGIN_ROOT / "hooks" / hook
    mapping[source_root / "pi-extension" / "index.js"] = PLUGIN_ROOT / "pi-extension" / "index.js"
    mapping[source_root / "LICENSE"] = LICENSE_TARGET
    return mapping


def assert_source_version(source_root: Path) -> None:
    package_path = source_root / "package.json"
    payload = json.loads(package_path.read_text(encoding="utf-8"))
    version = payload.get("version")
    if version != PONYTAIL_VERSION:
        raise ValueError(f"expected Ponytail {PONYTAIL_VERSION}, got {version!r}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative(path: Path) -> str:
    return path.relative_to(PLUGIN_ROOT).as_posix()


def write_lock(files: Iterable[Path]) -> None:
    payload = {
        "source": PONYTAIL_SOURCE,
        "version": PONYTAIL_VERSION,
        "files": {relative(path): sha256(path) for path in sorted(files)},
    }
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCK_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sync(source_root: Path) -> None:
    assert_source_version(source_root)
    mapping = allowed_file_map(source_root)
    missing = [source for source in mapping if not source.is_file()]
    if missing:
        raise FileNotFoundError("missing Ponytail allowlist files: " + ", ".join(str(path) for path in missing))
    written: list[Path] = []
    for source, target in sorted(mapping.items(), key=lambda item: item[1].as_posix()):
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        written.append(target)
        print(f"written: {relative(target)}")
    write_lock(written)
    print(f"written: {relative(LOCK_PATH)}")


def check() -> list[str]:
    if not LOCK_PATH.is_file():
        return [f"missing: {relative(LOCK_PATH)}"]
    payload = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    drift: list[str] = []
    if payload.get("source") != PONYTAIL_SOURCE:
        drift.append("drift: source")
    if payload.get("version") != PONYTAIL_VERSION:
        drift.append("drift: version")
    files = payload.get("files")
    if not isinstance(files, dict):
        return ["invalid: files"]
    for name, expected_hash in sorted(files.items()):
        path = PLUGIN_ROOT / name
        if not path.is_file():
            drift.append(f"missing: {name}")
            continue
        actual_hash = sha256(path)
        if actual_hash != expected_hash:
            drift.append(f"drift: {name}")
    return drift


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", help="Ponytail source root to vendor")
    parser.add_argument("--check", action="store_true", help="Check vendored files against vendor/ponytail.lock.json")
    args = parser.parse_args(argv)

    if args.check:
        drift = check()
        if drift:
            for entry in drift:
                print(entry)
            return 1
        print("ponytail vendored files are up to date")
        return 0
    if not args.source:
        parser.error("--source is required unless --check is used")
    sync(Path(args.source).expanduser().resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
