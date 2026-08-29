import type {
  Challenge,
  ChallengeId,
  GoalState,
  Hypothesis,
  HypothesisId,
  HypothesisStatus,
  HypothesisStatusChange,
  Observation,
  ObservationId,
  Plan,
  PlanId,
  PlanStatus,
  SessionEventUnion,
  SessionId,
  ToolEffect,
  ToolExecutionId,
  ToolExecutionStatus,
  TurnId,
  VerificationResult,
} from "@praxis/contracts";

/**
 * v1 StateReducer over the Session/Turn, tool-execution, model-call, and
 * Goal/Epistemic event slices (docs/02 sections 5-8, 10, 13-14). Pure: no
 * I/O, clock, randomness, or environment. All nondeterministic inputs must
 * already be facts inside the events.
 *
 * Epistemic events are session-level facts, not turn actions: they require a
 * live session but no open turn (docs/02 section 16 — the host/extension
 * contribution channel), mirroring the ToolReconciled historical-fact law.
 */

export type SessionStatus = "EMPTY" | "ACTIVE" | "PAUSED" | "COMPLETED";

/** Per-execution projection of the docs/02 section 8.2 state machine. */
export type ToolExecutionSnapshot = {
  readonly toolExecutionId: ToolExecutionId;
  readonly turnId: TurnId;
  readonly name: string;
  readonly argumentsJson: string;
  readonly effect: ToolEffect;
  readonly status: ToolExecutionStatus;
  /**
   * Reconciliation attempts recorded against this execution. Zero until a
   * ToolReconciled fact arrives; INDETERMINATE executions may reconcile
   * repeatedly, so this counts attempts, not outcomes.
   */
  readonly reconciliationCount: number;
  readonly resultJson?: string;
  readonly rejectionReason?: string;
  readonly failureMessage?: string;
  readonly indeterminateReason?: string;
};

const ACTIVE_TOOL_STATUSES: readonly ToolExecutionStatus[] = [
  "PROPOSED",
  "AUTHORIZED",
  "EXECUTING",
];

/** Legal HypothesisStatusChanged targets per current status; empty is terminal. */
const LEGAL_HYPOTHESIS_CHANGES: Readonly<
  Record<HypothesisStatus, readonly HypothesisStatusChange[]>
> = {
  proposed: ["supported", "falsified", "superseded"],
  supported: ["falsified", "superseded"],
  falsified: [],
  superseded: [],
};

/**
 * Derived, never persisted: recomputed by folding a session's event stream.
 * The docs/02 section 7 shape plus the id registries its laws enforce
 * ("at least includes" — uniqueness, terminal-target rejection, and challenge
 * target validation all need the maps).
 */
export type DerivedSessionState = {
  sessionId?: SessionId;
  status: SessionStatus;
  headSeq: number;
  currentTurnId?: TurnId;
  turnIds: ReadonlySet<TurnId>;
  toolExecutions: ReadonlyMap<ToolExecutionId, ToolExecutionSnapshot>;
  /** Set by ModelRequestStarted, cleared by ModelResponseCompleted/Failed. */
  pendingModelRequest?: { readonly model: string };
  goal?: GoalState;
  observations: ReadonlyMap<ObservationId, Observation>;
  hypotheses: ReadonlyMap<HypothesisId, Hypothesis>;
  plans: ReadonlyMap<PlanId, Plan>;
  /** Convenience view of the single plan with status "active". */
  activePlan?: Plan;
  challenges: ReadonlyMap<ChallengeId, Challenge>;
  openChallenges: readonly Challenge[];
  lastVerification?: VerificationResult;
};

export class IllegalTransitionError extends Error {
  constructor(
    readonly eventType: SessionEventUnion["type"] | "StreamContinuity",
    readonly status: SessionStatus,
    readonly detail: string,
  ) {
    super(`illegal transition: ${eventType} in status ${status}: ${detail}`);
    this.name = "IllegalTransitionError";
  }
}

export function initialSessionState(): DerivedSessionState {
  return {
    status: "EMPTY",
    headSeq: 0,
    turnIds: new Set(),
    toolExecutions: new Map(),
    observations: new Map(),
    hypotheses: new Map(),
    plans: new Map(),
    challenges: new Map(),
    openChallenges: [],
  };
}

export function reduceSession(
  state: DerivedSessionState,
  event: SessionEventUnion,
): DerivedSessionState {
  if (event.seq !== state.headSeq + 1) {
    throw new IllegalTransitionError(
      "StreamContinuity",
      state.status,
      `expected seq ${state.headSeq + 1}, got ${event.seq}`,
    );
  }
  if (state.sessionId !== undefined && event.sessionId !== state.sessionId) {
    throw new IllegalTransitionError(
      "StreamContinuity",
      state.status,
      `event belongs to session ${event.sessionId}, stream is ${state.sessionId}`,
    );
  }

  const advanced: DerivedSessionState = { ...state, headSeq: event.seq };

  switch (event.type) {
    case "SessionCreated": {
      if (state.status !== "EMPTY" || state.sessionId !== undefined) {
        throw new IllegalTransitionError("SessionCreated", state.status, "session already created");
      }
      return {
        status: "ACTIVE",
        headSeq: advanced.headSeq,
        sessionId: event.sessionId,
        turnIds: new Set(),
        toolExecutions: new Map(),
        observations: new Map(),
        hypotheses: new Map(),
        plans: new Map(),
        challenges: new Map(),
        openChallenges: [],
      };
    }
    case "SessionResumed": {
      requireStatus(state, "SessionResumed", "PAUSED");
      return { ...advanced, status: "ACTIVE" };
    }
    case "SessionPaused": {
      requireStatus(state, "SessionPaused", "ACTIVE");
      requireNoOpenTurn(state, "SessionPaused");
      return { ...advanced, status: "PAUSED" };
    }
    case "SessionCompleted": {
      requireStatus(state, "SessionCompleted", "ACTIVE");
      requireNoOpenTurn(state, "SessionCompleted");
      // Section 14: a completion-target challenge blocks completion until
      // resolved. The v1 policy is the law itself — deterministic, no
      // policy object, no model consultation.
      const blocking = state.openChallenges.filter(
        (challenge) => challenge.targetType === "completion",
      );
      if (blocking.length > 0) {
        const ids = blocking.map((challenge) => challenge.challengeId.valueOf()).join(", ");
        throw new IllegalTransitionError(
          "SessionCompleted",
          state.status,
          `open completion-target challenge(s) must be resolved first: ${ids}`,
        );
      }
      return { ...advanced, status: "COMPLETED" };
    }
    case "TurnStarted": {
      requireStatus(state, "TurnStarted", "ACTIVE");
      if (state.currentTurnId !== undefined) {
        throw new IllegalTransitionError(
          "TurnStarted",
          state.status,
          `turn ${state.currentTurnId} is still open`,
        );
      }
      if (state.turnIds.has(event.payload.turnId)) {
        throw new IllegalTransitionError(
          "TurnStarted",
          state.status,
          `turn id ${event.payload.turnId} already used`,
        );
      }
      const turnIds = new Set(state.turnIds);
      turnIds.add(event.payload.turnId);
      return {
        ...advanced,
        currentTurnId: event.payload.turnId,
        turnIds,
      };
    }
    case "TurnCompleted": {
      if (state.currentTurnId === undefined) {
        throw new IllegalTransitionError("TurnCompleted", state.status, "no open turn");
      }
      if (state.currentTurnId !== event.payload.turnId) {
        throw new IllegalTransitionError(
          "TurnCompleted",
          state.status,
          `open turn is ${state.currentTurnId}, event completes ${event.payload.turnId}`,
        );
      }
      requireNoActiveToolExecutions(state, "TurnCompleted");
      requireNoPendingModelRequest(state, "TurnCompleted");
      const { currentTurnId: _closed, ...rest } = advanced;
      return rest;
    }
    case "ToolProposed": {
      requireStatus(state, "ToolProposed", "ACTIVE");
      const turnId = requireOpenTurn(state, "ToolProposed");
      requireNoPendingModelRequest(state, "ToolProposed");
      const { toolExecutionId } = event.payload;
      if (state.toolExecutions.has(toolExecutionId)) {
        throw new IllegalTransitionError(
          "ToolProposed",
          state.status,
          `tool execution id ${toolExecutionId} already used`,
        );
      }
      return withTool(advanced, {
        toolExecutionId,
        turnId,
        name: event.payload.name,
        argumentsJson: event.payload.argumentsJson,
        effect: event.payload.effect,
        status: "PROPOSED",
        reconciliationCount: 0,
      });
    }
    case "ToolAuthorized": {
      const snapshot = requireTool(
        state,
        "ToolAuthorized",
        event.payload.toolExecutionId,
        "PROPOSED",
      );
      return withTool(advanced, { ...snapshot, status: "AUTHORIZED" });
    }
    case "ToolRejected": {
      // AUTHORIZED -> ToolRejected exists for crash recovery only: an
      // authorization without a start provably never executed, so abandoning
      // it is an honest rejection, not a coerced failure.
      const snapshot = requireTool(
        state,
        "ToolRejected",
        event.payload.toolExecutionId,
        "PROPOSED",
        "AUTHORIZED",
      );
      return withTool(advanced, {
        ...snapshot,
        status: "REJECTED",
        rejectionReason: event.payload.reason,
      });
    }
    case "ToolStarted": {
      const snapshot = requireTool(
        state,
        "ToolStarted",
        event.payload.toolExecutionId,
        "AUTHORIZED",
      );
      return withTool(advanced, { ...snapshot, status: "EXECUTING" });
    }
    case "ToolSucceeded": {
      const snapshot = requireTool(
        state,
        "ToolSucceeded",
        event.payload.toolExecutionId,
        "EXECUTING",
      );
      return withTool(advanced, {
        ...snapshot,
        status: "SUCCEEDED",
        resultJson: event.payload.resultJson,
      });
    }
    case "ToolFailed": {
      const snapshot = requireTool(state, "ToolFailed", event.payload.toolExecutionId, "EXECUTING");
      return withTool(advanced, {
        ...snapshot,
        status: "FAILED",
        failureMessage: event.payload.message,
      });
    }
    case "ToolIndeterminate": {
      const snapshot = requireTool(
        state,
        "ToolIndeterminate",
        event.payload.toolExecutionId,
        "EXECUTING",
      );
      return withTool(advanced, {
        ...snapshot,
        status: "INDETERMINATE",
        indeterminateReason: event.payload.reason,
      });
    }
    case "ToolReconciled": {
      // Only INDETERMINATE may settle (docs/02 section 8.2): reconciliation
      // must never resurrect a terminal reached by execution or by an earlier
      // reconciliation, and a still-indeterminate attempt stays honest for a
      // later retry or escalation.
      const snapshot = requireHistoricalTool(
        state,
        "ToolReconciled",
        event.payload.toolExecutionId,
        "INDETERMINATE",
      );
      const reconciled = { ...snapshot, reconciliationCount: snapshot.reconciliationCount + 1 };
      const outcome = event.payload.outcome;
      switch (outcome) {
        case "succeeded":
          return withTool(advanced, {
            ...reconciled,
            status: "SUCCEEDED",
            resultJson: event.payload.resultJson,
          });
        case "failed":
          return withTool(advanced, {
            ...reconciled,
            status: "FAILED",
            failureMessage: event.payload.message,
          });
        case "indeterminate":
          return withTool(advanced, {
            ...reconciled,
            indeterminateReason: event.payload.reason,
          });
      }
      // Unreachable for the validated union; guards against schema drift.
      throw new IllegalTransitionError(
        "ToolReconciled",
        state.status,
        `unhandled reconciliation outcome ${JSON.stringify(outcome)}`,
      );
    }
    case "ModelRequestStarted": {
      requireStatus(state, "ModelRequestStarted", "ACTIVE");
      requireOpenTurn(state, "ModelRequestStarted");
      requireNoPendingModelRequest(state, "ModelRequestStarted");
      return { ...advanced, pendingModelRequest: { model: event.payload.model } };
    }
    case "ModelResponseCompleted":
    case "ModelRequestFailed": {
      requireStatus(state, event.type, "ACTIVE");
      requireOpenTurn(state, event.type);
      requirePendingModelRequest(state, event.type);
      const { pendingModelRequest: _settled, ...rest } = advanced;
      return rest;
    }
    case "GoalSet": {
      // Latest-wins: a goal is strategy, replaceable by new evidence; the
      // superseded goal remains reconstructable from the event stream.
      requireStatus(state, "GoalSet", "ACTIVE");
      return { ...advanced, goal: event.payload };
    }
    case "ObservationRecorded": {
      requireStatus(state, "ObservationRecorded", "ACTIVE");
      const { observationId } = event.payload;
      if (state.observations.has(observationId)) {
        throw new IllegalTransitionError(
          "ObservationRecorded",
          state.status,
          `observation id ${observationId} already used`,
        );
      }
      const observations = new Map(state.observations);
      observations.set(observationId, { ...event.payload, observedAt: event.occurredAt });
      return { ...advanced, observations };
    }
    case "HypothesisProposed": {
      requireStatus(state, "HypothesisProposed", "ACTIVE");
      const { hypothesisId } = event.payload;
      if (state.hypotheses.has(hypothesisId)) {
        throw new IllegalTransitionError(
          "HypothesisProposed",
          state.status,
          `hypothesis id ${hypothesisId} already used`,
        );
      }
      const hypotheses = new Map(state.hypotheses);
      hypotheses.set(hypothesisId, {
        hypothesisId,
        statement: event.payload.statement,
        status: "proposed",
        support: event.payload.support ?? [],
        conflicts: event.payload.conflicts ?? [],
      });
      return { ...advanced, hypotheses };
    }
    case "HypothesisStatusChanged": {
      requireStatus(state, "HypothesisStatusChanged", "ACTIVE");
      const hypothesis = requireHypothesis(
        state,
        "HypothesisStatusChanged",
        event.payload.hypothesisId,
      );
      if (!LEGAL_HYPOTHESIS_CHANGES[hypothesis.status].includes(event.payload.to)) {
        throw new IllegalTransitionError(
          "HypothesisStatusChanged",
          state.status,
          `hypothesis ${hypothesis.hypothesisId} is ${hypothesis.status}, cannot become ${event.payload.to}`,
        );
      }
      // Evidence direction follows the change: support grows toward
      // "supported", conflicts toward "falsified"; supersession carries a
      // reason, not evidence, so its refs are not filed.
      const evidence = event.payload.evidenceEventIds ?? [];
      const hypotheses = new Map(state.hypotheses);
      hypotheses.set(hypothesis.hypothesisId, {
        ...hypothesis,
        status: event.payload.to,
        support:
          event.payload.to === "supported"
            ? [...hypothesis.support, ...evidence]
            : hypothesis.support,
        conflicts:
          event.payload.to === "falsified"
            ? [...hypothesis.conflicts, ...evidence]
            : hypothesis.conflicts,
      });
      return { ...advanced, hypotheses };
    }
    case "PlanSet": {
      requireStatus(state, "PlanSet", "ACTIVE");
      const { planId, hypothesisId } = event.payload;
      if (state.plans.has(planId)) {
        throw new IllegalTransitionError("PlanSet", state.status, `plan id ${planId} already used`);
      }
      if (hypothesisId !== undefined && !state.hypotheses.has(hypothesisId)) {
        throw new IllegalTransitionError(
          "PlanSet",
          state.status,
          `references unknown hypothesis ${hypothesisId}`,
        );
      }
      const plans = new Map(state.plans);
      if (state.activePlan !== undefined) {
        plans.set(state.activePlan.planId, { ...state.activePlan, status: "superseded" });
      }
      const plan: Plan = { ...event.payload, status: "active" };
      plans.set(planId, plan);
      return { ...advanced, plans, activePlan: plan };
    }
    case "PlanInvalidated": {
      requireStatus(state, "PlanInvalidated", "ACTIVE");
      const plan = requirePlan(state, "PlanInvalidated", event.payload.planId, "active");
      const plans = new Map(state.plans);
      plans.set(plan.planId, { ...plan, status: "invalidated" });
      const { activePlan: _invalidated, ...rest } = advanced;
      return { ...rest, plans };
    }
    case "ChallengeRaised": {
      requireStatus(state, "ChallengeRaised", "ACTIVE");
      const { challengeId, targetType, targetId } = event.payload;
      if (state.challenges.has(challengeId)) {
        throw new IllegalTransitionError(
          "ChallengeRaised",
          state.status,
          `challenge id ${challengeId} already used`,
        );
      }
      if (targetType === "hypothesis" && !state.hypotheses.has(targetId)) {
        throw new IllegalTransitionError(
          "ChallengeRaised",
          state.status,
          `unknown hypothesis target ${targetId}`,
        );
      }
      if (targetType === "plan" && !state.plans.has(targetId)) {
        throw new IllegalTransitionError(
          "ChallengeRaised",
          state.status,
          `unknown plan target ${targetId}`,
        );
      }
      const challenge: Challenge = {
        challengeId,
        targetType,
        targetId,
        claim: event.payload.claim,
        evidenceEventIds: event.payload.evidenceEventIds,
        status: "open",
      };
      const challenges = new Map(state.challenges);
      challenges.set(challengeId, challenge);
      return { ...advanced, challenges, openChallenges: [...state.openChallenges, challenge] };
    }
    case "ChallengeResolved": {
      requireStatus(state, "ChallengeResolved", "ACTIVE");
      const challenge = requireChallenge(
        state,
        "ChallengeResolved",
        event.payload.challengeId,
        "open",
      );
      const challenges = new Map(state.challenges);
      challenges.set(challenge.challengeId, { ...challenge, status: event.payload.outcome });
      return {
        ...advanced,
        challenges,
        openChallenges: state.openChallenges.filter(
          (open) => open.challengeId !== challenge.challengeId,
        ),
      };
    }
    case "VerificationRecorded": {
      // Latest-wins; "inconclusive" is an honest terminal reading of the
      // recorded evidence and is never coerced to "failed".
      requireStatus(state, "VerificationRecorded", "ACTIVE");
      return { ...advanced, lastVerification: event.payload };
    }
  }
}

export function foldSessionEvents(events: readonly SessionEventUnion[]): DerivedSessionState {
  let state = initialSessionState();
  for (const event of events) {
    state = reduceSession(state, event);
  }
  return state;
}

function requireStatus(
  state: DerivedSessionState,
  eventType: SessionEventUnion["type"],
  expected: SessionStatus,
): void {
  if (state.status !== expected) {
    throw new IllegalTransitionError(eventType, state.status, `requires status ${expected}`);
  }
}

function requireNoOpenTurn(state: DerivedSessionState, eventType: SessionEventUnion["type"]): void {
  if (state.currentTurnId !== undefined) {
    throw new IllegalTransitionError(
      eventType,
      state.status,
      `turn ${state.currentTurnId} is still open`,
    );
  }
}

function requireOpenTurn(state: DerivedSessionState, eventType: SessionEventUnion["type"]): TurnId {
  if (state.currentTurnId === undefined) {
    throw new IllegalTransitionError(eventType, state.status, "requires an open turn");
  }
  return state.currentTurnId;
}

function requireNoPendingModelRequest(
  state: DerivedSessionState,
  eventType: SessionEventUnion["type"],
): void {
  if (state.pendingModelRequest !== undefined) {
    throw new IllegalTransitionError(
      eventType,
      state.status,
      `model request to ${state.pendingModelRequest.model} is still pending`,
    );
  }
}

function requirePendingModelRequest(
  state: DerivedSessionState,
  eventType: SessionEventUnion["type"],
): void {
  if (state.pendingModelRequest === undefined) {
    throw new IllegalTransitionError(eventType, state.status, "no pending model request");
  }
}

function requireTool(
  state: DerivedSessionState,
  eventType: SessionEventUnion["type"],
  toolExecutionId: ToolExecutionId,
  ...expectedStatuses: readonly ToolExecutionStatus[]
): ToolExecutionSnapshot {
  requireStatus(state, eventType, "ACTIVE");
  const turnId = requireOpenTurn(state, eventType);
  const snapshot = state.toolExecutions.get(toolExecutionId);
  if (snapshot === undefined) {
    throw new IllegalTransitionError(
      eventType,
      state.status,
      `unknown tool execution ${toolExecutionId}`,
    );
  }
  if (snapshot.turnId !== turnId) {
    throw new IllegalTransitionError(
      eventType,
      state.status,
      `tool execution ${toolExecutionId} belongs to turn ${snapshot.turnId}, open turn is ${turnId}`,
    );
  }
  if (!expectedStatuses.includes(snapshot.status)) {
    throw new IllegalTransitionError(
      eventType,
      state.status,
      `requires tool status ${expectedStatuses.join(" or ")}, is ${snapshot.status}`,
    );
  }
  return snapshot;
}

/**
 * Historical tool facts (ToolReconciled) describe a past execution, not a
 * turn-scoped action: section 17 escalation closes the open turn before
 * SessionPaused, so a resumed session has no open turn when reconciliation
 * re-attempts. Requiring one would make the human-gated resume loop
 * structurally impossible; a live session and an INDETERMINATE execution
 * remain the invariants.
 */
function requireHistoricalTool(
  state: DerivedSessionState,
  eventType: SessionEventUnion["type"],
  toolExecutionId: ToolExecutionId,
  ...expectedStatuses: readonly ToolExecutionStatus[]
): ToolExecutionSnapshot {
  requireStatus(state, eventType, "ACTIVE");
  const snapshot = state.toolExecutions.get(toolExecutionId);
  if (snapshot === undefined) {
    throw new IllegalTransitionError(
      eventType,
      state.status,
      `unknown tool execution ${toolExecutionId}`,
    );
  }
  if (!expectedStatuses.includes(snapshot.status)) {
    throw new IllegalTransitionError(
      eventType,
      state.status,
      `requires tool status ${expectedStatuses.join(" or ")}, is ${snapshot.status}`,
    );
  }
  return snapshot;
}

function withTool(
  state: DerivedSessionState,
  snapshot: ToolExecutionSnapshot,
): DerivedSessionState {
  const toolExecutions = new Map(state.toolExecutions);
  toolExecutions.set(snapshot.toolExecutionId, snapshot);
  return { ...state, toolExecutions };
}

function requireHypothesis(
  state: DerivedSessionState,
  eventType: SessionEventUnion["type"],
  hypothesisId: HypothesisId,
): Hypothesis {
  requireStatus(state, eventType, "ACTIVE");
  const hypothesis = state.hypotheses.get(hypothesisId);
  if (hypothesis === undefined) {
    throw new IllegalTransitionError(eventType, state.status, `unknown hypothesis ${hypothesisId}`);
  }
  return hypothesis;
}

function requirePlan(
  state: DerivedSessionState,
  eventType: SessionEventUnion["type"],
  planId: PlanId,
  ...expectedStatuses: readonly PlanStatus[]
): Plan {
  requireStatus(state, eventType, "ACTIVE");
  const plan = state.plans.get(planId);
  if (plan === undefined) {
    throw new IllegalTransitionError(eventType, state.status, `unknown plan ${planId}`);
  }
  if (!expectedStatuses.includes(plan.status)) {
    throw new IllegalTransitionError(
      eventType,
      state.status,
      `requires plan status ${expectedStatuses.join(" or ")}, is ${plan.status}`,
    );
  }
  return plan;
}

function requireChallenge(
  state: DerivedSessionState,
  eventType: SessionEventUnion["type"],
  challengeId: ChallengeId,
  ...expectedStatuses: readonly Challenge["status"][]
): Challenge {
  requireStatus(state, eventType, "ACTIVE");
  const challenge = state.challenges.get(challengeId);
  if (challenge === undefined) {
    throw new IllegalTransitionError(eventType, state.status, `unknown challenge ${challengeId}`);
  }
  if (!expectedStatuses.includes(challenge.status)) {
    throw new IllegalTransitionError(
      eventType,
      state.status,
      `requires challenge status ${expectedStatuses.join(" or ")}, is ${challenge.status}`,
    );
  }
  return challenge;
}

function requireNoActiveToolExecutions(
  state: DerivedSessionState,
  eventType: SessionEventUnion["type"],
): void {
  for (const snapshot of state.toolExecutions.values()) {
    if (snapshot.turnId !== state.currentTurnId) {
      continue;
    }
    if (ACTIVE_TOOL_STATUSES.includes(snapshot.status)) {
      throw new IllegalTransitionError(
        eventType,
        state.status,
        `tool execution ${snapshot.toolExecutionId} is still ${snapshot.status}`,
      );
    }
  }
}
