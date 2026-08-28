import type {
  SessionEventUnion,
  SessionId,
  ToolEffect,
  ToolExecutionId,
  ToolExecutionStatus,
  TurnId,
} from "@praxis/contracts";

/**
 * v1 StateReducer over the Session/Turn, tool-execution, and model-call event
 * slices (docs/02 sections 6.2, 7-8, 10). Pure: no I/O, clock, randomness, or
 * environment. All nondeterministic inputs must already be facts inside the
 * events. Goal/epistemic projections join as their vocabulary lands in M3-M4.
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

/**
 * Derived, never persisted: recomputed by folding a session's event stream.
 * v1 slice of the DerivedSessionState shape in docs/02 section 7.
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
  return { status: "EMPTY", headSeq: 0, turnIds: new Set(), toolExecutions: new Map() };
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

function withTool(
  state: DerivedSessionState,
  snapshot: ToolExecutionSnapshot,
): DerivedSessionState {
  const toolExecutions = new Map(state.toolExecutions);
  toolExecutions.set(snapshot.toolExecutionId, snapshot);
  return { ...state, toolExecutions };
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
