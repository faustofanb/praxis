import { afterEach, beforeEach, test } from "bun:test";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { EMPTY_STREAM_HEAD_SEQ, EventStoreConflictError } from "@praxis/contracts";
import { foldSessionEvents } from "@praxis/core";
import type { SessionStore } from "@praxis/store-sqlite";
import { openSessionStore } from "@praxis/store-sqlite";
import fc from "fast-check";
import { inMemoryEventStore } from "../helpers/in-memory-event-store";
import { commandArbitrary, translateCommands } from "../helpers/random-session-streams";
import { TEST_SESSION_ID } from "../helpers/session-events";

/**
 * Store parity: the in-memory reference store and the SQLite adapter must
 * be observationally equivalent for property-generated streams — identical
 * readStream output, identical folded state, identical conflict behavior,
 * and identical afterSeq filtering.
 */

let dir: string;
let sqlite: SessionStore;

beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), "praxis-parity-"));
  sqlite = openSessionStore(join(dir, "parity.sqlite"));
});

afterEach(() => {
  sqlite.close();
  rmSync(dir, { recursive: true, force: true });
});

let iterationCount = 0;

test("both stores read back the same stream and fold the same state", () => {
  fc.assert(
    fc.asyncProperty(
      fc.array(commandArbitrary, { maxLength: 40 }),
      fc.nat(),
      async (commands, seed) => {
        const events = translateCommands(commands);
        const memory = inMemoryEventStore();
        // One fresh SQLite database per iteration: the session stream is
        // fixed, and fast-check may reuse seed values across iterations.
        iterationCount += 1;
        const iteration = openSessionStore(join(dir, `parity-${iterationCount}.sqlite`));
        try {
          const batches = splitIntoBatches(events, seed);
          let head = EMPTY_STREAM_HEAD_SEQ;
          for (const batch of batches) {
            await memory.append(batch, head);
            await iteration.append(batch, head);
            head += batch.length;
          }
          const fromMemory = await memory.readStream(TEST_SESSION_ID);
          const fromSqlite = await iteration.readStream(TEST_SESSION_ID);
          if (JSON.stringify(fromMemory) !== JSON.stringify(fromSqlite)) {
            throw new Error("stores diverged on readStream output");
          }
          if (
            JSON.stringify(foldSessionEvents(fromMemory)) !==
            JSON.stringify(foldSessionEvents(fromSqlite))
          ) {
            throw new Error("stores diverged on folded state");
          }
        } finally {
          iteration.close();
        }
      },
    ),
  );
});

test("both stores reject a stale head with EventStoreConflictError and write nothing", async () => {
  const events = translateCommands([{ kind: "pause" }]);
  const memory = inMemoryEventStore();
  await memory.append(events, EMPTY_STREAM_HEAD_SEQ);
  await sqlite.append(events, EMPTY_STREAM_HEAD_SEQ);

  const outcomes = await Promise.all(
    [memory, sqlite].map(async (store) => {
      try {
        await store.append(events, EMPTY_STREAM_HEAD_SEQ);
        return "accepted";
      } catch (error) {
        return error instanceof EventStoreConflictError ? "conflict" : "other";
      }
    }),
  );
  if (outcomes[0] !== "conflict" || outcomes[1] !== "conflict") {
    throw new Error(`conflict behavior diverged: ${outcomes.join(", ")}`);
  }
  const remaining = await Promise.all(
    [memory, sqlite].map((store) => store.readStream(TEST_SESSION_ID)),
  );
  if (remaining[0]?.length !== remaining[1]?.length) {
    throw new Error("stores diverged on post-conflict stream length");
  }
});

test("both stores filter identically via afterSeq", async () => {
  const events = translateCommands([
    { kind: "startTurn", turn: 1 },
    { kind: "completeTurn" },
    { kind: "pause" },
  ]);
  const memory = inMemoryEventStore();
  await memory.append(events, EMPTY_STREAM_HEAD_SEQ);
  await sqlite.append(events, EMPTY_STREAM_HEAD_SEQ);

  for (let after = 0; after <= events.length; after += 1) {
    const fromMemory = await memory.readStream(TEST_SESSION_ID, after);
    const fromSqlite = await sqlite.readStream(TEST_SESSION_ID, after);
    if (JSON.stringify(fromMemory) !== JSON.stringify(fromSqlite)) {
      throw new Error(`stores diverged afterSeq=${after}`);
    }
  }
});

/** Deterministically split a stream into non-empty batches (seed varies cuts). */
function splitIntoBatches<T>(events: readonly T[], seed: number): T[][] {
  if (events.length === 0) {
    return [];
  }
  const batches: T[][] = [];
  let index = 0;
  let step = seed % 3;
  while (index < events.length) {
    const size = 1 + ((step + index) % 3);
    batches.push(events.slice(index, index + size) as T[]);
    index += size;
    step += 1;
  }
  return batches;
}
