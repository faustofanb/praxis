from __future__ import annotations

from pathlib import Path

from praxis.fastlane.diagnostics import (
    baseline_fingerprint,
    compare_diagnostics,
    normalize_diagnostics,
)


def test_normalize_diagnostics_ignores_line_and_worktree_path_changes(
    tmp_path: Path,
) -> None:
    baseline_root = tmp_path / "baseline"
    current_root = tmp_path / "current"
    baseline = (
        f"{baseline_root}/src/view.ts(10,4): error TS2322: "
        "Type 'number' is not assignable to type 'string'.\n"
    )
    current = (
        f"{current_root}/src/view.ts(28,9): error TS2322: "
        "Type 'number' is not assignable to type 'string'.\n"
    )

    assert normalize_diagnostics(baseline, baseline_root) == normalize_diagnostics(
        current, current_root
    )
    assert compare_diagnostics(
        baseline,
        current,
        current_root,
        baseline_root=baseline_root,
    )["status"] == "incremental_passed_baseline_failed"


def test_compare_diagnostics_reports_only_positive_multiset_delta(tmp_path: Path) -> None:
    baseline = "\n".join(
        (
            "src/a.ts(1,1): error TS1001: existing",
            "src/a.ts(2,1): error TS1001: existing",
        )
    )
    current = "\n".join(
        (
            "src/a.ts(8,2): error TS1001: existing",
            "src/a.ts(9,3): error TS1001: existing",
            "src/b.ts(3,4): error TS2002: introduced",
        )
    )

    compared = compare_diagnostics(baseline, current, tmp_path)

    assert compared["status"] == "failed_new_diagnostics"
    assert compared["new_diagnostics"] == [
        {
            "path": "src/b.ts",
            "code": "TS2002",
            "message": "introduced",
            "count": 1,
        }
    ]


def test_compare_diagnostics_accepts_existing_failing_baseline(tmp_path: Path) -> None:
    baseline = "src/a.py:4:3: error: Existing issue [assignment]\n"
    current = "src/a.py:40:8: error: Existing issue [assignment]\n"

    compared = compare_diagnostics(baseline, current, tmp_path)

    assert compared["status"] == "incremental_passed_baseline_failed"
    assert compared["new_diagnostics"] == []


def test_compare_diagnostics_accepts_zero_error_baseline(tmp_path: Path) -> None:
    compared = compare_diagnostics("", "", tmp_path)

    assert compared["status"] == "passed"
    assert compared["new_diagnostics"] == []


def test_normalize_diagnostics_supports_ty_location_lines(tmp_path: Path) -> None:
    output = (
        "error: Object of type `None` is not callable [not-callable]\n"
        "  --> src/example.py:12:5\n"
    )

    assert normalize_diagnostics(output, tmp_path) == {
        ("src/example.py", "not-callable", "Object of type `None` is not callable"): 1
    }


def test_baseline_fingerprint_changes_with_lockfile_or_toolchain(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        '{"packageManager":"pnpm@9.15.0"}\n', encoding="utf-8"
    )
    lockfile = tmp_path / "pnpm-lock.yaml"
    lockfile.write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    first = baseline_fingerprint(
        "mes-pad",
        "abc123",
        ("pnpm", "run", "type-check"),
        tmp_path,
    )

    lockfile.write_text("lockfileVersion: '9.1'\n", encoding="utf-8")
    second = baseline_fingerprint(
        "mes-pad",
        "abc123",
        ("pnpm", "run", "type-check"),
        tmp_path,
    )

    assert first != second

    (tmp_path / "package.json").write_text(
        '{"packageManager":"pnpm@10.0.0"}\n', encoding="utf-8"
    )
    third = baseline_fingerprint(
        "mes-pad",
        "abc123",
        ("pnpm", "run", "type-check"),
        tmp_path,
    )

    assert second != third
