import type { EventActor, SessionEventUnion, SessionId } from "@praxis/contracts";
import { asEventId, asSessionId, asTurnId, EVENT_SCHEMA_VERSION } from "@praxis/contracts";

export const TEST_SESSION_ID: SessionId = asSessionId("session-test");

const SYSTEM_ACTOR: EventActor = { kind: "system" };

let eventCounter = 0;

function base(seq: number) {
  eventCounter += 1;
  return {
    id: asEventId(`event-${eventCounter}`),
    sessionId: TEST_SESSION_ID,
    seq,
    schemaVersion: EVENT_SCHEMA_VERSION,
    occurredAt: eventCounter,
    actor: SYSTEM_ACTOR,
  };
}

function turnId(turn: number) {
  return asTurnId(`turn-${turn}`);
}

export function sessionCreated(seq: number, reason?: string): SessionEventUnion {
  return {
    ...base(seq),
    type: "SessionCreated",
    payload: reason === undefined ? {} : { reason },
  };
}

export function sessionResumed(seq: number): SessionEventUnion {
  return { ...base(seq), type: "SessionResumed", payload: {} };
}

export function sessionPaused(seq: number): SessionEventUnion {
  return { ...base(seq), type: "SessionPaused", payload: {} };
}

export function sessionCompleted(seq: number): SessionEventUnion {
  return { ...base(seq), type: "SessionCompleted", payload: {} };
}

export function turnStarted(seq: number, turn: number): SessionEventUnion {
  return {
    ...base(seq),
    type: "TurnStarted",
    payload: { turnId: turnId(turn) },
  };
}

export function turnCompleted(seq: number, turn: number): SessionEventUnion {
  return {
    ...base(seq),
    type: "TurnCompleted",
    payload: { turnId: turnId(turn) },
  };
}
