import { EMPTY_STREAM_HEAD_SEQ, EventStoreConflictError } from "@praxis/contracts";
import { foldSessionEvents, initialSessionState, reduceSession } from "@praxis/core";
import { describe, expect, test } from "vitest";
import { inMemoryEventStore } from "../helpers/in-memory-event-store";
import {
  sessionCompleted,
  sessionCreated,
  sessionPaused,
  sessionResumed,
  TEST_SESSION_ID,
  turnCompleted,
  turnStarted,
} from "../helpers/session-events";

describe("session reducer over the EventStore port", () => {
  test("append with optimistic concurrency, read back, and replay to the same state", async () => {
    const store = inMemoryEventStore();
    const created = sessionCreated(1, "user request");
    const firstTurn = turnStarted(2, 1);
    const firstDone = turnCompleted(3, 1);
    const paused = sessionPaused(4);
    const resumed = sessionResumed(5);
    const secondTurn = turnStarted(6, 2);
    const secondDone = turnCompleted(7, 2);
    const completed = sessionCompleted(8);

    await store.append([created, firstTurn], EMPTY_STREAM_HEAD_SEQ);

    // A stale head prediction conflicts and writes nothing.
    await expect(store.append([firstDone], EMPTY_STREAM_HEAD_SEQ)).rejects.toBeInstanceOf(
      EventStoreConflictError,
    );
    expect(await store.readStream(TEST_SESSION_ID)).toHaveLength(2);

    await store.append([firstDone, paused, resumed], 2);
    await store.append([secondTurn, secondDone, completed], 5);

    const stream = await store.readStream(TEST_SESSION_ID);
    expect(stream.map((event) => event.seq)).toEqual([1, 2, 3, 4, 5, 6, 7, 8]);

    // Incremental live folding must equal full-stream replay.
    let live = initialSessionState();
    for (const event of stream) {
      live = reduceSession(live, event);
    }
    const replayed = foldSessionEvents(stream);
    expect(replayed).toEqual(live);
    expect(replayed.status).toBe("COMPLETED");
    expect(replayed.headSeq).toBe(8);
  });

  test("readStream afterSeq supports resuming a projection from a checkpoint", async () => {
    const store = inMemoryEventStore();
    await store.append(
      [sessionCreated(1), turnStarted(2, 1), turnCompleted(3, 1)],
      EMPTY_STREAM_HEAD_SEQ,
    );
    const tail = await store.readStream(TEST_SESSION_ID, 2);
    expect(tail.map((event) => event.type)).toEqual(["TurnCompleted"]);
    expect(tail.map((event) => event.seq)).toEqual([3]);
  });

  test("the store refuses a batch that would break seq continuity", async () => {
    const store = inMemoryEventStore();
    await store.append([sessionCreated(1)], EMPTY_STREAM_HEAD_SEQ);
    await expect(store.append([turnStarted(3, 1)], 1)).rejects.toThrow(/continuity/);
  });
});
