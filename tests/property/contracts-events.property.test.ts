import type { EventActor, SessionEventUnion } from "@praxis/contracts";
import {
  asEventId,
  asSessionId,
  asToolExecutionId,
  asTurnId,
  EVENT_SCHEMA_VERSION,
  SESSION_EVENT_TYPES,
  SessionEventUnionSchema,
} from "@praxis/contracts";
import fc from "fast-check";
import { expect, test } from "vitest";

const nonEmptyString = fc.string({ minLength: 1 }).filter((s) => s.trim().length > 0);

const positiveInt = fc.integer({ min: 1 });

const eventActor: fc.Arbitrary<EventActor> = fc.oneof(
  fc.constant<EventActor>({ kind: "user" }),
  fc.constant<EventActor>({ kind: "system" }),
  fc
    .record({ provider: nonEmptyString, model: nonEmptyString })
    .map((fields): EventActor => ({ kind: "model", ...fields })),
  nonEmptyString.map(
    (id): EventActor => ({
      kind: "tool",
      toolExecutionId: asToolExecutionId(id),
    }),
  ),
);

const eventArbitrary: fc.Arbitrary<SessionEventUnion> = fc
  .record({
    eventId: nonEmptyString,
    sessionId: nonEmptyString,
    seq: positiveInt,
    occurredAt: fc.nat(),
    actor: eventActor,
    causationId: fc.option(nonEmptyString, { nil: undefined }),
    type: fc.constantFrom(...SESSION_EVENT_TYPES),
    turnId: nonEmptyString,
    reason: fc.option(nonEmptyString, { nil: undefined }),
  })
  .map((fields) => {
    const payload =
      fields.type === "SessionCreated"
        ? { reason: fields.reason }
        : fields.type === "TurnStarted" || fields.type === "TurnCompleted"
          ? { turnId: fields.turnId }
          : {};
    return {
      id: asEventId(fields.eventId),
      sessionId: asSessionId(fields.sessionId),
      seq: fields.seq,
      schemaVersion: EVENT_SCHEMA_VERSION,
      occurredAt: fields.occurredAt,
      actor: fields.actor,
      causationId: fields.causationId === undefined ? undefined : asEventId(fields.causationId),
      type: fields.type,
      payload,
    } as SessionEventUnion;
  });

test("every well-formed event survives a JSON round-trip unchanged", () => {
  fc.assert(
    fc.property(eventArbitrary, (event) => {
      const reparsed = SessionEventUnionSchema.parse(JSON.parse(JSON.stringify(event)));
      expect(reparsed).toEqual(event);
    }),
  );
});

test("parse of a valid event is the identity", () => {
  fc.assert(
    fc.property(eventArbitrary, (event) => {
      expect(SessionEventUnionSchema.parse(event)).toEqual(event);
    }),
  );
});

test("seq is accepted exactly when it is a positive integer", () => {
  fc.assert(
    fc.property(fc.integer({ min: -1000, max: 1000 }), fc.boolean(), (n, makeFractional) => {
      const seq = makeFractional ? n + 0.5 : n;
      const accepted =
        SessionEventUnionSchema.safeParse({
          ...sampleBaseEvent(),
          seq,
          type: "SessionResumed",
          payload: {},
        }).success === true;
      expect(accepted).toBe(Number.isInteger(seq) && seq >= 1);
    }),
  );
});

test("event types outside the v1 vocabulary are rejected", () => {
  fc.assert(
    fc.property(
      fc.string().filter((s) => !(SESSION_EVENT_TYPES as readonly string[]).includes(s)),
      (unknownType) => {
        const result = SessionEventUnionSchema.safeParse({
          ...sampleBaseEvent(),
          type: unknownType,
          payload: {},
        });
        expect(result.success).toBe(false);
      },
    ),
  );
});

test("turn payload turnIds are preserved exactly", () => {
  fc.assert(
    fc.property(nonEmptyString, positiveInt, (id, seq) => {
      const event = SessionEventUnionSchema.parse({
        ...sampleBaseEvent(),
        seq,
        type: "TurnStarted",
        payload: { turnId: asTurnId(id) },
      }) as Extract<SessionEventUnion, { type: "TurnStarted" }>;
      expect(event.payload.turnId.valueOf()).toBe(id);
      expect(event.seq).toBe(seq);
    }),
  );
});

function sampleBaseEvent() {
  return {
    id: asEventId("event-base"),
    sessionId: asSessionId("session-base"),
    schemaVersion: EVENT_SCHEMA_VERSION,
    occurredAt: 0,
    actor: { kind: "user" } as const,
  };
}
