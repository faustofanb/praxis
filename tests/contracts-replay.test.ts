import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  applyEventMigrations,
  EVENT_SCHEMA_VERSION,
  FutureSchemaVersionError,
  InvalidMigrationTableError,
  InvalidReplayEventError,
  migratedSchemaVersion,
  parseReplayEvent,
  parseReplayStream,
  SESSION_EVENT_MIGRATIONS,
  type SessionEventMigration,
  SessionEventUnionSchema,
} from "@praxis/contracts";
import { foldSessionEvents } from "@praxis/core";
import { describe, expect, test } from "vitest";

/**
 * Versioned replay seam (docs/02 section 6.1, M5-T003): the version window
 * fails closed, the migration table law is enforced, and the drill proves
 * that a migrated stream folds to the identical derived state.
 */

const loopFixturePath = fileURLToPath(
  new URL("./fixtures/replay/agent-loop-recovery-v1.json", import.meta.url),
);

function minimalEvent(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: "event-1",
    sessionId: "session-seam",
    seq: 1,
    schemaVersion: 1,
    occurredAt: 1,
    actor: { kind: "system" },
    type: "SessionCreated",
    payload: {},
    ...overrides,
  };
}

describe("versioned replay window", () => {
  test("loads a current-version event through envelope-first validation", () => {
    const parsed = parseReplayEvent(minimalEvent());
    expect(parsed.type).toBe("SessionCreated");
    expect(parsed.schemaVersion).toBe(EVENT_SCHEMA_VERSION);
  });

  test("rejects a future-version event at load, before any fold", () => {
    expect(() =>
      parseReplayEvent(minimalEvent({ schemaVersion: EVENT_SCHEMA_VERSION + 1 })),
    ).toThrow(FutureSchemaVersionError);
  });

  test("rejects a non-positive or non-integer schemaVersion", () => {
    expect(() => parseReplayEvent(minimalEvent({ schemaVersion: 0 }))).toThrow();
    expect(() => parseReplayEvent(minimalEvent({ schemaVersion: 1.5 }))).toThrow();
    const { schemaVersion: _omitted, ...withoutVersion } = minimalEvent();
    expect(() => parseReplayEvent(withoutVersion)).toThrow();
  });

  test("rejects non-object events and non-array streams", () => {
    expect(() => parseReplayEvent("not an event")).toThrow(InvalidReplayEventError);
    expect(() => parseReplayStream({ not: "an array" })).toThrow(InvalidReplayEventError);
  });

  test("the live migration table is the identity while v1 is current", () => {
    expect(SESSION_EVENT_MIGRATIONS).toHaveLength(0);
    expect(migratedSchemaVersion(SESSION_EVENT_MIGRATIONS)).toBe(EVENT_SCHEMA_VERSION);
  });
});

describe("migration table law", () => {
  test("rejects a non-contiguous table", () => {
    const gap: readonly SessionEventMigration[] = [
      { fromVersion: 1, transform: (event) => event },
      { fromVersion: 3, transform: (event) => event },
    ];
    expect(() => migratedSchemaVersion(gap)).toThrow(InvalidMigrationTableError);
  });

  test("the pipeline stamps the migrated version; transforms cannot", () => {
    const table: readonly SessionEventMigration[] = [
      { fromVersion: 1, transform: (event) => ({ ...event, correlationId: "migrated-v2" }) },
    ];
    const migrated = applyEventMigrations(minimalEvent(), table);
    expect(migrated.schemaVersion).toBe(2);
    expect(migrated.correlationId).toBe("migrated-v2");
  });

  test("applyEventMigrations rejects a declared version above the table target", () => {
    const table: readonly SessionEventMigration[] = [
      { fromVersion: 1, transform: (event) => event },
    ];
    expect(() => applyEventMigrations(minimalEvent({ schemaVersion: 3 }), table)).toThrow(
      FutureSchemaVersionError,
    );
    expect(() => applyEventMigrations(minimalEvent({ schemaVersion: "1" }), table)).toThrow(
      InvalidReplayEventError,
    );
  });
});

describe("migration drill: a migrated fixture stream folds to the identical state", () => {
  test("a synthetic v1->v2 step applied to a real fixture preserves fold identity", () => {
    const raw: unknown = JSON.parse(readFileSync(loopFixturePath, "utf8"));
    const current = parseReplayStream(raw);
    const table: readonly SessionEventMigration[] = [
      { fromVersion: 1, transform: (event) => ({ ...event, correlationId: "migrated-v2" }) },
    ];
    const migrated = (raw as readonly Record<string, unknown>[]).map((event) =>
      applyEventMigrations(event, table),
    );

    for (const event of migrated) {
      expect(event.schemaVersion).toBe(2);
      expect(event.correlationId).toBe("migrated-v2");
    }
    // The migrated events are still shape-valid current events (the
    // synthetic step only touches an optional envelope field).
    const reparsed = migrated.map((event) => SessionEventUnionSchema.parse(event));
    expect(foldSessionEvents(reparsed)).toEqual(foldSessionEvents(current));
  });

  test("a future-version fixture stream is rejected by the loader and never folded", () => {
    const raw: unknown = JSON.parse(readFileSync(loopFixturePath, "utf8"));
    const future = (raw as readonly Record<string, unknown>[]).map((event) => ({
      ...event,
      schemaVersion: EVENT_SCHEMA_VERSION + 1,
    }));
    expect(() => parseReplayStream(future)).toThrow(FutureSchemaVersionError);
  });
});
