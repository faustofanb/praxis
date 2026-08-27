import type { Database } from "bun:sqlite";

/**
 * Explicit, monotonic SQL migrations (docs/01: no ORM, visible SQL).
 * Versions must apply strictly in order; a database that has an unknown
 * version applied (downgrade or divergence) fails closed.
 */

type Migration = {
  version: number;
  sql: string;
};

const MIGRATIONS: readonly Migration[] = [
  {
    version: 1,
    sql: `
      CREATE TABLE sessions (
        id TEXT PRIMARY KEY,
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL,
        head_seq INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL
      );

      CREATE TABLE events (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        seq INTEGER NOT NULL,
        type TEXT NOT NULL,
        schema_version INTEGER NOT NULL,
        occurred_at INTEGER NOT NULL,
        actor_json TEXT NOT NULL,
        causation_id TEXT,
        correlation_id TEXT,
        payload_json TEXT NOT NULL,
        FOREIGN KEY(session_id) REFERENCES sessions(id),
        UNIQUE(session_id, seq)
      );

      CREATE INDEX events_session_seq
        ON events(session_id, seq);
    `,
  },
];

export function migrate(db: Database): void {
  db.exec(`
    CREATE TABLE IF NOT EXISTS schema_migrations (
      version INTEGER PRIMARY KEY,
      applied_at INTEGER NOT NULL
    );
  `);
  const rows = db
    .query("SELECT version FROM schema_migrations ORDER BY version ASC")
    .all() as unknown as Array<{ version: number }>;
  const applied = rows.map((row) => row.version);

  for (let index = 0; index < applied.length; index += 1) {
    const expected = MIGRATIONS[index]?.version;
    if (applied[index] !== expected) {
      throw new Error(
        `schema_migrations diverged: applied version ${applied[index]} where ${expected ?? "nothing"} was expected`,
      );
    }
  }

  for (const migration of MIGRATIONS.slice(applied.length)) {
    db.transaction(() => {
      db.exec(migration.sql);
      db.query("INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)").run(
        migration.version,
        Date.now(),
      );
    })();
  }
}
