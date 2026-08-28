import {
  ChallengeRaisedEventSchema,
  ChallengeRaisedPayloadSchema,
  ChallengeResolvedEventSchema,
  ChallengeResolvedPayloadSchema,
  ChallengeSchema,
  ChallengeStatusSchema,
  ChallengeTargetTypeSchema,
  EPISTEMIC_EVENT_TYPES,
  GoalSetEventSchema,
  GoalSetPayloadSchema,
  HYPOTHESIS_STATUS_CHANGES,
  HypothesisStatusChangeSchema,
  PLAN_STATUSES,
  SessionEventUnionSchema,
} from "@praxis/contracts";
import { describe, expect, test } from "vitest";
import {
  challengeRaised,
  challengeResolved,
  goalSet,
  hypothesisProposed,
  hypothesisStatusChanged,
  observationRecorded,
  planInvalidated,
  planSet,
  verificationRecorded,
} from "./helpers/session-events";

function envelopeOf(event: ReturnType<typeof goalSet>) {
  const { type: _type, payload: _payload, ...envelope } = event;
  return envelope;
}

describe("epistemic event schemas", () => {
  test("every epistemic event type parses through its owning schema", () => {
    const samples = [
      goalSet(1, { goal: "restore the payment record" }),
      observationRecorded(2, 1),
      hypothesisProposed(3, 1),
      hypothesisStatusChanged(4, 1, "supported"),
      planSet(5, 1),
      planInvalidated(6, 1),
      challengeRaised(7, 1),
      challengeResolved(8, 1),
      verificationRecorded(9),
    ];
    for (const sample of samples) {
      expect(SessionEventUnionSchema.parse(sample)).toBeTruthy();
    }
  });

  test("the vocabulary covers exactly the nine Goal/Epistemic events", () => {
    expect(EPISTEMIC_EVENT_TYPES).toEqual([
      "GoalSet",
      "ObservationRecorded",
      "HypothesisProposed",
      "HypothesisStatusChanged",
      "PlanSet",
      "PlanInvalidated",
      "ChallengeRaised",
      "ChallengeResolved",
      "VerificationRecorded",
    ]);
  });

  test("GoalSet requires a goal and carries constraints as facts", () => {
    const parsed = GoalSetEventSchema.parse(
      goalSet(1, { goal: "g", constraints: ["a", "b"], need: "n" }),
    );
    expect(parsed.payload.goal).toBe("g");
    expect(parsed.payload.constraints).toEqual([{ description: "a" }, { description: "b" }]);
    expect(() => GoalSetPayloadSchema.parse({ goal: "", constraints: [] })).toThrow();
    expect(() => GoalSetPayloadSchema.parse({ goal: "g" })).toThrow();
  });

  test("hypothesis status changes never carry the birth status", () => {
    expect([...HYPOTHESIS_STATUS_CHANGES]).not.toContain("proposed");
    for (const to of HYPOTHESIS_STATUS_CHANGES) {
      expect(HypothesisStatusChangeSchema.parse(to)).toBe(to);
    }
    expect(() => HypothesisStatusChangeSchema.parse("proposed")).toThrow();
  });

  test("plan statuses exclude the unproducible completed value", () => {
    expect([...PLAN_STATUSES]).toEqual(["active", "invalidated", "superseded"]);
  });

  test("ChallengeRaised payloads discriminate on targetType with branded ids", () => {
    const hypothesisTarget = ChallengeRaisedPayloadSchema.parse(
      challengeRaised(1, 1, { targetType: "hypothesis", target: "hyp-9" }).payload,
    );
    expect(hypothesisTarget.targetType).toBe("hypothesis");
    const free = ChallengeRaisedPayloadSchema.parse(
      challengeRaised(1, 1, { targetType: "completion", target: "final-answer" }).payload,
    );
    expect(free.targetType).toBe("completion");
    for (const targetType of ["hypothesis", "plan", "completion", "policy"] as const) {
      expect(ChallengeTargetTypeSchema.parse(targetType)).toBe(targetType);
    }
    expect(() =>
      ChallengeRaisedEventSchema.parse({
        ...envelopeOf(goalSet(1)),
        type: "ChallengeRaised",
        payload: {
          challengeId: "challenge-1",
          targetType: "hypothesis",
          targetId: "",
          claim: "c",
          evidenceEventIds: [],
        },
      }),
    ).toThrow();
    expect(() =>
      ChallengeRaisedPayloadSchema.parse({
        challengeId: "challenge-1",
        targetType: "session",
        targetId: "x",
        claim: "c",
        evidenceEventIds: [],
      }),
    ).toThrow();
  });

  test("ChallengeResolved requires a terminal outcome and a reason", () => {
    const parsed = ChallengeResolvedPayloadSchema.parse(
      challengeResolved(1, 1, "accepted", "the challenge stands").payload,
    );
    expect(parsed.outcome).toBe("accepted");
    expect(() =>
      ChallengeResolvedEventSchema.parse({
        ...envelopeOf(goalSet(1)),
        type: "ChallengeResolved",
        payload: { challengeId: "challenge-1", outcome: "open", reason: "not terminal" },
      }),
    ).toThrow();
    expect(() =>
      ChallengeResolvedPayloadSchema.parse({
        challengeId: "challenge-1",
        outcome: "rejected",
        reason: "",
      }),
    ).toThrow();
  });

  test("the challenge state entity validates through its owning schema", () => {
    const challenge = ChallengeSchema.parse({
      challengeId: "challenge-1",
      targetType: "plan",
      targetId: "plan-1",
      claim: "the plan ignores counterevidence",
      evidenceEventIds: [],
      status: "open",
    });
    expect(challenge.status).toBe("open");
    expect(ChallengeStatusSchema.parse("resolved")).toBe("resolved");
    expect(() => ChallengeSchema.parse({ ...challenge, status: "pending" })).toThrow();
  });

  test("empty claims and unknown verification outcomes are rejected at the boundary", () => {
    expect(() =>
      SessionEventUnionSchema.parse({
        ...observationRecorded(1, 1),
        payload: {
          observationId: "obs-1",
          source: { kind: "user" },
          claim: "",
          evidenceEventIds: [],
        },
      }),
    ).toThrow();
    expect(() =>
      SessionEventUnionSchema.parse({
        ...verificationRecorded(1),
        payload: { outcome: "maybe", summary: "s", evidenceEventIds: [] },
      }),
    ).toThrow();
  });
});
