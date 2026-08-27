import { z } from "zod";
import { sessionEventSchema } from "../envelope";
import { TurnIdSchema } from "../ids";

/**
 * v1 durable event vocabulary: the Session/Turn lifecycle slice only
 * (docs/02 §6.2, ADR-0009). Model-call, evidence, and tool-execution events
 * join this union as schema-versioned members in M2–M4.
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
]);
export type SessionEventUnion = z.infer<typeof SessionEventUnionSchema>;
