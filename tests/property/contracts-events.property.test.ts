import type { EventActor, SessionEventUnion } from "@praxis/contracts";
import {
  asChallengeId,
  asEventId,
  asHypothesisId,
  asObservationId,
  asPlanId,
  asSessionId,
  asToolExecutionId,
  asTurnId,
  EPISTEMIC_EVENT_TYPES,
  EVENT_SCHEMA_VERSION,
  MODEL_EVENT_TYPES,
  SESSION_EVENT_TYPES,
  SessionEventUnionSchema,
  TOOL_EVENT_TYPES,
} from "@praxis/contracts";
import fc from "fast-check";
import { expect, test } from "vitest";

const nonEmptyString = fc.string({ minLength: 1 }).filter((s) => s.trim().length > 0);

const positiveInt = fc.integer({ min: 1 });

/** The full v1 vocabulary: any of these must parse, anything else must not. */
const KNOWN_EVENT_TYPES = [
  ...SESSION_EVENT_TYPES,
  ...TOOL_EVENT_TYPES,
  ...MODEL_EVENT_TYPES,
  ...EPISTEMIC_EVENT_TYPES,
] as const;

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
      fc.string().filter((s) => !(KNOWN_EVENT_TYPES as readonly string[]).includes(s)),
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

const evidenceArbitrary = fc
  .array(nonEmptyString, { maxLength: 3 })
  .map((ids) => ids.map((id) => asEventId(id)));

const observationSourceArbitrary = fc.oneof(
  nonEmptyString.map((id) => ({ kind: "tool" as const, toolExecutionId: asToolExecutionId(id) })),
  fc.constant({ kind: "user" as const }),
  nonEmptyString.map((detail) => ({ kind: "system" as const, detail })),
);

const epistemicEventArbitrary: fc.Arbitrary<SessionEventUnion> = fc
  .oneof(
    fc
      .record({
        goal: nonEmptyString,
        constraints: fc.array(nonEmptyString, { maxLength: 3 }),
        need: fc.option(nonEmptyString, { nil: undefined }),
      })
      .map((f) => ({
        type: "GoalSet" as const,
        payload: {
          goal: f.goal,
          constraints: f.constraints.map((description) => ({ description })),
          ...(f.need === undefined ? {} : { need: f.need }),
        },
      })),
    fc
      .record({
        observationId: nonEmptyString,
        source: observationSourceArbitrary,
        claim: nonEmptyString,
        evidence: evidenceArbitrary,
      })
      .map((f) => ({
        type: "ObservationRecorded" as const,
        payload: {
          observationId: asObservationId(f.observationId),
          source: f.source,
          claim: f.claim,
          evidenceEventIds: f.evidence,
        },
      })),
    fc
      .record({
        hypothesisId: nonEmptyString,
        statement: nonEmptyString,
        support: evidenceArbitrary,
        conflicts: evidenceArbitrary,
      })
      .map((f) => ({
        type: "HypothesisProposed" as const,
        payload: {
          hypothesisId: asHypothesisId(f.hypothesisId),
          statement: f.statement,
          support: f.support,
          conflicts: f.conflicts,
        },
      })),
    fc
      .record({
        hypothesisId: nonEmptyString,
        to: fc.constantFrom("supported", "falsified", "superseded" as const),
        evidence: evidenceArbitrary,
        reason: fc.option(nonEmptyString, { nil: undefined }),
      })
      .map((f) => ({
        type: "HypothesisStatusChanged" as const,
        payload: {
          hypothesisId: asHypothesisId(f.hypothesisId),
          to: f.to,
          evidenceEventIds: f.evidence,
          ...(f.reason === undefined ? {} : { reason: f.reason }),
        },
      })),
    fc
      .record({
        planId: nonEmptyString,
        goalRef: nonEmptyString,
        hypothesisId: fc.option(nonEmptyString, { nil: undefined }),
        nextAction: nonEmptyString,
        falsifiedIf: fc.option(nonEmptyString, { nil: undefined }),
      })
      .map((f) => ({
        type: "PlanSet" as const,
        payload: {
          planId: asPlanId(f.planId),
          goalRef: f.goalRef,
          ...(f.hypothesisId === undefined ? {} : { hypothesisId: asHypothesisId(f.hypothesisId) }),
          nextAction: f.nextAction,
          ...(f.falsifiedIf === undefined ? {} : { falsifiedIf: f.falsifiedIf }),
        },
      })),
    fc.record({ planId: nonEmptyString, reason: nonEmptyString }).map((f) => ({
      type: "PlanInvalidated" as const,
      payload: { planId: asPlanId(f.planId), reason: f.reason },
    })),
    fc
      .record({
        challengeId: nonEmptyString,
        // Spread keeps targetType/targetId paired as the discriminated union.
        target: fc.oneof(
          nonEmptyString.map((id) => ({
            targetType: "hypothesis" as const,
            targetId: asHypothesisId(id),
          })),
          nonEmptyString.map((id) => ({ targetType: "plan" as const, targetId: asPlanId(id) })),
          nonEmptyString.map((id) => ({ targetType: "completion" as const, targetId: id })),
          nonEmptyString.map((id) => ({ targetType: "policy" as const, targetId: id })),
        ),
        claim: nonEmptyString,
        evidence: evidenceArbitrary,
      })
      .map((f) => ({
        type: "ChallengeRaised" as const,
        payload: {
          challengeId: asChallengeId(f.challengeId),
          ...f.target,
          claim: f.claim,
          evidenceEventIds: f.evidence,
        },
      })),
    fc
      .record({
        challengeId: nonEmptyString,
        outcome: fc.constantFrom("accepted", "rejected", "resolved" as const),
        reason: nonEmptyString,
      })
      .map((f) => ({
        type: "ChallengeResolved" as const,
        payload: {
          challengeId: asChallengeId(f.challengeId),
          outcome: f.outcome,
          reason: f.reason,
        },
      })),
    fc
      .record({
        outcome: fc.constantFrom("passed", "failed", "inconclusive" as const),
        summary: nonEmptyString,
        evidence: evidenceArbitrary,
      })
      .map((f) => ({
        type: "VerificationRecorded" as const,
        payload: { outcome: f.outcome, summary: f.summary, evidenceEventIds: f.evidence },
      })),
  )
  .map((typed) => ({
    id: asEventId("epistemic-event"),
    sessionId: asSessionId("session-epistemic"),
    seq: 1,
    schemaVersion: EVENT_SCHEMA_VERSION,
    occurredAt: 0,
    actor: { kind: "system" } as const,
    ...typed,
  }));

test("every well-formed epistemic event survives a JSON round-trip unchanged", () => {
  fc.assert(
    fc.property(epistemicEventArbitrary, (event) => {
      const reparsed = SessionEventUnionSchema.parse(JSON.parse(JSON.stringify(event)));
      expect(reparsed).toEqual(event);
    }),
  );
});

test("epistemic payload variants outside the declared unions are rejected", () => {
  fc.assert(
    fc.property(nonEmptyString, (id) => {
      const base = { ...sampleBaseEvent(), type: "HypothesisStatusChanged" };
      const statusChange = SessionEventUnionSchema.safeParse({
        ...base,
        payload: { hypothesisId: asHypothesisId(id), to: "proposed" },
      });
      expect(statusChange.success).toBe(false);
      const challengeOutcome = SessionEventUnionSchema.safeParse({
        ...sampleBaseEvent(),
        type: "ChallengeResolved",
        payload: { challengeId: asChallengeId(id), outcome: "open", reason: "not terminal" },
      });
      expect(challengeOutcome.success).toBe(false);
      const verification = SessionEventUnionSchema.safeParse({
        ...sampleBaseEvent(),
        type: "VerificationRecorded",
        payload: { outcome: "maybe", summary: "undecided", evidenceEventIds: [] },
      });
      expect(verification.success).toBe(false);
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
