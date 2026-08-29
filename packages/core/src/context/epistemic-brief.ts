import type { DerivedSessionState } from "../state/reducer";
import type { ContextBudget } from "./budget";

/**
 * Structured epistemic projection (docs/02 sections 12.1-12.3, ADR-0012).
 * Pure renderer over DerivedSessionState: same state and budget always
 * produce the same brief. No clock, randomness, environment reads, or I/O.
 *
 * Composition order (section 12.2 priority): goal + hard constraints, active
 * plan, open challenges, pending INDETERMINATE executions, latest
 * verification, active hypotheses, then observations capped at
 * maxActiveObservations (oldest dropped first — the cap bounds the working
 * set, never the event log). Every rendered line passes the per-fragment
 * byte cap so one pathological claim cannot evict a later section.
 *
 * Returns undefined when there is nothing epistemic to say: sessions without
 * goal/plan/challenge/verification/hypothesis/observation facts and without
 * pending indeterminates build contexts byte-identical to the pre-M4
 * projection.
 */

/** Marker appended in place of cut bytes; mirrors builder.ts truncation. */
const TRUNCATION_RESERVE_BYTES = 40;

const TEXT_ENCODER = new TextEncoder();

function utf8Bytes(text: string): number {
  return TEXT_ENCODER.encode(text).length;
}

function cutToBytes(text: string, limitBytes: number): string {
  let kept = "";
  let bytes = 0;
  for (const char of text) {
    const charBytes = utf8Bytes(char);
    if (bytes + charBytes > limitBytes) {
      break;
    }
    kept += char;
    bytes += charBytes;
  }
  return kept;
}

/** Cap a single line at maxFragmentBytes, marking what was cut. */
function fitLine(text: string, maxFragmentBytes: number): string {
  const bytes = utf8Bytes(text);
  if (bytes <= maxFragmentBytes) {
    return text;
  }
  const kept = cutToBytes(text, maxFragmentBytes - TRUNCATION_RESERVE_BYTES);
  const cutBytes = bytes - utf8Bytes(kept);
  return `${kept}…[+${cutBytes} bytes truncated]`;
}

function pendingIndeterminates(state: DerivedSessionState): {
  readonly toolExecutionId: string;
  readonly name: string;
  readonly reason: string | undefined;
}[] {
  return [...state.toolExecutions.values()]
    .filter((snapshot) => snapshot.status === "INDETERMINATE")
    .map((snapshot) => ({
      toolExecutionId: snapshot.toolExecutionId.valueOf(),
      name: snapshot.name,
      reason: snapshot.indeterminateReason,
    }));
}

/**
 * Render the structured epistemic brief, or undefined when the epistemic
 * slice and pending indeterminates are all empty.
 */
export function projectEpistemicBrief(
  state: DerivedSessionState,
  budget: ContextBudget,
): string | undefined {
  const sections: string[] = [];
  const line = (text: string): void => {
    sections.push(fitLine(text, budget.maxFragmentBytes));
  };

  const goal = state.goal;
  if (goal !== undefined) {
    line(`## Goal`);
    if (goal.need !== undefined) {
      line(`Need: ${goal.need}`);
    }
    line(`Goal: ${goal.goal}`);
    if (goal.strategy !== undefined) {
      line(`Strategy: ${goal.strategy}`);
    }
    if (goal.mission !== undefined) {
      line(`Mission: ${goal.mission}`);
    }
    for (const constraint of goal.constraints) {
      line(`Hard constraint: ${constraint.description}`);
    }
  }

  const plan = state.activePlan;
  if (plan !== undefined) {
    line(`## Active plan`);
    line(`Next action: ${plan.nextAction}`);
    if (plan.focus !== undefined) {
      line(`Focus: ${plan.focus}`);
    }
    if (plan.hypothesisId !== undefined) {
      line(`Working hypothesis: ${plan.hypothesisId.valueOf()}`);
    }
    if (plan.falsifiedIf !== undefined) {
      line(`Falsified if: ${plan.falsifiedIf}`);
    }
  }

  for (const challenge of state.openChallenges) {
    line(`## Open challenge`);
    line(`Target: ${challenge.targetType} ${challenge.targetId.valueOf()}`);
    line(`Claim: ${challenge.claim}`);
  }

  for (const pending of pendingIndeterminates(state)) {
    line(`## Pending indeterminate action`);
    line(`Execution: ${pending.toolExecutionId} (${pending.name})`);
    if (pending.reason !== undefined) {
      line(`Reason: ${pending.reason}`);
    }
  }

  const verification = state.lastVerification;
  if (verification !== undefined) {
    line(`## Latest verification`);
    line(`Outcome: ${verification.outcome}`);
    line(`Summary: ${verification.summary}`);
  }

  const activeHypotheses = [...state.hypotheses.values()].filter(
    (hypothesis) => hypothesis.status === "proposed" || hypothesis.status === "supported",
  );
  if (activeHypotheses.length > 0) {
    line(`## Active hypotheses`);
    for (const hypothesis of activeHypotheses) {
      line(`- [${hypothesis.status}] ${hypothesis.statement}`);
    }
  }

  // Insertion order is append order; keep the newest N observations.
  const observations = [...state.observations.values()].slice(-budget.maxActiveObservations);
  if (observations.length > 0) {
    line(`## Observations (latest ${observations.length})`);
    for (const observation of observations) {
      line(`- ${observation.claim}`);
    }
  }

  if (sections.length === 0) {
    return undefined;
  }
  return sections.join("\n");
}
