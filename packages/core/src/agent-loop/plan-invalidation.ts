import type { HypothesisStatus, PlanId } from "@praxis/contracts";
import type { DerivedSessionState } from "../state/reducer";
import { foldSessionEvents } from "../state/reducer";
import { appendEvent, type EventAppenderDeps, eventEnvelope } from "./append-event";

/**
 * Falsifiable-plan orchestration (docs/02 sections 5.3-5.4 and 14; ADR-0012
 * reserved this decision for the runtime): the reducer records falsification
 * as a fact and never auto-invalidates — this pass makes the invalidation
 * decision deterministically. An active plan whose hypothesis died (falsified
 * or superseded) is closed with one PlanInvalidated fact per plan, in
 * registry insertion order, citing the hypothesis id and status so the
 * durable fact explains itself in replay. The model is never consulted: the
 * next plan arrives as its own PlanSet. Idempotent by construction — rerunning
 * over an already-invalidated stream matches nothing.
 */

export type PlanInvalidationReport = {
  /** Plans this pass closed, in append order. */
  readonly invalidated: ReadonlyArray<{ readonly planId: PlanId }>;
  /**
   * Active plans whose hypothesis is still alive after the pass — the
   * working set the model may legitimately keep following.
   */
  readonly active: ReadonlyArray<{ readonly planId: PlanId }>;
};

const DEAD_HYPOTHESIS_STATUSES: readonly HypothesisStatus[] = ["falsified", "superseded"];

function isDeadHypothesis(status: HypothesisStatus): boolean {
  return DEAD_HYPOTHESIS_STATUSES.includes(status);
}

export async function invalidatePlansFalsifiedByHypotheses(
  deps: EventAppenderDeps,
): Promise<PlanInvalidationReport> {
  const state: DerivedSessionState = foldSessionEvents(await deps.store.readStream(deps.sessionId));

  const invalidated: Array<{ readonly planId: PlanId }> = [];
  for (const plan of state.plans.values()) {
    if (plan.status !== "active" || plan.hypothesisId === undefined) {
      continue;
    }
    const hypothesis = state.hypotheses.get(plan.hypothesisId);
    if (hypothesis === undefined || !isDeadHypothesis(hypothesis.status)) {
      continue;
    }
    await appendEvent(deps, {
      ...eventEnvelope(deps),
      type: "PlanInvalidated",
      payload: {
        planId: plan.planId,
        reason: `hypothesis ${hypothesis.hypothesisId.valueOf()} is ${hypothesis.status}; plan invalidated by runtime`,
      },
    });
    invalidated.push({ planId: plan.planId });
  }

  const after = foldSessionEvents(await deps.store.readStream(deps.sessionId));
  const active = [...after.plans.values()]
    .filter((plan) => plan.status === "active")
    .map((plan) => ({ planId: plan.planId }));
  return { invalidated, active };
}
