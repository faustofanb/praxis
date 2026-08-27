import type { SessionEventUnion, SessionId, TurnId } from "@praxis/contracts";

/**
 * v1 StateReducer over the Session/Turn event slice (docs/02 section 7).
 * Pure: no I/O, clock, randomness, or environment. All nondeterministic
 * inputs must already be facts inside the events. Goal/epistemic/model/tool
 * projections join as their event vocabulary lands in M2-M4.
 */

export type SessionStatus = "EMPTY" | "ACTIVE" | "PAUSED" | "COMPLETED";

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
  return { status: "EMPTY", headSeq: 0, turnIds: new Set() };
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
      const { currentTurnId: _closed, ...rest } = advanced;
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
