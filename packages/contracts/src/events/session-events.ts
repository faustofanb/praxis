import { z } from "zod";
import { sessionEventSchema } from "../envelope";
import { TurnIdSchema } from "../ids";
import { EPISTEMIC_EVENT_SCHEMAS } from "./epistemic-events";
import { MODEL_EVENT_SCHEMAS } from "./model-events";
import { TOOL_EVENT_SCHEMAS } from "./tool-events";

/**
 * v1 durable event vocabulary: the Session/Turn lifecycle slice
 * (docs/02 §6.2, ADR-0009), the tool execution lifecycle slice
 * (docs/02 §8.2, joined in M2-T003), the model-call slice
 * (docs/02 §6.2, joined in M2-T004), and the Goal/Epistemic slice
 * (docs/02 §5/§6.2, joined in M4-T001 per ADR-0012).
 */

export const SESSION_CREATED = "SessionCreated";
export const SESSION_RESUMED = "SessionResumed";
export const SESSION_PAUSED = "SessionPaused";
export const SESSION_COMPLETED = "SessionCompleted";
export const TURN_STARTED = "TurnStarted";
export const TURN_COMPLETED = "TurnCompleted";

export const SESSION_EVENT_TYPES = [
  SESSION_CREATED,
  SESSION_RESUMED,
  SESSION_PAUSED,
  SESSION_COMPLETED,
  TURN_STARTED,
  TURN_COMPLETED,
] as const;
export type SessionEventType = (typeof SESSION_EVENT_TYPES)[number];

export const SessionCreatedPayloadSchema = z.object({
  reason: z.string().min(1).optional(),
});
export const SessionCreatedEventSchema = sessionEventSchema(
  SESSION_CREATED,
  SessionCreatedPayloadSchema,
);
export type SessionCreatedEvent = z.infer<typeof SessionCreatedEventSchema>;

export const SessionResumedPayloadSchema = z.object({});
export const SessionResumedEventSchema = sessionEventSchema(
  SESSION_RESUMED,
  SessionResumedPayloadSchema,
);
export type SessionResumedEvent = z.infer<typeof SessionResumedEventSchema>;

export const SessionPausedPayloadSchema = z.object({});
export const SessionPausedEventSchema = sessionEventSchema(
  SESSION_PAUSED,
  SessionPausedPayloadSchema,
);
export type SessionPausedEvent = z.infer<typeof SessionPausedEventSchema>;

export const SessionCompletedPayloadSchema = z.object({});
export const SessionCompletedEventSchema = sessionEventSchema(
  SESSION_COMPLETED,
  SessionCompletedPayloadSchema,
);
export type SessionCompletedEvent = z.infer<typeof SessionCompletedEventSchema>;

export const TurnStartedPayloadSchema = z.object({
  turnId: TurnIdSchema,
  /** User input that opened the turn, so conversation survives replay. */
  input: z.string().optional(),
});
export const TurnStartedEventSchema = sessionEventSchema(TURN_STARTED, TurnStartedPayloadSchema);
export type TurnStartedEvent = z.infer<typeof TurnStartedEventSchema>;

export const TurnCompletedPayloadSchema = z.object({
  turnId: TurnIdSchema,
});
export const TurnCompletedEventSchema = sessionEventSchema(
  TURN_COMPLETED,
  TurnCompletedPayloadSchema,
);
export type TurnCompletedEvent = z.infer<typeof TurnCompletedEventSchema>;

export const SessionEventUnionSchema = z.discriminatedUnion("type", [
  SessionCreatedEventSchema,
  SessionResumedEventSchema,
  SessionPausedEventSchema,
  SessionCompletedEventSchema,
  TurnStartedEventSchema,
  TurnCompletedEventSchema,
  ...TOOL_EVENT_SCHEMAS,
  ...MODEL_EVENT_SCHEMAS,
  ...EPISTEMIC_EVENT_SCHEMAS,
]);
export type SessionEventUnion = z.infer<typeof SessionEventUnionSchema>;
