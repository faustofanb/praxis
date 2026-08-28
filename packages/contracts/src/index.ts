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
export type {
  CompletedEvent,
  ModelEvent,
  ModelFinishReason,
  ModelProviderErrorInfo,
  ModelProviderErrorKind,
  ProviderErrorEvent,
  TextDeltaEvent,
  ToolCallDeltaEvent,
  ToolCallEndEvent,
  ToolCallStartEvent,
  UsageEvent,
} from "./model/events";
export {
  CompletedEventSchema,
  MODEL_FINISH_REASONS,
  MODEL_PROVIDER_ERROR_KINDS,
  ModelEventSchema,
  ModelProviderErrorInfoSchema,
  ProviderErrorEventSchema,
  TextDeltaEventSchema,
  ToolCallDeltaEventSchema,
  ToolCallEndEventSchema,
  ToolCallStartEventSchema,
  UsageEventSchema,
} from "./model/events";
export type { ModelProvider } from "./model/provider";
export type {
  AssistantMessage,
  ModelMessage,
  ModelRequest,
  ModelToolDefinition,
  SystemMessage,
  ToolCallRequest,
  ToolResultMessage,
  UserMessage,
} from "./model/request";
export {
  AssistantMessageSchema,
  ModelMessageSchema,
  ModelRequestSchema,
  ModelToolDefinitionSchema,
  SystemMessageSchema,
  ToolCallRequestSchema,
  ToolResultMessageSchema,
  UserMessageSchema,
} from "./model/request";
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
