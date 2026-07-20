from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from praxis import __version__


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="praxis")
    commands = parser.add_subparsers(dest="command", required=True)
    version = commands.add_parser("version")
    version.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.json:
        print(json.dumps({"ok": True, "data": {"version": __version__}}))
    else:
        print(__version__)
    return 0

