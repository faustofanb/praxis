import type { SessionEventUnion } from "@praxis/contracts";
import { SessionEventUnionSchema } from "@praxis/contracts";
import {
  foldSessionEvents,
  IllegalTransitionError,
  initialSessionState,
  reduceSession,
} from "@praxis/core";
import fc from "fast-check";
import { describe, expect, test } from "vitest";
import {
  projectDerivedState,
  projectMachine,
  sessionPlanArbitrary,
  translateSessionPlan,
} from "../helpers/full-vocabulary-machine";
import { hypothesisStatusChanged, toolReconciled } from "../helpers/session-events";

/**
 * State-machine hardening over the FULL v1 vocabulary (docs/03 M7 row
 * "fast-check state machine suite"). Where reducer.property.test.ts pins the
 * session/turn shell, this suite drives an independent shadow model of the
 * documented transition tables (tests/helpers/full-vocabulary-machine.ts)
 * through the tool lifecycle, the model-request machine, and the epistemic
 * machines — and pins the algebra the store relies on: legal streams fold to
 * the model's projection, precondition violations never fold, terminals are
 * absorbing, and folding is resume-invariant.
 */

const plans = sessionPlanArbitrary;

describe("full-vocabulary state machine", () => {
  test("the reducer agrees with the independent model on every projected field", () => {
    fc.assert(
      fc.property(plans, (commands) => {
        const { events, machine } = translateSessionPlan(commands);
        expect(events[0]?.type).toBe("SessionCreated");
        const state = foldSessionEvents(events);
        expect(projectDerivedState(state)).toEqual(projectMachine(machine));
      }),
      { numRuns: 200 },
    );
  });

  test("every machine-emitted event is schema-valid", () => {
    fc.assert(
      fc.property(plans, (commands) => {
        const { events } = translateSessionPlan(commands);
        for (const event of events) {
          expect(SessionEventUnionSchema.parse(event)).toEqual(event);
        }
      }),
    );
  });

  test("structural invariants hold at every prefix", () => {
    fc.assert(
      fc.property(plans, (commands) => {
        const { events } = translateSessionPlan(commands);
        let state = initialSessionState();
        events.forEach((event, index) => {
          state = reduceSession(state, event);
          expect(state.headSeq).toBe(index + 1);
          expect(state.status).not.toBe("EMPTY");
          // The open-challenge view is exactly the challenges still open
          // (held in raise order; compare as sorted id sets).
          const openIds = [...state.challenges.entries()]
            .filter(([, challenge]) => challenge.status === "open")
            .map(([id]) => id.valueOf())
            .sort();
          expect(
            [...state.openChallenges.map((challenge) => challenge.challengeId.valueOf())].sort(),
          ).toEqual(openIds);
          // At most one plan is ever active, and activePlan is it.
          const activePlans = [...state.plans.entries()].filter(
            ([, plan]) => plan.status === "active",
          );
          expect(activePlans.length).toBe(state.activePlan === undefined ? 0 : 1);
          if (state.activePlan !== undefined) {
            expect(activePlans[0]?.[0].valueOf()).toBe(state.activePlan.planId.valueOf());
          }
          // An open turn is always one of the registered turns.
          if (state.currentTurnId !== undefined) {
            expect(state.turnIds.has(state.currentTurnId)).toBe(true);
          }
        });
      }),
    );
  });

  test("folding is resume-invariant at every split point", () => {
    fc.assert(
      fc.property(plans, fc.nat(), (commands, splitIndex) => {
        const { events } = translateSessionPlan(commands);
        const split = splitIndex % (events.length + 1);
        const full = foldSessionEvents(events);
        let resumed = foldSessionEvents(events.slice(0, split));
        for (const event of events.slice(split)) {
          resumed = reduceSession(resumed, event);
        }
        expect(resumed).toEqual(full);
      }),
      { numRuns: 200 },
    );
  });

  test("a precondition-violating append is always rejected", () => {
    fc.assert(
      fc.property(plans, fc.nat(), (commands, pick) => {
        const { events, machine } = translateSessionPlan(commands);
        const candidates = machine.illegalEventCandidates(events.length + 1);
        expect(candidates.length).toBeGreaterThan(0);
        const evil: SessionEventUnion | undefined = candidates[pick % candidates.length];
        if (evil === undefined) {
          throw new Error("candidate list unexpectedly empty at index");
        }
        expect(() => foldSessionEvents([...events, evil])).toThrow(IllegalTransitionError);
      }),
      { numRuns: 200 },
    );
  });

  test("terminal statuses are absorbing under every vocabulary move", () => {
    fc.assert(
      fc.property(plans, (commands) => {
        const { events, machine } = translateSessionPlan(commands);
        const seq = events.length + 1;
        for (const [hypothesis, status] of machine.hypotheses) {
          if (status !== "falsified" && status !== "superseded") {
            continue;
          }
          for (const to of ["supported", "falsified", "superseded"] as const) {
            expect(() =>
              foldSessionEvents([...events, hypothesisStatusChanged(seq, hypothesis, to)]),
            ).toThrow(IllegalTransitionError);
          }
        }
        for (const [execution, tool] of machine.tools) {
          if (tool.status === "INDETERMINATE") {
            continue;
          }
          // Only INDETERMINATE may settle: every terminal (and every
          // pre-execution status) rejects reconciliation.
          expect(() =>
            foldSessionEvents([...events, toolReconciled(seq, execution, "succeeded")]),
          ).toThrow(IllegalTransitionError);
        }
      }),
    );
  });
});
