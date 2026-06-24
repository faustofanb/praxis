#!/usr/bin/env python3
"""Human-facing Praxis workspace doctor."""

from __future__ import annotations

import argparse

from praxis_check_workspace import analyze_workspace, report_to_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", nargs="?", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = analyze_workspace(args.workspace)
    if args.json:
        print(report_to_json(report))
    else:
        print("Praxis doctor")
        print("-------------")
        print(f"Workspace: {report.workspace}")
        print(f"Result: {'PASS' if report.ok else 'FAIL'}")
        if report.missing_files:
            print("Missing required files:")
            for item in report.missing_files:
                print(f"- {item}")
        if report.errors:
            print("Errors:")
            for item in report.errors:
                print(f"- {item}")
        if report.warnings:
            print("Warnings:")
            for item in report.warnings:
                print(f"- {item}")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
