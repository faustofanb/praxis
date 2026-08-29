import type { DerivedSessionState } from "../state/reducer";
import type { ContextBudget } from "./budget";
import { ContextBudgetExceededError } from "./builder";

/**
 * Structured epistemic projection (docs/02 sections 12.1-12.4, ADR-0012).
 * Pure renderer over DerivedSessionState: same state and budget always
 * produce the same brief. No clock, randomness, environment reads, or I/O.
 *
 * Two-tier assembly law (M5-T001): the non-compactable tier (docs/02 section
 * 12.2 — goal + hard constraints, active plan, open challenges, completion
 * block, pending INDETERMINATE executions, latest verification) renders in
 * full and is never evicted for byte pressure; if it alone cannot fit the
 * fragment cap the renderer fails closed. The compactable tier (count-capped
 * active hypotheses, then count-capped observations) evicts whole sections
 * with an honest omission line. Total brief bytes never exceed
 * maxFragmentBytes.
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

/** A compactable brief section: rendered lines evicted as a unit. */
type BriefSection = {
  readonly lines: readonly string[];
};

/**
 * Render the structured epistemic brief, or undefined when the epistemic
 * slice and pending indeterminates are all empty.
 */
export function projectEpistemicBrief(
  state: DerivedSessionState,
  budget: ContextBudget,
): string | undefined {
  const line = (text: string): string => fitLine(text, budget.maxFragmentBytes);

  // Non-compactable tier (docs/02 section 12.2): per-line capped, never
  // evicted to satisfy the fragment cap — overflow fails closed below.
  const fixed: string[] = [];

  const goal = state.goal;
  if (goal !== undefined) {
    fixed.push(line(`## Goal`));
    if (goal.need !== undefined) {
      fixed.push(line(`Need: ${goal.need}`));
    }
    fixed.push(line(`Goal: ${goal.goal}`));
    if (goal.strategy !== undefined) {
      fixed.push(line(`Strategy: ${goal.strategy}`));
    }
    if (goal.mission !== undefined) {
      fixed.push(line(`Mission: ${goal.mission}`));
    }
    for (const constraint of goal.constraints) {
      fixed.push(line(`Hard constraint: ${constraint.description}`));
    }
  }

  const plan = state.activePlan;
  if (plan !== undefined) {
    fixed.push(line(`## Active plan`));
    fixed.push(line(`Next action: ${plan.nextAction}`));
    if (plan.focus !== undefined) {
      fixed.push(line(`Focus: ${plan.focus}`));
    }
    if (plan.hypothesisId !== undefined) {
      fixed.push(line(`Working hypothesis: ${plan.hypothesisId.valueOf()}`));
    }
    if (plan.falsifiedIf !== undefined) {
      fixed.push(line(`Falsified if: ${plan.falsifiedIf}`));
    }
  }

  for (const challenge of state.openChallenges) {
    fixed.push(line(`## Open challenge`));
    fixed.push(line(`Target: ${challenge.targetType} ${challenge.targetId.valueOf()}`));
    fixed.push(line(`Claim: ${challenge.claim}`));
  }

  // The reducer refuses SessionCompleted while a completion-target
  // challenge is open (docs/02 section 14, M4-T004): render the block so
  // the model knows why completion is unavailable and what to resolve.
  const blockingCompletions = state.openChallenges.filter(
    (challenge) => challenge.targetType === "completion",
  );
  if (blockingCompletions.length > 0) {
    fixed.push(line(`## Completion blocked`));
    fixed.push(
      line(
        `Session completion is blocked until ${blockingCompletions.length} completion-target challenge(s) are resolved.`,
      ),
    );
    for (const challenge of blockingCompletions) {
      fixed.push(line(`Challenge: ${challenge.challengeId.valueOf()} — ${challenge.claim}`));
    }
  }

  for (const pending of pendingIndeterminates(state)) {
    fixed.push(line(`## Pending indeterminate action`));
    fixed.push(line(`Execution: ${pending.toolExecutionId} (${pending.name})`));
    if (pending.reason !== undefined) {
      fixed.push(line(`Reason: ${pending.reason}`));
    }
  }

  const verification = state.lastVerification;
  if (verification !== undefined) {
    fixed.push(line(`## Latest verification`));
    fixed.push(line(`Outcome: ${verification.outcome}`));
    fixed.push(line(`Summary: ${verification.summary}`));
  }

  // Compactable tier: count-capped sections, evicted whole under byte
  // pressure. Insertion order is append order; the newest entries win.
  const compactable: BriefSection[] = [];

  const activeHypotheses = [...state.hypotheses.values()].filter(
    (hypothesis) => hypothesis.status === "proposed" || hypothesis.status === "supported",
  );
  if (activeHypotheses.length > 0) {
    const shown = activeHypotheses.slice(-budget.maxActiveHypotheses);
    const hidden = activeHypotheses.length - shown.length;
    const lines = [line(`## Active hypotheses`)];
    for (const hypothesis of shown) {
      lines.push(line(`- [${hypothesis.status}] ${hypothesis.statement}`));
    }
    if (hidden > 0) {
      lines.push(line(`…[+${hidden} older active hypotheses omitted]`));
    }
    compactable.push({ lines });
  }

  const observations = [...state.observations.values()].slice(-budget.maxActiveObservations);
  if (observations.length > 0) {
    const lines = [line(`## Observations (latest ${observations.length})`)];
    for (const observation of observations) {
      lines.push(line(`- ${observation.claim}`));
    }
    compactable.push({ lines });
  }

  if (fixed.length === 0 && compactable.length === 0) {
    return undefined;
  }

  const cap = budget.maxFragmentBytes;
  const fixedBytes = utf8Bytes(fixed.join("\n"));
  // The reserve guarantees an honest omission line always fits when
  // compactable sections get evicted; the non-compactable tier itself is
  // never evicted — a session whose non-compactable facts cannot fit the
  // cap fails closed instead of silently hiding governance state.
  if (fixedBytes > cap - TRUNCATION_RESERVE_BYTES) {
    throw new ContextBudgetExceededError(
      `non-compactable brief sections alone reach ${fixedBytes} bytes against the fragment cap of ${cap}; refusing to evict structured non-compactable state`,
    );
  }

  const body = [...fixed];
  let omittedLines = 0;
  for (const section of compactable) {
    const candidate = [...body, ...section.lines].join("\n");
    if (utf8Bytes(candidate) + TRUNCATION_RESERVE_BYTES <= cap) {
      body.push(...section.lines);
    } else {
      omittedLines += section.lines.length;
    }
  }
  if (omittedLines > 0) {
    body.push(`…[+${omittedLines} brief lines omitted]`);
  }
  return body.join("\n");
}
