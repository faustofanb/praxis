import type {
  ChallengeOutcome,
  ChallengeTargetType,
  HypothesisStatus,
  HypothesisStatusChange,
  SessionEventUnion,
  ToolEffect,
  ToolExecutionStatus,
  VerificationOutcome,
} from "@praxis/contracts";
import { TOOL_EFFECTS } from "@praxis/contracts";
import type { DerivedSessionState, SessionStatus } from "@praxis/core";
import fc from "fast-check";
import {
  challengeRaised,
  challengeResolved,
  goalSet,
  hypothesisProposed,
  hypothesisStatusChanged,
  modelRequestFailed,
  modelRequestStarted,
  modelResponseCompleted,
  observationRecorded,
  planInvalidated,
  planSet,
  sessionCompleted,
  sessionCreated,
  sessionPaused,
  sessionResumed,
  toolAuthorized,
  toolFailed,
  toolIndeterminate,
  toolProposed,
  toolReconciled,
  toolRejected,
  toolStarted,
  toolSucceeded,
  turnCompleted,
  turnStarted,
  verificationRecorded,
} from "./session-events";

/**
 * Independent shadow model of the documented v1 transition tables (docs/02
 * sections 7, 8.2, 13-14, 16), covering the FULL event vocabulary — the
 * session/turn-level random-session-streams.ts helper stays untouched for
 * its existing consumers. Commands are intents filtered through this model,
 * so every surviving stream must fold cleanly through the real reducer.
 * The model is written from the documented tables, not from the reducer's
 * code; a disagreement between the two is exactly what the property suite
 * exists to catch.
 *
 * Numeric ids are deliberately bounded (0..4) so id collisions — a documented
 * rejection class — are exercised, not avoided. Ids >= 90 never appear in
 * legal streams and are reserved for unknown-reference probes.
 */

const ID_SPACE = 5;
const UNKNOWN_ID = 90;

/** docs/02 hypothesis transition table; empty means terminal (absorbing). */
const HYPOTHESIS_CHANGES: Readonly<Record<HypothesisStatus, readonly HypothesisStatusChange[]>> = {
  proposed: ["supported", "falsified", "superseded"],
  supported: ["falsified", "superseded"],
  falsified: [],
  superseded: [],
};

const ACTIVE_TOOL_STATUSES: readonly ToolExecutionStatus[] = [
  "PROPOSED",
  "AUTHORIZED",
  "EXECUTING",
];

export type FullVocabularyCommand =
  | { kind: "startTurn"; turn: number }
  | { kind: "completeTurn" }
  | { kind: "pause" }
  | { kind: "resume" }
  | { kind: "completeSession" }
  | { kind: "proposeTool"; execution: number; effect: ToolEffect }
  | { kind: "authorizeTool"; execution: number }
  | { kind: "rejectTool"; execution: number }
  | { kind: "startTool"; execution: number }
  | { kind: "succeedTool"; execution: number }
  | { kind: "failTool"; execution: number }
  | { kind: "indeterminateTool"; execution: number }
  | { kind: "reconcileTool"; execution: number; outcome: "succeeded" | "failed" | "indeterminate" }
  | { kind: "startModel" }
  | { kind: "completeModel" }
  | { kind: "failModel" }
  | { kind: "setGoal"; goal: string }
  | { kind: "recordObservation"; observation: number }
  | { kind: "proposeHypothesis"; hypothesis: number }
  | { kind: "changeHypothesis"; hypothesis: number; to: HypothesisStatusChange }
  | { kind: "setPlan"; plan: number; hypothesis?: number }
  | { kind: "invalidatePlan"; plan: number }
  | {
      kind: "raiseChallenge";
      challenge: number;
      targetType: ChallengeTargetType;
      target: number;
    }
  | { kind: "resolveChallenge"; challenge: number; outcome: ChallengeOutcome }
  | { kind: "recordVerification"; outcome: VerificationOutcome };

const epistemicId = fc.integer({ min: 0, max: ID_SPACE - 1 });
// Tiny tool-id space densifies propose→authorize→start→terminal chains; the
// wider turn-id space keeps turn blocks from starving on id exhaustion.
const toolId = fc.integer({ min: 0, max: 3 });
const turnId = fc.integer({ min: 0, max: 9 });

/** In-turn intents: the tool-execution and model-request machines. */
const inTurnCommandArbitrary: fc.Arbitrary<FullVocabularyCommand> = fc.oneof(
  {
    weight: 3,
    arbitrary: fc.record({
      kind: fc.constant("proposeTool"),
      execution: toolId,
      effect: fc.constantFrom(...TOOL_EFFECTS),
    }),
  },
  { weight: 3, arbitrary: fc.record({ kind: fc.constant("authorizeTool"), execution: toolId }) },
  { weight: 1, arbitrary: fc.record({ kind: fc.constant("rejectTool"), execution: toolId }) },
  { weight: 3, arbitrary: fc.record({ kind: fc.constant("startTool"), execution: toolId }) },
  { weight: 3, arbitrary: fc.record({ kind: fc.constant("succeedTool"), execution: toolId }) },
  { weight: 2, arbitrary: fc.record({ kind: fc.constant("failTool"), execution: toolId }) },
  {
    weight: 2,
    arbitrary: fc.record({ kind: fc.constant("indeterminateTool"), execution: toolId }),
  },
  {
    weight: 3,
    arbitrary: fc.record({
      kind: fc.constant("reconcileTool"),
      execution: toolId,
      outcome: fc.constantFrom("succeeded", "failed", "indeterminate" as const),
    }),
  },
  { weight: 3, arbitrary: fc.constant({ kind: "startModel" } as const) },
  { weight: 3, arbitrary: fc.constant({ kind: "completeModel" } as const) },
  { weight: 2, arbitrary: fc.constant({ kind: "failModel" } as const) },
);

/** Session-level intents: the epistemic machines. */
const epistemicCommandArbitrary: fc.Arbitrary<FullVocabularyCommand> = fc.oneof(
  {
    weight: 1,
    arbitrary: fc.record({
      kind: fc.constant("setGoal"),
      goal: fc.string({ minLength: 1, maxLength: 20 }),
    }),
  },
  {
    weight: 2,
    arbitrary: fc.record({ kind: fc.constant("recordObservation"), observation: epistemicId }),
  },
  {
    weight: 3,
    arbitrary: fc.record({ kind: fc.constant("proposeHypothesis"), hypothesis: epistemicId }),
  },
  {
    weight: 3,
    arbitrary: fc.record({
      kind: fc.constant("changeHypothesis"),
      hypothesis: epistemicId,
      to: fc.constantFrom("supported", "falsified", "superseded" as const),
    }),
  },
  {
    weight: 3,
    arbitrary: fc
      .record({
        kind: fc.constant("setPlan"),
        plan: epistemicId,
        hypothesis: fc.option(epistemicId, { nil: undefined }),
      })
      .map(
        (fields): FullVocabularyCommand =>
          fields.hypothesis === undefined
            ? { kind: "setPlan", plan: fields.plan }
            : { kind: "setPlan", plan: fields.plan, hypothesis: fields.hypothesis },
      ),
  },
  { weight: 2, arbitrary: fc.record({ kind: fc.constant("invalidatePlan"), plan: epistemicId }) },
  {
    weight: 3,
    arbitrary: fc.record({
      kind: fc.constant("raiseChallenge"),
      challenge: epistemicId,
      targetType: fc.constantFrom("hypothesis", "plan", "completion", "policy" as const),
      target: epistemicId,
    }),
  },
  {
    weight: 3,
    arbitrary: fc.record({
      kind: fc.constant("resolveChallenge"),
      challenge: epistemicId,
      outcome: fc.constantFrom("accepted", "rejected", "resolved" as const),
    }),
  },
  {
    weight: 1,
    arbitrary: fc.record({
      kind: fc.constant("recordVerification"),
      outcome: fc.constantFrom("passed", "failed", "inconclusive" as const),
    }),
  },
);

const turnStepArbitrary: fc.Arbitrary<FullVocabularyCommand> = fc.oneof(
  { weight: 2, arbitrary: inTurnCommandArbitrary },
  { weight: 1, arbitrary: epistemicCommandArbitrary },
);

/**
 * A staged session plan instead of a flat command soup: flat uniform commands
 * die early (pause/complete end a stream's useful life long before the tool
 * and epistemic machines get exercised), so the generator shapes structure —
 * turn blocks with random in-turn steps, epistemic interludes, pause/resume
 * passages whose steps are mostly filtered (proving the filter), and an
 * optional terminal completion. All content stays random and the machine
 * still filters every command; the shape only guarantees depth.
 */
type SessionPlanBlock =
  | { kind: "turn"; turn: number; steps: readonly FullVocabularyCommand[] }
  | { kind: "epistemic"; steps: readonly FullVocabularyCommand[] }
  | { kind: "pauseResume"; steps: readonly FullVocabularyCommand[] };

export type SessionPlan = {
  blocks: readonly SessionPlanBlock[];
  finish: boolean;
};

const turnBlockArbitrary: fc.Arbitrary<SessionPlanBlock> = fc.record({
  kind: fc.constant("turn"),
  turn: turnId,
  steps: fc.array(turnStepArbitrary, { maxLength: 14 }),
});

const interludeBlockArbitrary: fc.Arbitrary<SessionPlanBlock> = fc.oneof(
  {
    weight: 2,
    arbitrary: fc.record({
      kind: fc.constant("epistemic"),
      steps: fc.array(epistemicCommandArbitrary, { maxLength: 4 }),
    }),
  },
  {
    weight: 1,
    arbitrary: fc.record({
      kind: fc.constant("pauseResume"),
      steps: fc.array(turnStepArbitrary, { maxLength: 3 }),
    }),
  },
);

export const sessionPlanArbitrary: fc.Arbitrary<SessionPlan> = fc.record({
  blocks: fc.array(
    fc.oneof(
      { weight: 3, arbitrary: turnBlockArbitrary },
      { weight: 1, arbitrary: interludeBlockArbitrary },
    ),
    { maxLength: 10 },
  ),
  finish: fc.boolean(),
});

type ShadowStatus = "ACTIVE" | "PAUSED" | "COMPLETED";
type ShadowTool = {
  status: ToolExecutionStatus;
  reconciliations: number;
  hasResult: boolean;
  hasFailure: boolean;
  hasIndeterminate: boolean;
  hasRejection: boolean;
};

export class FullVocabularyMachine {
  status: ShadowStatus = "ACTIVE";
  openTurn: number | null = null;
  readonly usedTurns = new Set<number>();
  pendingModel = false;
  readonly tools = new Map<number, ShadowTool>();
  goal: string | null = null;
  readonly observations = new Set<number>();
  readonly hypotheses = new Map<number, HypothesisStatus>();
  readonly plans = new Map<number, "active" | "superseded" | "invalidated">();
  activePlan: number | null = null;
  readonly challenges = new Map<number, ChallengeOutcome | "open">();
  readonly challengeTargets = new Map<number, ChallengeTargetType>();
  openChallengeOrder: number[] = [];
  lastVerification: VerificationOutcome | null = null;

  /** Returns the durable fact for a legal command, or null (no mutation). */
  apply(command: FullVocabularyCommand, seq: number): SessionEventUnion | null {
    switch (command.kind) {
      case "startTurn":
        if (
          this.status === "ACTIVE" &&
          this.openTurn === null &&
          !this.usedTurns.has(command.turn)
        ) {
          this.openTurn = command.turn;
          this.usedTurns.add(command.turn);
          return turnStarted(seq, command.turn);
        }
        return null;
      case "completeTurn": {
        if (
          this.openTurn === null ||
          [...this.tools.values()].some((tool) => ACTIVE_TOOL_STATUSES.includes(tool.status)) ||
          this.pendingModel
        ) {
          return null;
        }
        const turn = this.openTurn;
        this.openTurn = null;
        return turnCompleted(seq, turn);
      }
      case "pause":
        if (this.status === "ACTIVE" && this.openTurn === null) {
          this.status = "PAUSED";
          return sessionPaused(seq);
        }
        return null;
      case "resume":
        if (this.status === "PAUSED") {
          this.status = "ACTIVE";
          return sessionResumed(seq);
        }
        return null;
      case "completeSession":
        if (
          this.status === "ACTIVE" &&
          this.openTurn === null &&
          !this.openChallengeOrder.some((id) => this.challengeTargets.get(id) === "completion")
        ) {
          this.status = "COMPLETED";
          return sessionCompleted(seq);
        }
        return null;
      case "proposeTool":
        if (
          this.status === "ACTIVE" &&
          this.openTurn !== null &&
          !this.pendingModel &&
          !this.tools.has(command.execution)
        ) {
          this.tools.set(command.execution, {
            status: "PROPOSED",
            reconciliations: 0,
            hasResult: false,
            hasFailure: false,
            hasIndeterminate: false,
            hasRejection: false,
          });
          return toolProposed(seq, command.execution, { effect: command.effect });
        }
        return null;
      case "authorizeTool": {
        const tool = this.tools.get(command.execution);
        if (tool === undefined || tool.status !== "PROPOSED") {
          return null;
        }
        tool.status = "AUTHORIZED";
        return toolAuthorized(seq, command.execution);
      }
      case "rejectTool": {
        const tool = this.tools.get(command.execution);
        if (tool === undefined || (tool.status !== "PROPOSED" && tool.status !== "AUTHORIZED")) {
          return null;
        }
        tool.status = "REJECTED";
        tool.hasRejection = true;
        return toolRejected(seq, command.execution);
      }
      case "startTool": {
        const tool = this.tools.get(command.execution);
        if (tool === undefined || tool.status !== "AUTHORIZED") {
          return null;
        }
        tool.status = "EXECUTING";
        return toolStarted(seq, command.execution);
      }
      case "succeedTool": {
        const tool = this.tools.get(command.execution);
        if (tool === undefined || tool.status !== "EXECUTING") {
          return null;
        }
        tool.status = "SUCCEEDED";
        tool.hasResult = true;
        return toolSucceeded(seq, command.execution);
      }
      case "failTool": {
        const tool = this.tools.get(command.execution);
        if (tool === undefined || tool.status !== "EXECUTING") {
          return null;
        }
        tool.status = "FAILED";
        tool.hasFailure = true;
        return toolFailed(seq, command.execution);
      }
      case "indeterminateTool": {
        const tool = this.tools.get(command.execution);
        if (tool === undefined || tool.status !== "EXECUTING") {
          return null;
        }
        tool.status = "INDETERMINATE";
        tool.hasIndeterminate = true;
        return toolIndeterminate(seq, command.execution);
      }
      case "reconcileTool": {
        const tool = this.tools.get(command.execution);
        if (tool === undefined || tool.status !== "INDETERMINATE") {
          return null;
        }
        tool.reconciliations += 1;
        if (command.outcome === "succeeded") {
          tool.status = "SUCCEEDED";
          tool.hasResult = true;
        } else if (command.outcome === "failed") {
          tool.status = "FAILED";
          tool.hasFailure = true;
        }
        return toolReconciled(seq, command.execution, command.outcome);
      }
      case "startModel":
        if (this.status === "ACTIVE" && this.openTurn !== null && !this.pendingModel) {
          this.pendingModel = true;
          return modelRequestStarted(seq);
        }
        return null;
      case "completeModel":
        if (this.pendingModel) {
          this.pendingModel = false;
          return modelResponseCompleted(seq);
        }
        return null;
      case "failModel":
        if (this.pendingModel) {
          this.pendingModel = false;
          return modelRequestFailed(seq);
        }
        return null;
      case "setGoal":
        if (this.status === "ACTIVE") {
          this.goal = command.goal;
          return goalSet(seq, { goal: command.goal });
        }
        return null;
      case "recordObservation":
        if (this.status === "ACTIVE" && !this.observations.has(command.observation)) {
          this.observations.add(command.observation);
          return observationRecorded(seq, command.observation);
        }
        return null;
      case "proposeHypothesis":
        if (this.status === "ACTIVE" && !this.hypotheses.has(command.hypothesis)) {
          this.hypotheses.set(command.hypothesis, "proposed");
          return hypothesisProposed(seq, command.hypothesis);
        }
        return null;
      case "changeHypothesis": {
        const status = this.hypotheses.get(command.hypothesis);
        if (
          this.status !== "ACTIVE" ||
          status === undefined ||
          !HYPOTHESIS_CHANGES[status].includes(command.to)
        ) {
          return null;
        }
        this.hypotheses.set(command.hypothesis, command.to);
        return hypothesisStatusChanged(seq, command.hypothesis, command.to);
      }
      case "setPlan":
        if (
          this.status === "ACTIVE" &&
          !this.plans.has(command.plan) &&
          (command.hypothesis === undefined || this.hypotheses.has(command.hypothesis))
        ) {
          if (this.activePlan !== null) {
            this.plans.set(this.activePlan, "superseded");
          }
          this.plans.set(command.plan, "active");
          this.activePlan = command.plan;
          return planSet(
            seq,
            command.plan,
            command.hypothesis === undefined ? {} : { hypothesis: command.hypothesis },
          );
        }
        return null;
      case "invalidatePlan":
        if (this.status === "ACTIVE" && this.plans.get(command.plan) === "active") {
          this.plans.set(command.plan, "invalidated");
          this.activePlan = null;
          return planInvalidated(seq, command.plan);
        }
        return null;
      case "raiseChallenge": {
        const targetExists =
          command.targetType === "hypothesis"
            ? this.hypotheses.has(command.target)
            : command.targetType === "plan"
              ? this.plans.has(command.target)
              : true;
        if (this.status !== "ACTIVE" || this.challenges.has(command.challenge) || !targetExists) {
          return null;
        }
        this.challenges.set(command.challenge, "open");
        this.challengeTargets.set(command.challenge, command.targetType);
        this.openChallengeOrder.push(command.challenge);
        const prefix =
          command.targetType === "hypothesis"
            ? "hyp"
            : command.targetType === "plan"
              ? "plan"
              : null;
        return challengeRaised(seq, command.challenge, {
          targetType: command.targetType,
          ...(prefix === null ? {} : { target: `${prefix}-${command.target}` }),
        });
      }
      case "resolveChallenge":
        if (this.status === "ACTIVE" && this.challenges.get(command.challenge) === "open") {
          this.challenges.set(command.challenge, command.outcome);
          this.openChallengeOrder = this.openChallengeOrder.filter(
            (id) => id !== command.challenge,
          );
          return challengeResolved(seq, command.challenge, command.outcome);
        }
        return null;
      case "recordVerification":
        if (this.status === "ACTIVE") {
          this.lastVerification = command.outcome;
          return verificationRecorded(seq, { outcome: command.outcome });
        }
        return null;
    }
  }

  /**
   * Schema-valid events that each violate a documented precondition at the
   * CURRENT state — the real reducer must reject every one of them with
   * IllegalTransitionError. Built from this model's view only.
   */
  illegalEventCandidates(seq: number): SessionEventUnion[] {
    const candidates: SessionEventUnion[] = [
      // Unknown-id references: always applicable.
      toolSucceeded(seq, UNKNOWN_ID),
      planInvalidated(seq, UNKNOWN_ID),
      challengeResolved(seq, UNKNOWN_ID, "rejected"),
      hypothesisStatusChanged(seq, UNKNOWN_ID, "supported"),
    ];

    if (this.status !== "PAUSED") {
      // Resume requires PAUSED (ACTIVE and COMPLETED both reject it).
      candidates.push(sessionResumed(seq));
    }
    if (this.openTurn !== null && this.status === "ACTIVE") {
      // Pause/complete demand no open turn; a second concurrent turn is illegal.
      candidates.push(sessionPaused(seq));
      candidates.push(sessionCompleted(seq));
      candidates.push(turnStarted(seq, this.firstUnusedTurn()));
    } else if (
      this.status === "ACTIVE" &&
      this.openChallengeOrder.some((id) => this.challengeTargets.get(id) === "completion")
    ) {
      // Section 14: an open completion-target challenge blocks completion.
      candidates.push(sessionCompleted(seq));
    }
    if (this.pendingModel) {
      // Only one model request may be pending at a time.
      candidates.push(modelRequestStarted(seq));
    }
    if (this.status !== "ACTIVE") {
      // Every epistemic event requires a live session.
      candidates.push(goalSet(seq, { goal: "dead-session goal" }));
    }
    if (this.status === "ACTIVE" && this.openTurn !== null && !this.pendingModel) {
      for (const execution of this.tools.keys()) {
        // Duplicate tool-execution id.
        candidates.push(toolProposed(seq, execution));
      }
    }
    for (const [execution, tool] of this.tools) {
      if (tool.status !== "PROPOSED") {
        // Authorization requires PROPOSED; reconciliation requires INDETERMINATE
        // (terminal and pre-execution statuses are both absorbing here).
        candidates.push(toolAuthorized(seq, execution));
        candidates.push(toolReconciled(seq, execution, "succeeded"));
      }
    }
    for (const hypothesis of this.hypotheses.keys()) {
      if (this.status === "ACTIVE") {
        // Duplicate hypothesis id.
        candidates.push(hypothesisProposed(seq, hypothesis));
      }
      const status = this.hypotheses.get(hypothesis);
      if (status === "falsified" || status === "superseded") {
        // Terminal statuses are absorbing.
        candidates.push(hypothesisStatusChanged(seq, hypothesis, "supported"));
        candidates.push(hypothesisStatusChanged(seq, hypothesis, "falsified"));
        candidates.push(hypothesisStatusChanged(seq, hypothesis, "superseded"));
      }
    }
    if (this.status === "ACTIVE") {
      for (const observation of this.observations) {
        // Duplicate observation id.
        candidates.push(observationRecorded(seq, observation));
      }
      for (const plan of this.plans.keys()) {
        // Duplicate plan id.
        candidates.push(planSet(seq, plan));
      }
      for (const challenge of this.challenges.keys()) {
        // Duplicate challenge id (policy target needs no existence).
        candidates.push(
          challengeRaised(seq, challenge, { targetType: "policy", target: "any policy" }),
        );
      }
    }
    return candidates;
  }

  private firstUnusedTurn(): number {
    let candidate = 0;
    while (this.usedTurns.has(candidate)) {
      candidate += 1;
    }
    return candidate;
  }
}

export type FullVocabularyStream = {
  readonly events: readonly SessionEventUnion[];
  readonly machine: FullVocabularyMachine;
};

/**
 * Deterministic settling choices for the turn drain, rotated per use so
 * different legal settlement paths (reject, fail, indeterminate-then-
 * reconcile across all three outcomes, model failure vs completion) are
 * spread over the streams' turns without extra randomness.
 */
class DrainChooser {
  private uses = 0;

  constructor(private readonly seed: number) {}

  pick(modulo: number): number {
    const choice = (this.seed + this.uses) % modulo;
    this.uses += 1;
    return choice;
  }
}

/**
 * Translate a staged plan into a legal stream: every emitted command still
 * passes through the shadow model (illegal intents are silently skipped —
 * that filter is itself under test via the pauseResume passages). Open turns
 * are DRAINED deterministically at block end the way the real loop ends a
 * turn: settle the pending model request, settle every ACTIVE tool execution,
 * complete the turn. A `finish` plan resolves open challenges (the legal §14
 * path) before completing the session.
 */
export function translateSessionPlan(plan: SessionPlan): FullVocabularyStream {
  const machine = new FullVocabularyMachine();
  const events: SessionEventUnion[] = [sessionCreated(1)];
  const chooser = new DrainChooser(plan.blocks.length);
  const emit = (command: FullVocabularyCommand): void => {
    const event = machine.apply(command, events.length + 1);
    if (event !== null) {
      events.push(event);
    }
  };

  for (const block of plan.blocks) {
    if (machine.status === "COMPLETED") {
      break;
    }
    if (block.kind === "turn") {
      emit({ kind: "startTurn", turn: block.turn });
      for (const step of block.steps) {
        emit(step);
      }
      drainOpenTurn(machine, events, chooser);
      continue;
    }
    if (block.kind === "epistemic") {
      for (const step of block.steps) {
        emit(step);
      }
      continue;
    }
    emit({ kind: "pause" });
    for (const step of block.steps) {
      emit(step);
    }
    emit({ kind: "resume" });
  }

  if (plan.finish && machine.status !== "COMPLETED") {
    for (const challenge of [...machine.openChallengeOrder]) {
      const choice = chooser.pick(3);
      const outcome: ChallengeOutcome =
        choice === 0 ? "accepted" : choice === 1 ? "rejected" : "resolved";
      emit({ kind: "resolveChallenge", challenge, outcome });
    }
    emit({ kind: "completeSession" });
  }
  return { events, machine };
}

function drainOpenTurn(
  machine: FullVocabularyMachine,
  events: SessionEventUnion[],
  chooser: DrainChooser,
): void {
  if (machine.openTurn === null) {
    return;
  }
  const emit = (command: FullVocabularyCommand): void => {
    const event = machine.apply(command, events.length + 1);
    if (event !== null) {
      events.push(event);
    }
  };
  if (machine.pendingModel) {
    emit(chooser.pick(2) === 0 ? { kind: "completeModel" } : { kind: "failModel" });
  }
  for (const execution of [...machine.tools.keys()]) {
    const tool = machine.tools.get(execution);
    if (tool === undefined || !ACTIVE_TOOL_STATUSES.includes(tool.status)) {
      continue;
    }
    // Half the drains abandon the execution (the crash-recovery rejection
    // path); the other half drives it to a terminal, including the
    // indeterminate-then-reconcile path across all three outcomes.
    if (chooser.pick(2) === 0) {
      emit({ kind: "rejectTool", execution });
      continue;
    }
    if (tool.status === "PROPOSED") {
      emit({ kind: "authorizeTool", execution });
    }
    emit({ kind: "startTool", execution });
    const outcome = chooser.pick(3);
    if (outcome === 0) {
      emit({ kind: "succeedTool", execution });
    } else if (outcome === 1) {
      emit({ kind: "failTool", execution });
    } else {
      emit({ kind: "indeterminateTool", execution });
      const reconciliationChoice = chooser.pick(3);
      const reconciliation: "succeeded" | "failed" | "indeterminate" =
        reconciliationChoice === 0
          ? "succeeded"
          : reconciliationChoice === 1
            ? "failed"
            : "indeterminate";
      emit({ kind: "reconcileTool", execution, outcome: reconciliation });
    }
  }
  emit({ kind: "completeTurn" });
}

/**
 * Normalized projection both sides can produce: the folded DerivedSessionState
 * and the shadow machine. Plain JSON-comparable data (ids are the factories'
 * stable schemes), so vitest's toEqual gives field-precise failure output.
 */
export type VocabularyProjection = {
  status: SessionStatus;
  openTurn: string | null;
  turnCount: number;
  pendingModel: boolean;
  tools: ReadonlyArray<
    readonly [string, readonly [ToolExecutionStatus, number, boolean, boolean, boolean, boolean]]
  >;
  goal: string | null;
  observations: readonly string[];
  hypotheses: ReadonlyArray<readonly [string, HypothesisStatus]>;
  plans: ReadonlyArray<readonly [string, "active" | "superseded" | "invalidated"]>;
  activePlan: string | null;
  challenges: ReadonlyArray<readonly [string, ChallengeOutcome | "open"]>;
  openChallenges: readonly string[];
  lastVerification: VerificationOutcome | null;
};

const sorted = <T>(values: readonly T[]): readonly T[] => [...values].sort();

export function projectMachine(machine: FullVocabularyMachine): VocabularyProjection {
  return {
    status: machine.status,
    openTurn: machine.openTurn === null ? null : `turn-${machine.openTurn}`,
    turnCount: machine.usedTurns.size,
    pendingModel: machine.pendingModel,
    tools: sorted(
      [...machine.tools.entries()].map(
        ([execution, tool]) =>
          [
            `tool-exec-${execution}`,
            [
              tool.status,
              tool.reconciliations,
              tool.hasResult,
              tool.hasFailure,
              tool.hasIndeterminate,
              tool.hasRejection,
            ],
          ] as const,
      ),
    ),
    goal: machine.goal,
    observations: sorted([...machine.observations].map((observation) => `obs-${observation}`)),
    hypotheses: sorted(
      [...machine.hypotheses.entries()].map(
        ([hypothesis, status]) => [`hyp-${hypothesis}`, status] as const,
      ),
    ),
    plans: sorted(
      [...machine.plans.entries()].map(([plan, status]) => [`plan-${plan}`, status] as const),
    ),
    activePlan: machine.activePlan === null ? null : `plan-${machine.activePlan}`,
    challenges: sorted(
      [...machine.challenges.entries()].map(
        ([challenge, status]) => [`challenge-${challenge}`, status] as const,
      ),
    ),
    openChallenges: machine.openChallengeOrder.map((challenge) => `challenge-${challenge}`),
    lastVerification: machine.lastVerification,
  };
}

export function projectDerivedState(state: DerivedSessionState): VocabularyProjection {
  return {
    status: state.status,
    openTurn: state.currentTurnId === undefined ? null : state.currentTurnId.valueOf(),
    turnCount: state.turnIds.size,
    pendingModel: state.pendingModelRequest !== undefined,
    tools: sorted(
      [...state.toolExecutions.entries()].map(
        ([id, snapshot]) =>
          [
            id.valueOf(),
            [
              snapshot.status,
              snapshot.reconciliationCount,
              snapshot.resultJson !== undefined,
              snapshot.failureMessage !== undefined,
              snapshot.indeterminateReason !== undefined,
              snapshot.rejectionReason !== undefined,
            ],
          ] as const,
      ),
    ),
    goal: state.goal === undefined ? null : state.goal.goal,
    observations: sorted([...state.observations.keys()].map((id) => id.valueOf())),
    hypotheses: sorted(
      [...state.hypotheses.entries()].map(
        ([id, hypothesis]) => [id.valueOf(), hypothesis.status] as const,
      ),
    ),
    plans: sorted(
      [...state.plans.entries()].map(([id, plan]) => [id.valueOf(), plan.status] as const),
    ),
    activePlan: state.activePlan === undefined ? null : state.activePlan.planId.valueOf(),
    challenges: sorted(
      [...state.challenges.entries()].map(
        ([id, challenge]) => [id.valueOf(), challenge.status] as const,
      ),
    ),
    openChallenges: state.openChallenges.map((challenge) => challenge.challengeId.valueOf()),
    lastVerification: state.lastVerification === undefined ? null : state.lastVerification.outcome,
  };
}
