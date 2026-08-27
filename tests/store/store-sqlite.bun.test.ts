import { Database } from "bun:sqlite";
import { afterEach, beforeEach, describe, expect, test } from "bun:test";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { EMPTY_STREAM_HEAD_SEQ, EventStoreConflictError } from "@praxis/contracts";
import { foldSessionEvents } from "@praxis/core";
import type { SessionStore } from "@praxis/store-sqlite";
import { openSessionStore } from "@praxis/store-sqlite";
import {
  sessionCompleted,
  sessionCreated,
  sessionPaused,
  sessionResumed,
  TEST_SESSION_ID,
  turnCompleted,
  turnStarted,
} from "../helpers/session-events";

let dir: string;
let dbPath: string;
let store: SessionStore;

beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), "praxis-store-"));
  dbPath = join(dir, "store.sqlite");
  store = openSessionStore(dbPath);
});

afterEach(() => {
  store.close();
  rmSync(dir, { recursive: true, force: true });
});

function lifecycleEvents() {
  return [
    sessionCreated(1, "user request"),
    turnStarted(2, 1),
    turnCompleted(3, 1),
    sessionPaused(4),
    sessionResumed(5),
    turnStarted(6, 2),
    turnCompleted(7, 2),
    sessionCompleted(8),
  ];
}

describe("sqlite event store", () => {
  test("append in batches and read the stream back unchanged", async () => {
    const events = lifecycleEvents();
    await store.append(events.slice(0, 3), EMPTY_STREAM_HEAD_SEQ);
    await store.append(events.slice(3, 5), 3);
    await store.append(events.slice(5), 5);

    const stream = await store.readStream(TEST_SESSION_ID);
    expect(stream.length).toBe(8);
    expect(stream).toEqual(events);
  });

  test("stale expectedHeadSeq conflicts and writes nothing", async () => {
    const events = lifecycleEvents();
    await store.append(events.slice(0, 2), EMPTY_STREAM_HEAD_SEQ);

    let conflict: unknown;
    try {
      await store.append(events.slice(2, 4), EMPTY_STREAM_HEAD_SEQ);
    } catch (error) {
      conflict = error;
    }
    expect(conflict).toBeInstanceOf(EventStoreConflictError);
    expect((await store.readStream(TEST_SESSION_ID)).length).toBe(2);
  });

  test("a batch with a seq gap is rejected atomically", async () => {
    await store.append([sessionCreated(1)], EMPTY_STREAM_HEAD_SEQ);

    let failure: unknown;
    try {
      await store.append([turnStarted(3, 1), turnCompleted(4, 1)], 1);
    } catch (error) {
      failure = error;
    }
    expect(failure instanceof Error).toBe(true);
    const stream = await store.readStream(TEST_SESSION_ID);
    expect(stream.length).toBe(1);
  });

  test("reopen replays identical events and re-applies no migration", async () => {
    const events = lifecycleEvents();
    await store.append(events.slice(0, 4), EMPTY_STREAM_HEAD_SEQ);
    const beforeFold = foldSessionEvents(await store.readStream(TEST_SESSION_ID));
    store.close();

    store = openSessionStore(dbPath);
    const stream = await store.readStream(TEST_SESSION_ID);
    expect(stream).toEqual(events.slice(0, 4));
    expect(foldSessionEvents(stream)).toEqual(beforeFold);
  });

  test("full lifecycle folds through the core reducer", async () => {
    await store.append(lifecycleEvents(), EMPTY_STREAM_HEAD_SEQ);
    const state = foldSessionEvents(await store.readStream(TEST_SESSION_ID));
    expect(state.status).toBe("COMPLETED");
    expect(state.headSeq).toBe(8);
    expect(state.currentTurnId).toBeUndefined();
  });

  test("readStream resumes from a checkpoint via afterSeq", async () => {
    await store.append(lifecycleEvents(), EMPTY_STREAM_HEAD_SEQ);
    const tail = await store.readStream(TEST_SESSION_ID, 5);
    expect(tail.map((event) => event.type)).toEqual([
      "TurnStarted",
      "TurnCompleted",
      "SessionCompleted",
    ]);
  });

  test("corrupted actor JSON fails validation on read", async () => {
    await store.append(lifecycleEvents(), EMPTY_STREAM_HEAD_SEQ);

    const raw = new Database(dbPath);
    try {
      raw.exec("UPDATE events SET actor_json = 'not-json' WHERE seq = 2");

      let failure: unknown;
      try {
        await store.readStream(TEST_SESSION_ID);
      } catch (error) {
        failure = error;
      }
      expect(failure instanceof Error).toBe(true);
    } finally {
      raw.close();
    }
  });

  test("an unknown persisted event type fails validation on read", async () => {
    await store.append(lifecycleEvents(), EMPTY_STREAM_HEAD_SEQ);

    const raw = new Database(dbPath);
    try {
      raw.exec("UPDATE events SET type = 'Teleported' WHERE seq = 4");

      let failure: unknown;
      try {
        await store.readStream(TEST_SESSION_ID);
      } catch (error) {
        failure = error;
      }
      expect(failure instanceof Error).toBe(true);
    } finally {
      raw.close();
    }
  });

  test("the public surface is append, readStream, and close only", () => {
    const own = Object.getOwnPropertyNames(Object.getPrototypeOf(store)).sort();
    expect(own).toEqual(["append", "close", "constructor", "readStream"]);
  });
});
