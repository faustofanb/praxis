#!/usr/bin/env python3
"""Run every package and profile verification required before delivery."""

from __future__ import annotations

import argparse
import shlex
import subprocess
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def verification_commands() -> list[list[str]]:
    commands = [
        ["uv", "run", "python", "scripts/praxis_build_adapters.py", "--check"],
        ["uv", "run", "python", "scripts/praxis_vendor_ponytail.py", "--check"],
        ["uv", "run", "--with", "pytest", "pytest", "-q", "tests"],
    ]
    adapters_root = PLUGIN_ROOT / "adapters" / "omp"
    if adapters_root.is_dir():
        for adapter in sorted(adapters_root.glob("*.mjs")):
            commands.append(["node", "--check", adapter.relative_to(PLUGIN_ROOT).as_posix()])
    profiles_root = PLUGIN_ROOT / "profiles"
    if profiles_root.is_dir():
        for profile_root in sorted(path for path in profiles_root.iterdir() if path.is_dir()):
            tests_root = profile_root / "scripts" / "praxis" / "tests"
            if (profile_root / "profile.toml").is_file() and tests_root.is_dir():
                commands.append(
                    [
                        "uv",
                        "run",
                        "--with",
                        "pytest",
                        "pytest",
                        "-q",
                        tests_root.relative_to(PLUGIN_ROOT).as_posix(),
                    ]
                )
    return commands


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="Print commands without running them")
    args = parser.parse_args(argv)

    commands = verification_commands()
    if args.list:
        for command in commands:
            print(shlex.join(command))
        return 0

    for command in commands:
        print(f"==> {shlex.join(command)}", flush=True)
        completed = subprocess.run(command, cwd=PLUGIN_ROOT)
        if completed.returncode != 0:
            return completed.returncode
    print("package verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
