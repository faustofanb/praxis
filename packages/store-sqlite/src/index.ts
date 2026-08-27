import type { EventStore } from "@praxis/contracts";
import { packageName as contractsPackageName } from "@praxis/contracts";
import { openDatabase } from "./db";
import { migrate } from "./migrations";
import { SqliteEventStore } from "./session-store";

/**
 * Public API of @praxis/store-sqlite. Deep imports are forbidden
 * (.praxis/architecture.yaml); openSessionStore is the only construction
 * path and always migrates to the current schema version first.
 */

export type SessionStore = EventStore & {
  close(): void;
};

export function openSessionStore(path: string): SessionStore {
  const db = openDatabase(path);
  migrate(db);
  return new SqliteEventStore(db);
}

export const packageName = "@praxis/store-sqlite";
export const workspaceDependencies = [contractsPackageName] as const;
