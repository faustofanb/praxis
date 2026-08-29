import { asChallengeId, asHypothesisId, asObservationId, asPlanId } from "@praxis/contracts";
import type { DerivedSessionState } from "@praxis/core";
import {
  foldSessionEvents,
  IllegalTransitionError,
  initialSessionState,
  reduceSession,
} from "@praxis/core";
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
  sessionCompleted,
  sessionCreated,
  sessionPaused,
  turnCompleted,
  turnStarted,
  verificationRecorded,
} from "./helpers/session-events";

/**
 * Epistemic slice laws (docs/02 sections 5, 13-14, ADR-0012): session-level
 * facts with no open-turn requirement, id registries with terminal statuses,
 * evidence filed by direction, and honest inconclusive verification.
 */

function epistemicStream() {
  return [
    sessionCreated(1),
    goalSet(2, { goal: "restore the missing payment record" }),
    observationRecorded(3, 1, { evidence: [1] }),
    hypothesisProposed(4, 1),
    hypothesisStatusChanged(5, 1, "supported", { evidence: [3] }),
    planSet(6, 1, { hypothesis: 1, falsifiedIf: "the ledger has no matching entry" }),
    challengeRaised(7, 1, { targetType: "plan", target: "plan-1", evidence: [3] }),
    challengeResolved(8, 1, "rejected", "the ledger entry exists under an alias"),
  ];
}

describe("epistemic stream folding", () => {
  test("the full slice folds into goal/observation/hypothesis/plan/challenge state", () => {
    const state = foldSessionEvents(epistemicStream());
    expect(state.status).toBe("ACTIVE");
    expect(state.goal?.goal).toBe("restore the missing payment record");
    expect(state.goal?.constraints).toEqual([{ description: "stay read-only" }]);

    const observation = state.observations.get(asObservationId("obs-1"));
    expect(observation?.claim).toBe("the note file exists");
    // observedAt comes from the envelope, never from the payload.
    expect(observation?.observedAt).toBe(state.headSeq - 5);

    const hypothesis = state.hypotheses.get(asHypothesisId("hyp-1"));
    expect(hypothesis?.status).toBe("supported");
    expect(hypothesis?.support).toHaveLength(1);
    expect(hypothesis?.conflicts).toHaveLength(0);

    expect(state.activePlan?.planId).toEqual(asPlanId("plan-1"));
    expect(state.activePlan?.status).toBe("active");
    expect(state.activePlan?.hypothesisId).toEqual(asHypothesisId("hyp-1"));

    const challenge = state.challenges.get(asChallengeId("challenge-1"));
    expect(challenge?.status).toBe("rejected");
    expect(state.openChallenges).toHaveLength(0);
  });

  test("folding the stream twice yields identical states", () => {
    const events = epistemicStream();
    expect(foldSessionEvents(events)).toEqual(foldSessionEvents(events));
  });

  test("epistemic facts are legal with an open turn and between turns", () => {
    const midTurn = reduceSession(
      foldSessionEvents([sessionCreated(1), turnStarted(2, 1)]),
      goalSet(3),
    );
    expect(midTurn.goal?.goal).toBe("answer the user question");
    const betweenTurns = reduceSession(
      foldSessionEvents([sessionCreated(1), turnStarted(2, 1), turnCompleted(3, 1)]),
      observationRecorded(4, 1),
    );
    expect(betweenTurns.observations.size).toBe(1);
  });

  test("epistemic facts are illegal in EMPTY, PAUSED, and COMPLETED sessions", () => {
    expect(() => reduceSession(initialSessionState(), goalSet(1))).toThrow(IllegalTransitionError);
    const paused = foldSessionEvents([sessionCreated(1), sessionPaused(2)]);
    for (const event of [
      goalSet(3),
      observationRecorded(3, 1),
      hypothesisProposed(3, 1),
      hypothesisStatusChanged(3, 1, "supported"),
      planSet(3, 1),
      planInvalidated(3, 1),
      challengeRaised(3, 1),
      challengeResolved(3, 1),
      verificationRecorded(3),
    ]) {
      expect(() => reduceSession(paused, event)).toThrow(IllegalTransitionError);
    }
    const completed = foldSessionEvents([sessionCreated(1), sessionCompleted(2)]);
    expect(() => reduceSession(completed, goalSet(3))).toThrow(IllegalTransitionError);
  });
});

describe("id registries", () => {
  test("duplicate observation, hypothesis, plan, and challenge ids are rejected", () => {
    const base = foldSessionEvents([
      sessionCreated(1),
      observationRecorded(2, 1),
      hypothesisProposed(3, 1),
      planSet(4, 1),
      challengeRaised(5, 1),
    ]);
    expect(() => reduceSession(base, observationRecorded(6, 1))).toThrow(/already used/);
    expect(() => reduceSession(base, hypothesisProposed(6, 1))).toThrow(/already used/);
    expect(() => reduceSession(base, planSet(6, 1))).toThrow(/already used/);
    expect(() => reduceSession(base, challengeRaised(6, 1))).toThrow(/already used/);
  });

  test("unknown targets for status change, invalidation, and resolution are rejected", () => {
    const state = foldSessionEvents([sessionCreated(1)]);
    expect(() => reduceSession(state, hypothesisStatusChanged(2, 9, "supported"))).toThrow(
      /unknown hypothesis/,
    );
    expect(() => reduceSession(state, planInvalidated(2, 9))).toThrow(/unknown plan/);
    expect(() => reduceSession(state, challengeResolved(2, 9))).toThrow(/unknown challenge/);
  });
});

describe("hypothesis status law", () => {
  test("proposed may become supported, falsified, or superseded", () => {
    for (const to of ["supported", "falsified", "superseded"] as const) {
      const state = foldSessionEvents([
        sessionCreated(1),
        hypothesisProposed(2, 1),
        hypothesisStatusChanged(3, 1, to),
      ]);
      expect(state.hypotheses.get(asHypothesisId("hyp-1"))?.status).toBe(to);
    }
  });

  test("evidence files under support toward supported and conflicts toward falsified", () => {
    const supported = foldSessionEvents([
      sessionCreated(1),
      hypothesisProposed(2, 1),
      hypothesisStatusChanged(3, 1, "supported", { evidence: [2] }),
    ]);
    const s = supported.hypotheses.get(asHypothesisId("hyp-1"));
    expect(s?.support).toHaveLength(1);
    expect(s?.conflicts).toHaveLength(0);

    const falsified = foldSessionEvents([
      sessionCreated(1),
      hypothesisProposed(2, 1),
      hypothesisStatusChanged(3, 1, "supported", { evidence: [2] }),
      hypothesisStatusChanged(4, 1, "falsified", { evidence: [3] }),
    ]);
    const f = falsified.hypotheses.get(asHypothesisId("hyp-1"));
    expect(f?.status).toBe("falsified");
    expect(f?.support).toHaveLength(1);
    expect(f?.conflicts).toHaveLength(1);
  });

  test("falsified and superseded are terminal", () => {
    const falsified = foldSessionEvents([
      sessionCreated(1),
      hypothesisProposed(2, 1),
      hypothesisStatusChanged(3, 1, "falsified"),
    ]);
    for (const to of ["supported", "falsified", "superseded"] as const) {
      expect(() => reduceSession(falsified, hypothesisStatusChanged(4, 1, to))).toThrow(
        /cannot become/,
      );
    }
    const superseded = foldSessionEvents([
      sessionCreated(1),
      hypothesisProposed(2, 1),
      hypothesisStatusChanged(3, 1, "superseded"),
    ]);
    expect(() => reduceSession(superseded, hypothesisStatusChanged(4, 1, "falsified"))).toThrow(
      /cannot become/,
    );
  });

  test("a supported hypothesis may still be falsified, but not re-supported", () => {
    const supported = foldSessionEvents([
      sessionCreated(1),
      hypothesisProposed(2, 1),
      hypothesisStatusChanged(3, 1, "supported"),
    ]);
    expect(() => reduceSession(supported, hypothesisStatusChanged(4, 1, "supported"))).toThrow(
      /cannot become/,
    );
    const falsified = reduceSession(supported, hypothesisStatusChanged(4, 1, "falsified"));
    expect(falsified.hypotheses.get(asHypothesisId("hyp-1"))?.status).toBe("falsified");
  });
});

describe("plan law", () => {
  test("a new PlanSet supersedes the previous active plan", () => {
    const state = foldSessionEvents([
      sessionCreated(1),
      hypothesisProposed(2, 1),
      planSet(3, 1),
      planSet(4, 2, { nextAction: "search the archive" }),
    ]);
    expect(state.plans.get(asPlanId("plan-1"))?.status).toBe("superseded");
    expect(state.activePlan?.planId).toEqual(asPlanId("plan-2"));
    expect(state.activePlan?.status).toBe("active");
    expect(state.plans.size).toBe(2);
  });

  test("invalidation marks the active plan terminal and clears activePlan", () => {
    const state = foldSessionEvents([
      sessionCreated(1),
      planSet(2, 1),
      planInvalidated(3, 1, "the ledger contradicts the plan"),
    ]);
    expect(state.plans.get(asPlanId("plan-1"))?.status).toBe("invalidated");
    expect(state.activePlan).toBeUndefined();
    // A superseded or invalidated plan cannot be invalidated again.
    expect(() => reduceSession(state, planInvalidated(4, 1))).toThrow(
      /requires plan status active/,
    );
  });

  test("a plan referencing an unknown hypothesis is rejected", () => {
    const state = foldSessionEvents([sessionCreated(1)]);
    expect(() => reduceSession(state, planSet(2, 1, { hypothesis: 9 }))).toThrow(
      /unknown hypothesis/,
    );
  });
});

describe("challenge law", () => {
  test("hypothesis and plan targets are registry-validated; completion and policy stay free-form", () => {
    const state = foldSessionEvents([sessionCreated(1), planSet(2, 1)]);
    expect(() => reduceSession(state, challengeRaised(3, 1, { targetType: "hypothesis" }))).toThrow(
      /unknown hypothesis target/,
    );
    expect(() => reduceSession(state, challengeRaised(3, 1, { target: "plan-9" }))).toThrow(
      /unknown plan target/,
    );
    const free = reduceSession(
      state,
      challengeRaised(3, 1, { targetType: "completion", target: "final-answer" }),
    );
    expect(free.openChallenges).toHaveLength(1);
    const policy = reduceSession(
      free,
      challengeRaised(4, 2, { targetType: "policy", target: "read-only boundary" }),
    );
    expect(policy.openChallenges).toHaveLength(2);
  });

  test("raised challenges are open until resolved, and resolution removes them", () => {
    const state = foldSessionEvents([sessionCreated(1), planSet(2, 1), challengeRaised(3, 1)]);
    expect(state.openChallenges[0]?.status).toBe("open");
    const resolved = reduceSession(state, challengeResolved(4, 1, "accepted", "the plan is wrong"));
    expect(resolved.challenges.get(asChallengeId("challenge-1"))?.status).toBe("accepted");
    expect(resolved.openChallenges).toHaveLength(0);
    expect(() => reduceSession(resolved, challengeResolved(5, 1))).toThrow(
      /requires challenge status open/,
    );
  });

  test("an open completion-target challenge blocks SessionCompleted; any outcome resolves the block", () => {
    const blocked = foldSessionEvents([
      sessionCreated(1),
      challengeRaised(2, 1, { targetType: "completion" }),
    ]);
    expect(() => reduceSession(blocked, sessionCompleted(3))).toThrow(
      /open completion-target challenge\(s\) must be resolved first: challenge-1/,
    );

    // Resolution with any recorded outcome (here: the challenge was wrong)
    // removes the block and completion becomes legal.
    const resolved = foldSessionEvents([
      sessionCreated(1),
      challengeRaised(2, 1, { targetType: "completion" }),
      challengeResolved(3, 1, "rejected", "the verification already passed"),
      sessionCompleted(4),
    ]);
    expect(resolved.status).toBe("COMPLETED");
  });

  test("non-completion targets never block completion on their own", () => {
    const state = foldSessionEvents([
      sessionCreated(1),
      planSet(2, 1),
      challengeRaised(3, 1),
      challengeRaised(4, 2, { targetType: "policy", target: "read-only boundary" }),
    ]);
    expect(state.openChallenges).toHaveLength(2);
    const completed = reduceSession(state, sessionCompleted(5));
    expect(completed.status).toBe("COMPLETED");
  });

  test("multiple completion-target challenges all listed; resolving one still blocks", () => {
    const two = foldSessionEvents([
      sessionCreated(1),
      challengeRaised(2, 1, { targetType: "completion" }),
      challengeRaised(3, 2, { targetType: "completion" }),
    ]);
    expect(() => reduceSession(two, sessionCompleted(4))).toThrow(/challenge-1, challenge-2/);

    const oneLeft = foldSessionEvents([
      sessionCreated(1),
      challengeRaised(2, 1, { targetType: "completion" }),
      challengeRaised(3, 2, { targetType: "completion" }),
      challengeResolved(4, 1, "resolved", "addressed by replanning"),
    ]);
    expect(() => reduceSession(oneLeft, sessionCompleted(5))).toThrow(/challenge-2/);
  });
});

describe("verification law", () => {
  test("latest-wins and inconclusive is never coerced", () => {
    const state = foldSessionEvents([
      sessionCreated(1),
      verificationRecorded(2, { outcome: "passed", summary: "postcondition holds" }),
      verificationRecorded(3, { outcome: "inconclusive", summary: "checker unreachable" }),
    ]);
    expect(state.lastVerification?.outcome).toBe("inconclusive");
    expect(state.lastVerification?.summary).toBe("checker unreachable");
    const failed = reduceSession(
      state,
      verificationRecorded(4, { outcome: "failed", summary: "postcondition violated" }),
    );
    expect(failed.lastVerification?.outcome).toBe("failed");
  });
});

describe("goal law", () => {
  test("GoalSet replaces the goal latest-wins", () => {
    const state: DerivedSessionState = foldSessionEvents([
      sessionCreated(1),
      goalSet(2, { goal: "first goal" }),
      goalSet(3, { goal: "second goal", constraints: ["no writes", "no network"] }),
    ]);
    expect(state.goal?.goal).toBe("second goal");
    expect(state.goal?.constraints).toHaveLength(2);
  });
});
