from __future__ import annotations

import re
from pathlib import Path

from .paths import ROOT_DIR
from .process import capture


COMMIT_SUBJECT_PATTERN = re.compile(r"^(feat|refactor|fix|chore)\([^()\s]+\):\s+\S.*$")
DETAIL_LINE_PATTERN = re.compile(r"^\d+\.\s+\S.*$")
OFFICIAL_MIGRATION_MARKERS = ["db/migration/", "/db/migration/", "src/main/resources/db/migration/"]
MENU_MIGRATION_PATH_MARKERS = ["菜单", "授权", "menu", "auth", "authority"]
MENU_MIGRATION_CONTENT_MARKERS = ["菜单", "授权", "def_resource", "def_authority", "resource", "authority", "menu"]


def commit_message(repo_dir: Path, commit: str) -> str:
    """Return the full commit message for delivery policy checks."""
    return capture(["git", "-C", str(repo_dir), "log", "-1", "--format=%B", commit], ROOT_DIR)


def commit_changed_files(repo_dir: Path, commit: str) -> list[str]:
    """Return files changed by a commit."""
    output = capture(["git", "-C", str(repo_dir), "diff-tree", "--no-commit-id", "--name-only", "-r", commit], ROOT_DIR)
    return sorted(line for line in output.splitlines() if line)


def commit_file_content(repo_dir: Path, commit: str, path: str) -> str:
    """Return a file content as recorded by a commit."""
    return capture(["git", "-C", str(repo_dir), "show", f"{commit}:{path}"], ROOT_DIR)


def delivery_commit_message_issues(commit: str, message: str) -> list[str]:
    """Validate that a feature delivery commit has a structured body."""
    normalized = message.replace("\r\n", "\n").strip()
    lines = normalized.splitlines()
    if (
        len(lines) < 3
        or not COMMIT_SUBJECT_PATTERN.match(lines[0])
        or lines[1] != ""
        or not all(DETAIL_LINE_PATTERN.match(line) for line in lines[2:] if line.strip())
        or any(not line.strip() for line in lines[2:])
    ):
        return [
            f"delivery commit message is not structured: {commit}",
            "expected: feat|refactor|fix|chore(scope): subject, blank line, then numbered detail lines",
        ]
    return []


def is_pad_api_file(path: str) -> bool:
    """Detect changed MES PAD BFF controller files that normally require menu authorization."""
    normalized = path.replace("\\", "/").lower()
    return (
        normalized.endswith(".java")
        and "lamp-mes-bff" in normalized
        and "/pad/controller/" in normalized
        and "controller" in normalized.rsplit("/", 1)[-1]
    )


def is_official_migration(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return normalized.lower().endswith(".sql") and any(marker in normalized for marker in OFFICIAL_MIGRATION_MARKERS)


def is_menu_authorization_migration(repo_dir: Path, commit: str, path: str) -> bool:
    """Detect menu/authorization Flyway scripts by path or SQL content."""
    if not is_official_migration(path):
        return False
    lowered_path = path.lower()
    if any(marker in lowered_path or marker in path for marker in MENU_MIGRATION_PATH_MARKERS):
        return True
    content = commit_file_content(repo_dir, commit, path).lower()
    return any(marker in content for marker in MENU_MIGRATION_CONTENT_MARKERS)


def delivery_policy_issues(repo_dir: Path, commits: list[str]) -> list[str]:
    """Return issues that must block feature delivery."""
    issues: list[str] = []
    pad_api_files: list[str] = []
    has_menu_migration = False

    for commit in commits:
        issues.extend(delivery_commit_message_issues(commit, commit_message(repo_dir, commit)))
        for path in commit_changed_files(repo_dir, commit):
            if is_pad_api_file(path):
                pad_api_files.append(path)
            if is_menu_authorization_migration(repo_dir, commit, path):
                has_menu_migration = True

    if pad_api_files and not has_menu_migration:
        issues.append("MES PAD controller delivery is missing menu authorization Flyway migration")
        for path in pad_api_files:
            issues.append(f"PAD controller file: {path}")

    return issues
