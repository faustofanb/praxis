from __future__ import annotations

from pathlib import Path

from praxis.naming.commit import parse_commit_message
from praxis.result import Result

DEFAULT_SCOPES = frozenset(
    {
        "report",
        "production",
        "quality",
        "inventory",
        "database",
        "api",
        "admin",
        "mobile",
        "praxis",
        "workflow",
    }
)


def validate_commit_message(
    *,
    message: str | None = None,
    message_file: Path | None = None,
    allowed_scopes: frozenset[str] = DEFAULT_SCOPES,
) -> Result:
    if (message is None) == (message_file is None):
        raise ValueError("message 和 message_file 必须且只能提供一个")
    if message is not None:
        content = message
    else:
        assert message_file is not None
        content = message_file.read_text(encoding="utf-8")
    try:
        parsed = parse_commit_message(content, allowed_scopes)
    except ValueError as error:
        return Result(False, "COMMIT_MESSAGE_INVALID", data={"message": str(error)})
    return Result(
        True,
        data={
            "requirement_id": parsed.requirement_id,
            "stage": parsed.trailers["Praxis-Stage"],
            "scope": parsed.scope,
        },
    )
