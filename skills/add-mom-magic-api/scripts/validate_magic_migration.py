#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

_DELIMITER = "================================"
_TENANT_NAMES = {"tenant", "tenantid", "tenant_id"}


def _add(diagnostics: list[str], code: str) -> None:
    if code not in diagnostics:
        diagnostics.append(code)


def _magic_blocks(text: str) -> list[str]:
    return re.findall(r"\$magic\$(.*?)\$magic\$", text, flags=re.DOTALL)


def _metadata_and_script(
    block: str,
    diagnostics: list[str],
) -> tuple[dict, str] | None:
    marker = f"\n{_DELIMITER}\n"
    if marker not in block:
        _add(diagnostics, "MAGIC_DELIMITER_MISSING")
        return None
    metadata_text, script = block.split(marker, 1)
    try:
        metadata = json.loads(metadata_text.strip())
    except json.JSONDecodeError:
        _add(diagnostics, "MAGIC_JSON_INVALID")
        return None
    return metadata, script


def _tenant_parameter_exposed(metadata: dict) -> bool:
    names = {
        str(item.get("name", "")).casefold()
        for item in metadata.get("parameters", [])
        if isinstance(item, dict)
    }
    request_body = metadata.get("requestBody")
    if isinstance(request_body, str) and request_body.strip():
        try:
            body = json.loads(request_body)
        except json.JSONDecodeError:
            body = {}
        if isinstance(body, dict):
            names.update(str(name).casefold() for name in body)
    return bool(names & _TENANT_NAMES)


def _snowflake_id_not_string(script: str) -> bool:
    for line in script.splitlines():
        if not re.search(r"\b(?:\w+\.)?id\s+AS\s+\w*id\b", line, flags=re.IGNORECASE):
            continue
        expression = line.split(" AS ", 1)[0].casefold()
        if "::varchar" not in expression and "cast(" not in expression:
            return True
    return False


def _unbound_placeholder(script: str) -> bool:
    placeholders = set(re.findall(r"#\{([A-Za-z_]\w*)\}", script))
    return any(
        not re.search(rf"\b{re.escape(name)}\s*:", script)
        for name in placeholders
    )


def validate_text(
    text: str,
    *,
    expected_group_id: str = "",
    expected_group_path: str = "",
    expected_menu_route: str = "",
) -> list[str]:
    diagnostics: list[str] = []
    blocks = _magic_blocks(text)
    if not blocks:
        _add(diagnostics, "MAGIC_BLOCK_MISSING")
        return diagnostics

    for block in blocks:
        parsed = _metadata_and_script(block, diagnostics)
        if parsed is None:
            continue
        metadata, script = parsed
        group_id = str(metadata.get("groupId", ""))
        method = str(metadata.get("method", "")).upper()
        api_path = str(metadata.get("path", ""))

        if expected_group_id and group_id != expected_group_id:
            _add(diagnostics, "MAGIC_GROUP_MISMATCH")
        if _tenant_parameter_exposed(metadata):
            _add(diagnostics, "MAGIC_TENANT_PARAMETER_EXPOSED")
        if "ifc.getTenantId()" not in script:
            _add(diagnostics, "MAGIC_TENANT_CONTEXT_MISSING")
        if _snowflake_id_not_string(script):
            _add(diagnostics, "SNOWFLAKE_ID_NOT_STRING")
        if _unbound_placeholder(script):
            _add(diagnostics, "SQL_PLACEHOLDER_UNBOUND")

        group_path = "/" + expected_group_path.strip("/") if expected_group_path else ""
        full_uri = "/magic/api" + group_path + "/" + api_path.lstrip("/")
        permission_contract = all(
            value in text
            for value in (
                "'MagicController'",
                "'lamp-system-server'",
                f"'{method}'",
                f"'{full_uri}'",
            )
        )
        if not permission_contract:
            _add(diagnostics, "PERMISSION_URI_MISMATCH")

    if expected_menu_route and f"'{expected_menu_route}'" not in text:
        _add(diagnostics, "MENU_ROUTE_MISMATCH")
    if not re.search(
        r"INSERT\s+INTO\s+def_tenant_resource_rel",
        text,
        flags=re.IGNORECASE,
    ) or not re.search(r"\bNOT\s+EXISTS\b", text, flags=re.IGNORECASE):
        _add(diagnostics, "TENANT_GRANT_MISSING")
    if not re.search(
        r"DELETE\s+FROM\s+magic_api_file\s+WHERE\s+file_path",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        _add(diagnostics, "MAGIC_FILE_NOT_IDEMPOTENT")
    if not re.search(
        r"(DELETE\s+FROM\s+def_resource_api|INSERT\s+INTO\s+def_resource_api.*NOT\s+EXISTS)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        _add(diagnostics, "PERMISSION_NOT_IDEMPOTENT")
    if not re.search(
        r"(DELETE\s+FROM\s+def_resource\s+WHERE\s+code|INSERT\s+INTO\s+def_resource.*NOT\s+EXISTS)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        _add(diagnostics, "MENU_NOT_IDEMPOTENT")
    return diagnostics


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a MOM Magic-API Flyway migration contract."
    )
    parser.add_argument("migration", type=Path)
    parser.add_argument("--expected-group-id", default="")
    parser.add_argument("--expected-group-path", default="")
    parser.add_argument("--expected-menu-route", default="")
    args = parser.parse_args()
    diagnostics = validate_text(
        args.migration.read_text(encoding="utf-8"),
        expected_group_id=args.expected_group_id,
        expected_group_path=args.expected_group_path,
        expected_menu_route=args.expected_menu_route,
    )
    if diagnostics:
        for code in diagnostics:
            print(code)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
