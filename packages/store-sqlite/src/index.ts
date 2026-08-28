import type { EventStore } from "@praxis/contracts";
import { packageName as contractsPackageName } from "@praxis/contracts";
import { openDatabase } from "./db";
import { migrate } from "./migrations";
import { type SessionSummary, SqliteEventStore } from "./session-store";

/**
 * Public API of @praxis/store-sqlite. Deep imports are forbidden
 * (.praxis/architecture.yaml); openSessionStore is the only construction
 * path and always migrates to the current schema version first.
 */

export type SessionStore = EventStore & {
  close(): void;
  /** Metadata listing (facts stay authoritative in the event stream). */
  listSessions(): readonly SessionSummary[];
};

export type { SessionSummary };

export function openSessionStore(path: string): SessionStore {
  const db = openDatabase(path);
  migrate(db);
  return new SqliteEventStore(db);
}

export const packageName = "@praxis/store-sqlite";
export const workspaceDependencies = [contractsPackageName] as const;
