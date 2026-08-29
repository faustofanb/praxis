import { EVENT_SCHEMA_VERSION, EventEnvelopeBaseSchema } from "./envelope";
import type { SessionEventUnion } from "./events/session-events";
import { SessionEventUnionSchema } from "./events/session-events";

/**
 * Versioned replay seam (docs/02 section 6.1, M5-T003). Persisted streams
 * outlive code: loading them is a boundary parse, not a cast.
 *
 * Laws:
 * - Version window: `1 <= schemaVersion <= EVENT_SCHEMA_VERSION`. A stream
 *   written by a newer runtime fails closed at load — it never reaches the
 *   reducer, so a future-shaped event can never fold silently under
 *   current rules.
 * - Stepwise migrations: every schema bump appends exactly one migration
 *   step; steps must be contiguous ascending (step i migrates FROM version
 *   i+1) and the pipeline stamps the migrated version itself.
 * - Old fixtures replay: after any migration, every historical fixture must
 *   fold to the identical derived state (docs/02 section 4.3).
 */

export type SessionEventMigration = {
  /** Version this step migrates FROM; step i must declare `fromVersion: i + 1`. */
  readonly fromVersion: number;
  readonly transform: (event: Record<string, unknown>) => Record<string, unknown>;
};

export class InvalidMigrationTableError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "InvalidMigrationTableError";
  }
}

export class InvalidReplayEventError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "InvalidReplayEventError";
  }
}

export class FutureSchemaVersionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "FutureSchemaVersionError";
  }
}

/**
 * Empty while v1 is current. The first real schema bump appends exactly one
 * step here (plus the EVENT_SCHEMA_VERSION increment in `./envelope`); old
 * fixtures must keep folding identically through the drill pinned in
 * tests/contracts-replay.test.ts.
 */
export const SESSION_EVENT_MIGRATIONS: readonly SessionEventMigration[] = [];

/**
 * The version a migration table migrates TO, after enforcing the contiguous
 * ascending law. `migratedSchemaVersion([])` is 1 — the identity table.
 */
export function migratedSchemaVersion(migrations: readonly SessionEventMigration[]): number {
  migrations.forEach((step, index) => {
    if (step.fromVersion !== index + 1) {
      throw new InvalidMigrationTableError(
        `migration steps must be contiguous ascending: step ${index + 1} declares fromVersion ${String(step.fromVersion)}, expected ${String(index + 1)}`,
      );
    }
  });
  return 1 + migrations.length;
}

/**
 * Apply a migration table to one envelope-validated event, from its declared
 * schemaVersion up to the table's target. The pipeline — never the transform
 * — stamps the resulting schemaVersion, so a step cannot lie about version.
 */
export function applyEventMigrations(
  event: Record<string, unknown>,
  migrations: readonly SessionEventMigration[],
): Record<string, unknown> {
  const target = migratedSchemaVersion(migrations);
  const declared = event.schemaVersion;
  if (typeof declared !== "number" || !Number.isInteger(declared) || declared < 1) {
    throw new InvalidReplayEventError(
      "event schemaVersion must be a positive integer before migration",
    );
  }
  if (declared > target) {
    throw new FutureSchemaVersionError(
      `event schemaVersion ${String(declared)} is newer than the migration target ${String(target)}; refusing to fold a future stream`,
    );
  }
  let migrated = event;
  for (let version = declared; version < target; version += 1) {
    const step = migrations[version - 1];
    migrated = step === undefined ? migrated : step.transform(migrated);
  }
  return { ...migrated, schemaVersion: target };
}

/**
 * Load one persisted event: envelope-first (identity + version window),
 * stepwise migration to the current version, then full union validation.
 */
export function parseReplayEvent(raw: unknown): SessionEventUnion {
  if (typeof raw !== "object" || raw === null) {
    throw new InvalidReplayEventError("a replay event must be a JSON object");
  }
  const record = raw as Record<string, unknown>;
  const envelope = EventEnvelopeBaseSchema.parse(record);
  if (envelope.schemaVersion > EVENT_SCHEMA_VERSION) {
    throw new FutureSchemaVersionError(
      `event schemaVersion ${String(envelope.schemaVersion)} exceeds the current EVENT_SCHEMA_VERSION ${String(EVENT_SCHEMA_VERSION)}; a stream written by a newer runtime fails closed at load`,
    );
  }
  const migrated = applyEventMigrations(record, SESSION_EVENT_MIGRATIONS);
  return SessionEventUnionSchema.parse(migrated);
}

/** Load a persisted session stream through the versioned seam. */
export function parseReplayStream(raw: unknown): SessionEventUnion[] {
  if (!Array.isArray(raw)) {
    throw new InvalidReplayEventError("a replay stream must be a JSON array of events");
  }
  return raw.map((event) => parseReplayEvent(event));
}
