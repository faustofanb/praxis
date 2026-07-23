from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from hashlib import blake2b
from pathlib import Path
from threading import Lock
from typing import Any

from praxis.domain.requirement import Requirement, RequirementStatus


class StateStore:
    _initialization_lock = Lock()

    def __init__(self, root: Path | str):
        self.path = Path(root) / ".praxis" / "workspace.db"

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("pragma busy_timeout = 5000")
        # ponytail: process-local lock; add a cross-process lock if concurrent startup matters.
        with self._initialization_lock:
            if connection.execute("pragma journal_mode").fetchone()[0] != "wal":
                connection.execute("pragma journal_mode = wal")
            self._migrate(connection)
        connection.execute("pragma foreign_keys = on")
        connection.execute("pragma synchronous = normal")
        try:
            yield connection
            if connection.in_transaction:
                connection.commit()
        except BaseException:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _migrate(connection: sqlite3.Connection) -> None:
        migration_root = Path(__file__).with_name("migrations")
        connection.execute(
            "create table if not exists schema_migrations "
            "(version text primary key, applied_at text not null)"
        )
        applied = {row[0] for row in connection.execute("select version from schema_migrations")}
        for path in sorted(migration_root.glob("*.sql")):
            if path.stem in applied:
                continue
            connection.executescript(path.read_text(encoding="utf-8"))
            connection.execute(
                "insert into schema_migrations(version, applied_at) values (?, ?)",
                (path.stem, datetime.now(UTC).isoformat()),
            )

    def set(self, scope: str, key: str, value: dict[str, Any]) -> None:
        with self._connect() as database:
            database.execute(
                """insert into runtime_state(scope, key, value, updated_at)
                values (?, ?, ?, ?)
                on conflict(scope, key) do update set
                value=excluded.value, updated_at=excluded.updated_at""",
                (scope, key, json.dumps(value, sort_keys=True), datetime.now(UTC).isoformat()),
            )

    def set_many(
        self, updates: Sequence[tuple[str, str, dict[str, Any]]]
    ) -> None:
        updated_at = datetime.now(UTC).isoformat()
        with self._connect() as database:
            database.execute("begin immediate")
            database.executemany(
                """insert into runtime_state(scope, key, value, updated_at)
                values (?, ?, ?, ?)
                on conflict(scope, key) do update set
                value=excluded.value, updated_at=excluded.updated_at""",
                [
                    (scope, key, json.dumps(value, sort_keys=True), updated_at)
                    for scope, key, value in updates
                ],
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

    def list_scope(self, scope: str) -> list[dict[str, Any]]:
        with self._connect() as database:
            rows = database.execute(
                "select value from runtime_state where scope=? order by key", (scope,)
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def audit(self, event: str, code: str, details: dict[str, Any]) -> str:
        with self._connect() as database:
            database.execute("begin immediate")
            return self._audit(database, event, code, details)

    def create_requirement(
        self,
        short_name: str,
        original_request: str,
        systems: list[str],
        domains: list[str],
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        timestamp = now or datetime.now(UTC)
        created_at = timestamp.isoformat()
        date = timestamp.strftime("%Y%m%d")
        with self._connect() as database:
            database.execute("begin immediate")
            duplicate = database.execute(
                "select requirement_id from requirements where short_name=? "
                "and status not in ('completed', 'cancelled', 'archived')",
                (short_name,),
            ).fetchone()
            if duplicate:
                raise ValueError(f"存在同名活跃需求：{duplicate['requirement_id']}")
            last = database.execute(
                "select max(requirement_id) from requirements where requirement_id like ?",
                (f"REQ-{date}-%",),
            ).fetchone()[0]
            sequence = int(last.rsplit("-", 1)[1]) + 1 if last else 1
            requirement_id = f"REQ-{date}-{sequence:03d}"
            record = {
                "requirement_id": requirement_id,
                "short_name": short_name,
                "status": RequirementStatus.CAPTURED.value,
                "original_request": original_request,
                "systems": systems,
                "domains": domains,
                "created_at": created_at,
                "updated_at": created_at,
            }
            database.execute(
                """insert into requirements(
                    requirement_id, short_name, status, original_request,
                    systems_json, domains_json, created_at, updated_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    requirement_id,
                    short_name,
                    record["status"],
                    original_request,
                    json.dumps(systems, ensure_ascii=False),
                    json.dumps(domains, ensure_ascii=False),
                    created_at,
                    created_at,
                ),
            )
            self._enqueue(database, "requirement.project", record, created_at)
            self._audit(database, "requirement.created", "OK", record, created_at=created_at)
        return record

    def requirement(self, requirement_id: str) -> dict[str, Any] | None:
        with self._connect() as database:
            row = database.execute(
                "select * from requirements where requirement_id=?", (requirement_id,)
            ).fetchone()
        return self._requirement_record(row) if row else None

    def transition_requirement(
        self,
        requirement_id: str,
        target: RequirementStatus,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        updated_at = (now or datetime.now(UTC)).isoformat()
        with self._connect() as database:
            database.execute("begin immediate")
            row = database.execute(
                "select * from requirements where requirement_id=?", (requirement_id,)
            ).fetchone()
            if not row:
                raise KeyError(requirement_id)
            current = Requirement(
                row["requirement_id"],
                row["short_name"],
                RequirementStatus(row["status"]),
            )
            changed = current.transition(target)
            database.execute(
                "update requirements set status=?, updated_at=? where requirement_id=?",
                (changed.status.value, updated_at, requirement_id),
            )
            record = self._requirement_record(row)
            record.update(status=changed.status.value, updated_at=updated_at)
            self._enqueue(database, "requirement.project", record, updated_at)
            self._audit(
                database,
                "requirement.transitioned",
                "OK",
                {"requirement_id": requirement_id, "status": changed.status.value},
                created_at=updated_at,
            )
        return record

    def reopen_requirement(
        self,
        requirement_id: str,
        reason: str,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        updated_at = (now or datetime.now(UTC)).isoformat()
        with self._connect() as database:
            database.execute("begin immediate")
            row = database.execute(
                "select * from requirements where requirement_id=?", (requirement_id,)
            ).fetchone()
            if not row:
                raise KeyError(requirement_id)
            current = Requirement(
                row["requirement_id"],
                row["short_name"],
                RequirementStatus(row["status"]),
            )
            changed = current.reopen()
            database.execute(
                "update requirements set status=?, updated_at=? where requirement_id=?",
                (changed.status.value, updated_at, requirement_id),
            )
            record = self._requirement_record(row)
            record.update(status=changed.status.value, updated_at=updated_at)
            self._enqueue(database, "requirement.project", record, updated_at)
            self._audit(
                database,
                "requirement.reopened",
                "OK",
                {
                    "requirement_id": requirement_id,
                    "from": RequirementStatus.VERIFYING.value,
                    "status": changed.status.value,
                    "reason": reason,
                },
                created_at=updated_at,
            )
        return record

    def merge_domain(self, source: str, target: str) -> int:
        updated = 0
        timestamp = datetime.now(UTC).isoformat()
        with self._connect() as database:
            database.execute("begin immediate")
            rows = database.execute("select * from requirements").fetchall()
            for row in rows:
                domains = json.loads(row["domains_json"])
                if source not in domains:
                    continue
                domains = list(
                    dict.fromkeys(target if item == source else item for item in domains)
                )
                database.execute(
                    "update requirements set domains_json=?, updated_at=? where requirement_id=?",
                    (json.dumps(domains, ensure_ascii=False), timestamp, row["requirement_id"]),
                )
                record = self._requirement_record(
                    database.execute(
                        "select * from requirements where requirement_id=?",
                        (row["requirement_id"],),
                    ).fetchone()
                )
                self._enqueue(database, "requirement.project", record, timestamp)
                updated += 1
            self._audit(
                database,
                "domain.merged",
                "OK",
                {"source": source, "target": target, "requirements": updated},
                created_at=timestamp,
            )
        return updated

    def rename_requirement(self, requirement_id: str, short_name: str) -> dict[str, Any]:
        timestamp = datetime.now(UTC).isoformat()
        with self._connect() as database:
            database.execute("begin immediate")
            row = database.execute(
                "select * from requirements where requirement_id=?", (requirement_id,)
            ).fetchone()
            if not row:
                raise KeyError(requirement_id)
            database.execute(
                "update requirements set short_name=?, updated_at=? where requirement_id=?",
                (short_name, timestamp, requirement_id),
            )
            updated = database.execute(
                "select * from requirements where requirement_id=?", (requirement_id,)
            ).fetchone()
            assert updated is not None
            record = self._requirement_record(updated)
            self._enqueue(database, "requirement.project", record, timestamp)
            self._audit(
                database,
                "requirement.renamed",
                "OK",
                {"requirement_id": requirement_id, "short_name": short_name},
                created_at=timestamp,
            )
        return record

    def pending_outbox(self) -> list[dict[str, Any]]:
        with self._connect() as database:
            rows = database.execute(
                "select id, topic, payload from outbox where processed_at is null order by id"
            ).fetchall()
        return [
            {"id": row["id"], "topic": row["topic"], "payload": json.loads(row["payload"])}
            for row in rows
        ]

    def mark_outbox_processed(self, outbox_id: int) -> None:
        with self._connect() as database:
            database.execute(
                "update outbox set processed_at=? where id=?",
                (datetime.now(UTC).isoformat(), outbox_id),
            )

    def verify_audit_chain(self) -> bool:
        previous_hash: str | None = None
        with self._connect() as database:
            rows = database.execute(
                "select * from audit_events order by sequence_number"
            ).fetchall()
        for row in rows:
            expected = self._event_hash(
                previous_hash,
                row["event"],
                row["code"],
                row["details"],
                row["created_at"],
            )
            if row["previous_hash"] != previous_hash or row["event_hash"] != expected:
                return False
            previous_hash = row["event_hash"]
        return True

    def audit_events(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as database:
            rows = database.execute(
                "select * from audit_events order by sequence_number desc limit ?", (limit,)
            ).fetchall()
        return [self._audit_record(row) for row in rows]

    def audit_event(self, audit_id: str) -> dict[str, Any] | None:
        with self._connect() as database:
            row = database.execute(
                "select * from audit_events where audit_id=?", (audit_id,)
            ).fetchone()
        return self._audit_record(row) if row else None

    @staticmethod
    def _audit_record(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "sequence_number": row["sequence_number"],
            "audit_id": row["audit_id"],
            "event": row["event"],
            "code": row["code"],
            "details": json.loads(row["details"]),
            "previous_hash": row["previous_hash"],
            "event_hash": row["event_hash"],
            "created_at": row["created_at"],
        }

    @staticmethod
    def _requirement_record(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "requirement_id": row["requirement_id"],
            "short_name": row["short_name"],
            "status": row["status"],
            "original_request": row["original_request"],
            "systems": json.loads(row["systems_json"]),
            "domains": json.loads(row["domains_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def _enqueue(
        database: sqlite3.Connection,
        topic: str,
        payload: dict[str, Any],
        created_at: str,
    ) -> None:
        database.execute(
            "insert into outbox(topic, payload, created_at) values (?, ?, ?)",
            (topic, json.dumps(payload, ensure_ascii=False, sort_keys=True), created_at),
        )

    def _audit(
        self,
        database: sqlite3.Connection,
        event: str,
        code: str,
        details: dict[str, Any],
        *,
        created_at: str | None = None,
    ) -> str:
        timestamp = created_at or datetime.now(UTC).isoformat()
        payload = json.dumps(details, ensure_ascii=False, sort_keys=True)
        row = database.execute(
            "select event_hash from audit_events order by sequence_number desc limit 1"
        ).fetchone()
        previous_hash = row[0] if row else None
        event_hash = self._event_hash(previous_hash, event, code, payload, timestamp)
        audit_id = (
            f"AUD-{timestamp.replace('-', '').replace(':', '')[:15]}-{event_hash[:8].upper()}"
        )
        database.execute(
            """insert into audit_events(
                audit_id, event, code, details, previous_hash, event_hash, created_at
            ) values (?, ?, ?, ?, ?, ?, ?)""",
            (audit_id, event, code, payload, previous_hash, event_hash, timestamp),
        )
        return audit_id

    @staticmethod
    def _event_hash(
        previous_hash: str | None,
        event: str,
        code: str,
        details: str,
        created_at: str,
    ) -> str:
        content = "\0".join((previous_hash or "", event, code, details, created_at))
        return blake2b(content.encode(), digest_size=20).hexdigest()
