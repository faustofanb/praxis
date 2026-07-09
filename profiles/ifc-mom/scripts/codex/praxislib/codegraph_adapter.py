from __future__ import annotations

import shutil
from pathlib import Path

from momlib.process import fail, run_command


ALLOWED_SUBCOMMANDS = {
    "init",
    "index",
    "sync",
    "status",
    "explore",
    "query",
    "node",
    "files",
    "callers",
    "callees",
    "impact",
    "affected",
}


def _git_dir(root: Path) -> Path | None:
    marker = root / ".git"
    if marker.is_dir():
        return marker
    if marker.is_file():
        prefix = "gitdir: "
        text = marker.read_text(encoding="utf-8", errors="ignore").strip()
        if text.startswith(prefix):
            path = Path(text[len(prefix) :])
            return path if path.is_absolute() else root / path
    return None


def _exclude_local_index(root: Path) -> None:
    git_dir = _git_dir(root)
    if not git_dir:
        return
    exclude = git_dir / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    text = exclude.read_text(encoding="utf-8", errors="ignore") if exclude.exists() else ""
    if ".codegraph/" not in text.splitlines():
        exclude.write_text(text + ("" if text.endswith("\n") or not text else "\n") + ".codegraph/\n", encoding="utf-8")


def run_codegraph(root: Path, args: list[str]) -> int:
    """Run the optional external CodeGraph CLI from the current workspace."""
    if not args or args[0] not in ALLOWED_SUBCOMMANDS:
        fail(
            "usage: task system -- codegraph "
            "<init|index|sync|status|explore|query|node|files|callers|callees|impact|affected> [args...]"
        )
    binary = shutil.which("codegraph")
    if not binary:
        fail("codegraph CLI not found; install it with `npx @colbymchenry/codegraph` or `codegraph install`")
    if args[0] in {"init", "index", "sync"}:
        _exclude_local_index(root)
    return run_command([binary, *args], cwd=root, check=False).returncode
