import type { Database } from "bun:sqlite";
import { createRequire } from "node:module";

/**
 * bun:sqlite is bound lazily so importing this module under a non-Bun
 * runtime (e.g. the Node-hosted vitest suite reaching the package entry
 * for manifest smoke checks) does not throw; only actually opening a
 * database requires the Bun runtime.
 */
const runtimeRequire = createRequire(import.meta.url);

/**
 * Open the store database with the pragmas the event store relies on:
 * strict typing on binds, FK enforcement, WAL for single-writer durability.
 * ":memory:" databases are supported for tests.
 */
export function openDatabase(path: string): Database {
  const { Database: BunDatabase } = runtimeRequire("bun:sqlite") as {
    Database: typeof Database;
  };
  const db = new BunDatabase(path, { strict: true });
  db.exec("PRAGMA foreign_keys = ON");
  db.exec("PRAGMA journal_mode = WAL");
  return db;
}
