import type {
  ChallengeOutcome,
  ChallengeTargetType,
  EventActor,
  HypothesisStatusChange,
  ModelProviderErrorKind,
  ObservationSource,
  SessionEventUnion,
  SessionId,
  ToolCallRequest,
  ToolEffect,
  VerificationOutcome,
} from "@praxis/contracts";
import {
  asChallengeId,
  asEventId,
  asHypothesisId,
  asObservationId,
  asPlanId,
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

export function turnStarted(seq: number, turn: number, input?: string): SessionEventUnion {
  return {
    ...base(seq),
    type: "TurnStarted",
    payload: input === undefined ? { turnId: turnId(turn) } : { turnId: turnId(turn), input },
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
  options: {
    name?: string;
    argumentsJson?: string;
    effect?: ToolEffect;
    toolCallId?: string;
  } = {},
): SessionEventUnion {
  return {
    ...base(seq),
    type: "ToolProposed",
    payload: {
      toolExecutionId: toolExecutionId(execution),
      name: options.name ?? "read_file",
      argumentsJson: options.argumentsJson ?? '{"path":"a.txt"}',
      effect: options.effect ?? "read_only",
      ...(options.toolCallId === undefined ? {} : { toolCallId: options.toolCallId }),
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

export function toolReconciled(
  seq: number,
  execution: number,
  outcome: "succeeded" | "failed" | "indeterminate" = "indeterminate",
  detail?: string,
): SessionEventUnion {
  const id = toolExecutionId(execution);
  const payload =
    outcome === "succeeded"
      ? { toolExecutionId: id, outcome, resultJson: detail ?? '{"content":"reconciled"}' }
      : outcome === "failed"
        ? { toolExecutionId: id, outcome, message: detail ?? "provably absent" }
        : { toolExecutionId: id, outcome, reason: detail ?? "still unknown" };
  return { ...base(seq), type: "ToolReconciled", payload };
}

export function modelRequestStarted(seq: number, model = "test-model"): SessionEventUnion {
  return {
    ...base(seq),
    type: "ModelRequestStarted",
    payload: { model },
  };
}

export function modelResponseCompleted(
  seq: number,
  options: { text?: string; toolCalls?: ToolCallRequest[] } = {},
): SessionEventUnion {
  return {
    ...base(seq),
    type: "ModelResponseCompleted",
    payload: {
      ...(options.text === undefined ? {} : { text: options.text }),
      toolCalls: options.toolCalls ?? [],
    },
  };
}

export function modelRequestFailed(
  seq: number,
  options: { kind?: ModelProviderErrorKind; retryable?: boolean; message?: string } = {},
): SessionEventUnion {
  return {
    ...base(seq),
    type: "ModelRequestFailed",
    payload: {
      kind: options.kind ?? "network",
      retryable: options.retryable ?? false,
      message: options.message ?? "provider exploded",
    },
  };
}

function observationId(observation: number) {
  return asObservationId(`obs-${observation}`);
}

function hypothesisId(hypothesis: number) {
  return asHypothesisId(`hyp-${hypothesis}`);
}

function planId(plan: number) {
  return asPlanId(`plan-${plan}`);
}

function challengeId(challenge: number) {
  return asChallengeId(`challenge-${challenge}`);
}

export function goalSet(
  seq: number,
  options: {
    goal?: string;
    need?: string;
    constraints?: readonly string[];
    strategy?: string;
    mission?: string;
  } = {},
): SessionEventUnion {
  return {
    ...base(seq),
    type: "GoalSet",
    payload: {
      ...(options.need === undefined ? {} : { need: options.need }),
      goal: options.goal ?? "answer the user question",
      constraints: (options.constraints ?? ["stay read-only"]).map((description) => ({
        description,
      })),
      ...(options.strategy === undefined ? {} : { strategy: options.strategy }),
      ...(options.mission === undefined ? {} : { mission: options.mission }),
    },
  };
}

export function observationRecorded(
  seq: number,
  observation: number,
  options: { claim?: string; source?: ObservationSource; evidence?: number[] } = {},
): SessionEventUnion {
  return {
    ...base(seq),
    type: "ObservationRecorded",
    payload: {
      observationId: observationId(observation),
      source: options.source ?? { kind: "system", detail: "test observation" },
      claim: options.claim ?? "the note file exists",
      evidenceEventIds: (options.evidence ?? [1]).map((n) => asEventId(`event-${n}`)),
    },
  };
}

export function hypothesisProposed(
  seq: number,
  hypothesis: number,
  options: { statement?: string; support?: number[]; conflicts?: number[] } = {},
): SessionEventUnion {
  return {
    ...base(seq),
    type: "HypothesisProposed",
    payload: {
      hypothesisId: hypothesisId(hypothesis),
      statement: options.statement ?? "the answer is inside the note file",
      ...(options.support === undefined
        ? {}
        : { support: options.support.map((n) => asEventId(`event-${n}`)) }),
      ...(options.conflicts === undefined
        ? {}
        : { conflicts: options.conflicts.map((n) => asEventId(`event-${n}`)) }),
    },
  };
}

export function hypothesisStatusChanged(
  seq: number,
  hypothesis: number,
  to: HypothesisStatusChange,
  options: { evidence?: number[]; reason?: string } = {},
): SessionEventUnion {
  return {
    ...base(seq),
    type: "HypothesisStatusChanged",
    payload: {
      hypothesisId: hypothesisId(hypothesis),
      to,
      ...(options.evidence === undefined
        ? {}
        : { evidenceEventIds: options.evidence.map((n) => asEventId(`event-${n}`)) }),
      ...(options.reason === undefined ? {} : { reason: options.reason }),
    },
  };
}

export function planSet(
  seq: number,
  plan: number,
  options: {
    goalRef?: string;
    hypothesis?: number;
    nextAction?: string;
    falsifiedIf?: string;
    focus?: string;
  } = {},
): SessionEventUnion {
  return {
    ...base(seq),
    type: "PlanSet",
    payload: {
      planId: planId(plan),
      goalRef: options.goalRef ?? "answer the user question",
      ...(options.focus === undefined ? {} : { focus: options.focus }),
      ...(options.hypothesis === undefined
        ? {}
        : { hypothesisId: hypothesisId(options.hypothesis) }),
      nextAction: options.nextAction ?? "read the note file",
      ...(options.falsifiedIf === undefined ? {} : { falsifiedIf: options.falsifiedIf }),
    },
  };
}

export function planInvalidated(
  seq: number,
  plan: number,
  reason = "the note file is gone",
): SessionEventUnion {
  return {
    ...base(seq),
    type: "PlanInvalidated",
    payload: { planId: planId(plan), reason },
  };
}

export function challengeRaised(
  seq: number,
  challenge: number,
  options: {
    targetType?: ChallengeTargetType;
    target?: string;
    claim?: string;
    evidence?: number[];
  } = {},
): SessionEventUnion {
  const targetType = options.targetType ?? "plan";
  const challengeIdValue = challengeId(challenge);
  const claim = options.claim ?? "the plan ignores the missing file";
  const evidenceEventIds = (options.evidence ?? [2]).map((n) => asEventId(`event-${n}`));
  const payload =
    targetType === "hypothesis"
      ? {
          challengeId: challengeIdValue,
          targetType,
          targetId: asHypothesisId(options.target ?? "hyp-1"),
          claim,
          evidenceEventIds,
        }
      : targetType === "plan"
        ? {
            challengeId: challengeIdValue,
            targetType,
            targetId: asPlanId(options.target ?? "plan-1"),
            claim,
            evidenceEventIds,
          }
        : targetType === "completion"
          ? {
              challengeId: challengeIdValue,
              targetType,
              targetId: options.target ?? "session-completion",
              claim,
              evidenceEventIds,
            }
          : {
              challengeId: challengeIdValue,
              targetType,
              targetId: options.target ?? "read-only boundary",
              claim,
              evidenceEventIds,
            };
  return {
    ...base(seq),
    type: "ChallengeRaised",
    payload,
  };
}

export function challengeResolved(
  seq: number,
  challenge: number,
  outcome: ChallengeOutcome = "rejected",
  reason = "the file exists under another name",
): SessionEventUnion {
  return {
    ...base(seq),
    type: "ChallengeResolved",
    payload: { challengeId: challengeId(challenge), outcome, reason },
  };
}

export function verificationRecorded(
  seq: number,
  options: { outcome?: VerificationOutcome; summary?: string; evidence?: number[] } = {},
): SessionEventUnion {
  return {
    ...base(seq),
    type: "VerificationRecorded",
    payload: {
      outcome: options.outcome ?? "inconclusive",
      summary: options.summary ?? "checker unavailable",
      evidenceEventIds: (options.evidence ?? [1]).map((n) => asEventId(`event-${n}`)),
    },
  };
}
