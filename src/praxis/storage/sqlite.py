from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class StateStore:
    def __init__(self, root: Path | str):
        self.path = Path(root) / ".praxis" / "state.db"

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        try:
            connection.executescript(
                """
                create table if not exists runtime_state (
                    scope text not null,
                    key text not null,
                    value text not null,
                    updated_at text not null,
                    primary key (scope, key)
                );
                create table if not exists audit_log (
                    id integer primary key,
                    event text not null,
                    code text not null,
                    details text not null,
                    created_at text not null
                );
                """
            )
            yield connection
            connection.commit()
        finally:
            connection.close()

    def set(self, scope: str, key: str, value: dict[str, Any]) -> None:
        with self._connect() as database:
            database.execute(
                """insert into runtime_state(scope, key, value, updated_at)
                values (?, ?, ?, ?)
                on conflict(scope, key) do update set
                value=excluded.value, updated_at=excluded.updated_at""",
                (scope, key, json.dumps(value, sort_keys=True), datetime.now(UTC).isoformat()),
            )

    def get(self, scope: str, key: str) -> dict[str, Any] | None:
        with self._connect() as database:
            row = database.execute(
                "select value from runtime_state where scope=? and key=?", (scope, key)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def delete(self, scope: str, key: str) -> None:
        with self._connect() as database:
            database.execute("delete from runtime_state where scope=? and key=?", (scope, key))

    def audit(self, event: str, code: str, details: dict[str, Any]) -> None:
        with self._connect() as database:
            database.execute(
                "insert into audit_log(event, code, details, created_at) values (?, ?, ?, ?)",
                (event, code, json.dumps(details, sort_keys=True), datetime.now(UTC).isoformat()),
            )
