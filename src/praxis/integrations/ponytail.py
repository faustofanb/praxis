from __future__ import annotations

from praxis.result import Result


def diff_warning(added_lines: int, deleted_lines: int, threshold: int = 500) -> Result:
    growth = added_lines - deleted_lines
    if growth <= threshold:
        return Result(True, data={"growth": growth})
    return Result(
        True,
        "PONYTAIL_DIFF_GROWTH",
        data={"growth": growth, "threshold": threshold},
        diagnostics=(
            {
                "code": "PONYTAIL_DIFF_GROWTH",
                "message": "Diff growth exceeds the non-blocking simplification threshold.",
            },
        ),
    )
