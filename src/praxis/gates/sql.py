from __future__ import annotations

import re

from praxis.result import Result

_ROOT_OPERATIONS = {"SELECT", "INSERT", "UPDATE", "DELETE"}
_DDL = {"ALTER", "CREATE", "DROP", "RENAME", "TRUNCATE"}


def inspect_sql(sql: str) -> Result:
    """Classify one SQL statement, rejecting anything that is not clearly safe."""
    statements, error = _statements(sql)
    if error:
        return Result(False, error, data={"kind": "blocked"})
    if len(statements) != 1:
        code = "SQL_EMPTY" if not statements else "SQL_MULTIPLE_STATEMENTS"
        return Result(False, code, data={"kind": "blocked"})

    tokens = re.findall(r"[A-Za-z_][A-Za-z_0-9]*|[()]", statements[0].upper())
    operation = _root_operation(tokens)
    if operation in _DDL:
        return Result(False, "SQL_DDL_BLOCKED", data={"kind": "blocked"})
    if operation == "SELECT":
        if _contains_sequence(tokens, "FOR", "UPDATE"):
            return Result(False, "SQL_LOCKING_READ_BLOCKED", data={"kind": "blocked"})
        if "INTO" in tokens:
            return Result(False, "SQL_SELECT_INTO_BLOCKED", data={"kind": "blocked"})
        return Result(True, data={"kind": "read", "operation": operation.lower()})
    if operation in {"INSERT", "UPDATE", "DELETE"}:
        if operation in {"UPDATE", "DELETE"} and not _has_top_level_where(tokens):
            return Result(False, "SQL_WHERE_REQUIRED", data={"kind": "blocked"})
        return Result(True, data={"kind": "write", "operation": operation.lower()})
    return Result(False, "SQL_UNSUPPORTED", data={"kind": "blocked"})


def _root_operation(tokens: list[str]) -> str | None:
    if not tokens:
        return None
    if tokens[0] != "WITH":
        return tokens[0]
    depth = 0
    for token in tokens[1:]:
        if token == "(":
            depth += 1
        elif token == ")":
            depth -= 1
        elif depth == 0 and token in _ROOT_OPERATIONS | _DDL:
            return token
    return None


def _has_top_level_where(tokens: list[str]) -> bool:
    depth = 0
    for token in tokens:
        if token == "(":
            depth += 1
        elif token == ")":
            depth -= 1
        elif depth == 0 and token == "WHERE":
            return True
    return False


def _contains_sequence(tokens: list[str], first: str, second: str) -> bool:
    return any(pair == (first, second) for pair in zip(tokens, tokens[1:], strict=False))


def _statements(sql: str) -> tuple[list[str], str | None]:
    statements: list[str] = []
    current: list[str] = []
    index = 0
    quote: str | None = None
    while index < len(sql):
        character = sql[index]
        following = sql[index + 1] if index + 1 < len(sql) else ""
        if quote:
            if character == quote and following == quote:
                index += 2
                continue
            if character == quote:
                quote = None
            current.append(" ")
            index += 1
            continue
        if character in {"'", '"'}:
            quote = character
            current.append(" ")
            index += 1
            continue
        if character == "-" and following == "-":
            index = sql.find("\n", index + 2)
            if index == -1:
                index = len(sql)
            current.append(" ")
            continue
        if character == "/" and following == "*":
            end = sql.find("*/", index + 2)
            if end == -1:
                return [], "SQL_INVALID"
            current.append(" ")
            index = end + 2
            continue
        if character == ";":
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
        else:
            current.append(character)
        index += 1
    if quote:
        return [], "SQL_INVALID"
    statement = "".join(current).strip()
    if statement:
        statements.append(statement)
    return statements, None
