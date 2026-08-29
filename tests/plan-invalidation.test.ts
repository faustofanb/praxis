import type { EventId } from "@praxis/contracts";
import { asEventId } from "@praxis/contracts";
import { foldSessionEvents, invalidatePlansFalsifiedByHypotheses } from "@praxis/core";
import { describe, expect, test } from "vitest";
import { inMemoryEventStore } from "./helpers/in-memory-event-store";
import {
  hypothesisProposed,
  hypothesisStatusChanged,
  observationRecorded,
  planInvalidated,
  planSet,
  sessionCreated,
  TEST_SESSION_ID,
} from "./helpers/session-events";

/**
 * Falsifiable-plan orchestration (docs/02 sections 5.3-5.4, ADR-0012):
 * the reducer records falsification as a fact; this pass makes the
 * invalidation decision — deterministically, idempotently, never consulting
 * the model.
 */

function deps() {
  let n = 0;
  return {
    store: inMemoryEventStore(),
    sessionId: TEST_SESSION_ID,
    now: () => 2_000,
    newEventId: (): EventId => {
      n += 1;
      return asEventId(`pass-event-${n}`);
    },
  };
}

describe("invalidatePlansFalsifiedByHypotheses", () => {
  test("invalidates an active plan whose hypothesis was falsified, with a self-explaining reason", async () => {
    const harness = deps();
    await harness.store.append(
      [
        sessionCreated(1),
        hypothesisProposed(2, 1),
        observationRecorded(3, 1),
        hypothesisStatusChanged(4, 1, "falsified", { evidence: [3] }),
        planSet(5, 1, { hypothesis: 1 }),
      ],
      0,
    );

    // Fact law holds before the pass: the plan is still active.
    const before = foldSessionEvents(await harness.store.readStream(harness.sessionId));
    expect(before.activePlan?.planId.valueOf()).toBe("plan-1");

    const report = await invalidatePlansFalsifiedByHypotheses(harness);
    expect(report.invalidated).toEqual([{ planId: expect.objectContaining({}) }]);
    expect(report.invalidated.map((entry) => entry.planId.valueOf())).toEqual(["plan-1"]);
    expect(report.active).toEqual([]);

    const after = foldSessionEvents(await harness.store.readStream(harness.sessionId));
    expect(after.activePlan).toBeUndefined();
    const invalidation = after.plans.get(
      after.plans.keys().next().value ?? ("".toString() as never),
    );
    expect(invalidation?.status).toBe("invalidated");
    const events = await harness.store.readStream(harness.sessionId);
    const appended = events.find((event) => event.type === "PlanInvalidated");
    if (appended?.type !== "PlanInvalidated") {
      throw new Error("expected the pass to append PlanInvalidated");
    }
    expect(appended.payload.reason).toBe(
      "hypothesis hyp-1 is falsified; plan invalidated by runtime",
    );
    expect(appended.actor).toEqual({ kind: "system" });
  });

  test("superseded hypotheses invalidate too; proposed and supported keep the plan active", async () => {
    const supersededHarness = deps();
    await supersededHarness.store.append(
      [
        sessionCreated(1),
        hypothesisProposed(2, 1),
        hypothesisProposed(3, 2),
        hypothesisStatusChanged(4, 2, "superseded"),
        planSet(5, 1, { hypothesis: 2 }),
      ],
      0,
    );
    const superseded = await invalidatePlansFalsifiedByHypotheses(supersededHarness);
    expect(superseded.invalidated.map((entry) => entry.planId.valueOf())).toEqual(["plan-1"]);

    const aliveHarness = deps();
    await aliveHarness.store.append(
      [
        sessionCreated(1),
        hypothesisProposed(2, 1),
        hypothesisProposed(3, 2),
        hypothesisStatusChanged(4, 1, "supported", { evidence: [1] }),
        planSet(5, 1, { hypothesis: 1 }),
      ],
      0,
    );
    const alive = await invalidatePlansFalsifiedByHypotheses(aliveHarness);
    expect(alive.invalidated).toEqual([]);
    expect(alive.active.map((entry) => entry.planId.valueOf())).toEqual(["plan-1"]);
    expect((await aliveHarness.store.readStream(aliveHarness.sessionId)).length).toBe(5);
  });

  test("plans without a hypothesis reference are never touched", async () => {
    const harness = deps();
    await harness.store.append(
      [
        sessionCreated(1),
        hypothesisProposed(2, 1),
        hypothesisStatusChanged(3, 1, "falsified"),
        planSet(4, 1),
      ],
      0,
    );
    const report = await invalidatePlansFalsifiedByHypotheses(harness);
    expect(report.invalidated).toEqual([]);
    expect(report.active.map((entry) => entry.planId.valueOf())).toEqual(["plan-1"]);
  });

  test("multiple dead plans invalidate in insertion order", async () => {
    const harness = deps();
    await harness.store.append(
      [
        sessionCreated(1),
        hypothesisProposed(2, 1),
        hypothesisProposed(3, 2),
        hypothesisStatusChanged(4, 1, "falsified"),
        hypothesisStatusChanged(5, 2, "falsified"),
        planSet(6, 1, { hypothesis: 1 }),
        planSet(7, 2, { hypothesis: 2 }),
      ],
      0,
    );
    // plan-1 was superseded by plan-2 at seq 7; only plan-2 is active.
    const report = await invalidatePlansFalsifiedByHypotheses(harness);
    expect(report.invalidated.map((entry) => entry.planId.valueOf())).toEqual(["plan-2"]);
    const events = await harness.store.readStream(harness.sessionId);
    expect(events.filter((event) => event.type === "PlanInvalidated")).toHaveLength(1);
  });

  test("re-running the pass is a no-op (idempotent)", async () => {
    const harness = deps();
    await harness.store.append(
      [
        sessionCreated(1),
        hypothesisProposed(2, 1),
        hypothesisStatusChanged(3, 1, "falsified"),
        planSet(4, 1, { hypothesis: 1 }),
      ],
      0,
    );
    await invalidatePlansFalsifiedByHypotheses(harness);
    const lengthAfterFirst = (await harness.store.readStream(harness.sessionId)).length;

    const second = await invalidatePlansFalsifiedByHypotheses(harness);
    expect(second.invalidated).toEqual([]);
    expect((await harness.store.readStream(harness.sessionId)).length).toBe(lengthAfterFirst);
  });

  test("replay determinism: the appended invalidation folds identically on replay", async () => {
    const harness = deps();
    await harness.store.append(
      [
        sessionCreated(1),
        hypothesisProposed(2, 1),
        hypothesisStatusChanged(3, 1, "falsified"),
        planSet(4, 1, { hypothesis: 1 }),
      ],
      0,
    );
    await invalidatePlansFalsifiedByHypotheses(harness);

    const stream = await harness.store.readStream(harness.sessionId);
    const first = foldSessionEvents(stream);
    const second = foldSessionEvents(stream);
    expect(first).toEqual(second);
    expect(first.activePlan).toBeUndefined();
    expect(first.plans.get(first.plans.keys().next().value as never)?.status).toBe("invalidated");
  });

  test("an explicit PlanInvalidated before the pass keeps the pass silent", async () => {
    const harness = deps();
    await harness.store.append(
      [
        sessionCreated(1),
        hypothesisProposed(2, 1),
        hypothesisStatusChanged(3, 1, "falsified"),
        planSet(4, 1, { hypothesis: 1 }),
        planInvalidated(5, 1, "the model gave up on it"),
      ],
      0,
    );
    const report = await invalidatePlansFalsifiedByHypotheses(harness);
    expect(report.invalidated).toEqual([]);
    expect(report.active).toEqual([]);
  });
});
