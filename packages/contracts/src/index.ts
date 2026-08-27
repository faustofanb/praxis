/**
 * Public API of @praxis/contracts. Deep imports are forbidden
 * (.praxis/architecture.yaml); everything durable goes through this entry.
 */

export const packageName = "@praxis/contracts";

export type {
  EventActor,
  ModelActor,
  SystemActor,
  ToolActor,
  UserActor,
} from "./actor";
export {
  EventActorSchema,
  ModelActorSchema,
  SystemActorSchema,
  ToolActorSchema,
  UserActorSchema,
} from "./actor";
export type { EventEnvelopeBase, SessionEvent } from "./envelope";
export { EVENT_SCHEMA_VERSION, sessionEventSchema } from "./envelope";
export type {
  SessionCompletedEvent,
  SessionCreatedEvent,
  SessionEventType,
  SessionEventUnion,
  SessionPausedEvent,
  SessionResumedEvent,
  TurnCompletedEvent,
  TurnStartedEvent,
} from "./events/session-events";
export {
  SESSION_COMPLETED,
  SESSION_CREATED,
  SESSION_EVENT_TYPES,
  SESSION_PAUSED,
  SESSION_RESUMED,
  SessionCompletedEventSchema,
  SessionCompletedPayloadSchema,
  SessionCreatedEventSchema,
  SessionCreatedPayloadSchema,
  SessionEventUnionSchema,
  SessionPausedEventSchema,
  SessionPausedPayloadSchema,
  SessionResumedEventSchema,
  SessionResumedPayloadSchema,
  TURN_COMPLETED,
  TURN_STARTED,
  TurnCompletedEventSchema,
  TurnCompletedPayloadSchema,
  TurnStartedEventSchema,
  TurnStartedPayloadSchema,
} from "./events/session-events";
export type {
  EventId,
  SessionId,
  StepId,
  ToolExecutionId,
  TurnId,
} from "./ids";
export {
  asEventId,
  asSessionId,
  asStepId,
  asToolExecutionId,
  asTurnId,
  EventIdSchema,
  SessionIdSchema,
  StepIdSchema,
  ToolExecutionIdSchema,
  TurnIdSchema,
} from "./ids";
export type { EventStore } from "./ports/event-store";
export {
  EMPTY_STREAM_HEAD_SEQ,
  EventStoreConflictError,
} from "./ports/event-store";
export type { ToolExecutionStatus } from "./tool-state";
export {
  TOOL_EXECUTION_STATUSES,
  ToolExecutionStatusSchema,
} from "./tool-state";
