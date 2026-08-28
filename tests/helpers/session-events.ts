import type { EventActor, SessionEventUnion, SessionId, ToolEffect } from "@praxis/contracts";
import {
  asEventId,
  asSessionId,
  asToolExecutionId,
  asTurnId,
  EVENT_SCHEMA_VERSION,
} from "@praxis/contracts";

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

function toolExecutionId(execution: number) {
  return asToolExecutionId(`tool-exec-${execution}`);
}

export function toolProposed(
  seq: number,
  execution: number,
  options: { name?: string; argumentsJson?: string; effect?: ToolEffect } = {},
): SessionEventUnion {
  return {
    ...base(seq),
    type: "ToolProposed",
    payload: {
      toolExecutionId: toolExecutionId(execution),
      name: options.name ?? "read_file",
      argumentsJson: options.argumentsJson ?? '{"path":"a.txt"}',
      effect: options.effect ?? "read_only",
    },
  };
}

export function toolAuthorized(seq: number, execution: number): SessionEventUnion {
  return {
    ...base(seq),
    type: "ToolAuthorized",
    payload: { toolExecutionId: toolExecutionId(execution) },
  };
}

export function toolRejected(
  seq: number,
  execution: number,
  reason = "not permitted",
): SessionEventUnion {
  return {
    ...base(seq),
    type: "ToolRejected",
    payload: { toolExecutionId: toolExecutionId(execution), reason },
  };
}

export function toolStarted(seq: number, execution: number): SessionEventUnion {
  return {
    ...base(seq),
    type: "ToolStarted",
    payload: { toolExecutionId: toolExecutionId(execution) },
  };
}

export function toolSucceeded(
  seq: number,
  execution: number,
  resultJson = '{"content":"ok"}',
): SessionEventUnion {
  return {
    ...base(seq),
    type: "ToolSucceeded",
    payload: { toolExecutionId: toolExecutionId(execution), resultJson },
  };
}

export function toolFailed(seq: number, execution: number, message = "boom"): SessionEventUnion {
  return {
    ...base(seq),
    type: "ToolFailed",
    payload: { toolExecutionId: toolExecutionId(execution), message },
  };
}

export function toolIndeterminate(
  seq: number,
  execution: number,
  reason = "outcome unknown",
): SessionEventUnion {
  return {
    ...base(seq),
    type: "ToolIndeterminate",
    payload: { toolExecutionId: toolExecutionId(execution), reason },
  };
}
