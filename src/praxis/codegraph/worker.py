from __future__ import annotations

import argparse
from pathlib import Path

from praxis.codegraph.service import CodeGraphService


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--worktree", type=Path, required=True)
    parser.add_argument("--binding", default="")
    arguments = parser.parse_args()
    result = CodeGraphService(
        arguments.root,
        arguments.project,
        repo=arguments.worktree,
    ).run_pending(binding_id=arguments.binding)
    return 0 if result.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
