import type { SessionCreatedEvent, SessionEventUnion } from "@praxis/contracts";
import {
  asEventId,
  asSessionId,
  asTurnId,
  EMPTY_STREAM_HEAD_SEQ,
  EVENT_SCHEMA_VERSION,
  EventStoreConflictError,
  SESSION_EVENT_TYPES,
  SessionCreatedEventSchema,
  SessionEventUnionSchema,
  ToolExecutionStatusSchema,
} from "@praxis/contracts";
import { describe, expect, test } from "vitest";
import { inMemoryEventStore } from "./helpers/in-memory-event-store";

const sessionId = asSessionId("session-1");
const eventId = asEventId("event-1");

function envelopeOverrides() {
  return {
    id: eventId,
    sessionId,
    seq: 1,
    schemaVersion: EVENT_SCHEMA_VERSION,
    occurredAt: 1_777_777_777_777,
    actor: { kind: "system" as const },
  };
}

describe("branded ids", () => {
  test("accept non-empty strings", () => {
    expect(asSessionId("s").valueOf()).toBe("s");
    expect(asEventId("e").valueOf()).toBe("e");
    expect(asTurnId("t").valueOf()).toBe("t");
  });

  test("reject empty strings", () => {
    expect(() => asSessionId("")).toThrow();
    expect(() => asEventId("")).toThrow();
    expect(() => asTurnId("")).toThrow();
  });
});

describe("event envelope", () => {
  test("parses a minimal SessionCreated event without optional fields", () => {
    const event = SessionCreatedEventSchema.parse({
      ...envelopeOverrides(),
      type: "SessionCreated",
      payload: {},
    });
    expect(event.type).toBe("SessionCreated");
    expect(event.causationId).toBeUndefined();
    expect(event.correlationId).toBeUndefined();
  });

  test("parses optional causation and correlation when present", () => {
    const event = SessionCreatedEventSchema.parse({
      ...envelopeOverrides(),
      causationId: "event-0",
      correlationId: "corr-1",
      type: "SessionCreated",
      payload: { reason: "user request" },
    });
    expect(event.causationId).toBe("event-0");
    expect(event.correlationId).toBe("corr-1");
    expect(event.payload.reason).toBe("user request");
  });

  test("rejects non-positive, zero, or fractional seq", () => {
    for (const seq of [0, -1, 1.5]) {
      expect(() =>
        SessionCreatedEventSchema.parse({
          ...envelopeOverrides(),
          seq,
          type: "SessionCreated",
          payload: {},
        }),
      ).toThrow();
    }
  });

  test("rejects unknown actor kinds and negative timestamps", () => {
    expect(() =>
      SessionCreatedEventSchema.parse({
        ...envelopeOverrides(),
        actor: { kind: "root" },
        type: "SessionCreated",
        payload: {},
      }),
    ).toThrow();
    expect(() =>
      SessionCreatedEventSchema.parse({
        ...envelopeOverrides(),
        occurredAt: -1,
        type: "SessionCreated",
        payload: {},
      }),
    ).toThrow();
  });
});

describe("session event union", () => {
  test("covers the v1 vocabulary", () => {
    expect(SESSION_EVENT_TYPES).toEqual([
      "SessionCreated",
      "SessionResumed",
      "SessionPaused",
      "SessionCompleted",
      "TurnStarted",
      "TurnCompleted",
    ]);
  });

  test("narrows payload by event type", () => {
    const event = SessionEventUnionSchema.parse({
      ...envelopeOverrides(),
      type: "TurnStarted",
      payload: { turnId: "turn-1" },
    }) as Extract<SessionEventUnion, { type: "TurnStarted" }>;
    expect(event.payload.turnId).toBe("turn-1");
  });

  test("rejects a payload missing required fields", () => {
    expect(() =>
      SessionEventUnionSchema.parse({
        ...envelopeOverrides(),
        type: "TurnStarted",
        payload: {},
      }),
    ).toThrow();
  });

  test("rejects event types outside the v1 vocabulary", () => {
    expect(() =>
      SessionEventUnionSchema.parse({
        ...envelopeOverrides(),
        type: "ToolSucceeded",
        payload: {},
      }),
    ).toThrow();
  });
});

describe("tool execution status", () => {
  test("accepts every documented status", () => {
    for (const status of [
      "PROPOSED",
      "AUTHORIZED",
      "REJECTED",
      "EXECUTING",
      "SUCCEEDED",
      "FAILED",
      "INDETERMINATE",
    ] as const) {
      expect(ToolExecutionStatusSchema.parse(status)).toBe(status);
    }
  });

  test("rejects undocumented statuses", () => {
    expect(() => ToolExecutionStatusSchema.parse("TIMEOUT")).toThrow();
  });
});

describe("EventStore port", () => {
  test("an in-memory implementation satisfies the interface contract", async () => {
    const store = inMemoryEventStore();

    const created: SessionCreatedEvent = {
      ...envelopeOverrides(),
      type: "SessionCreated",
      payload: {},
    };
    await store.append([created], EMPTY_STREAM_HEAD_SEQ);
    await expect(store.append([created], EMPTY_STREAM_HEAD_SEQ)).rejects.toBeInstanceOf(
      EventStoreConflictError,
    );
    await expect(store.readStream(sessionId)).resolves.toHaveLength(1);
    await expect(store.readStream(sessionId, 1)).resolves.toHaveLength(0);
  });
});
