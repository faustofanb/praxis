import { z } from "zod";
import { sessionEventSchema } from "../envelope";
import { MODEL_PROVIDER_ERROR_KINDS } from "../model/events";
import { ToolCallRequestSchema } from "../model/request";

/**
 * v1 durable event vocabulary: the model-call slice (docs/02 section 6.2).
 * ModelResponseCompleted carries the assistant output (text and/or tool
 * calls) as facts so conversation can be rebuilt from the stream alone;
 * ModelRequestFailed carries the normalized provider failure for guard and
 * recovery decisions. Streaming deltas are NOT durable events.
 */

export const MODEL_REQUEST_STARTED = "ModelRequestStarted";
export const MODEL_RESPONSE_COMPLETED = "ModelResponseCompleted";
export const MODEL_REQUEST_FAILED = "ModelRequestFailed";

export const MODEL_EVENT_TYPES = [
  MODEL_REQUEST_STARTED,
  MODEL_RESPONSE_COMPLETED,
  MODEL_REQUEST_FAILED,
] as const;
export type ModelEventType = (typeof MODEL_EVENT_TYPES)[number];

export const ModelRequestStartedPayloadSchema = z.object({
  model: z.string().min(1),
});
export const ModelRequestStartedEventSchema = sessionEventSchema(
  MODEL_REQUEST_STARTED,
  ModelRequestStartedPayloadSchema,
);
export type ModelRequestStartedEvent = z.infer<typeof ModelRequestStartedEventSchema>;

export const ModelResponseCompletedPayloadSchema = z.object({
  text: z.string().optional(),
  toolCalls: z.array(ToolCallRequestSchema).default([]),
});
export const ModelResponseCompletedEventSchema = sessionEventSchema(
  MODEL_RESPONSE_COMPLETED,
  ModelResponseCompletedPayloadSchema,
);
export type ModelResponseCompletedEvent = z.infer<typeof ModelResponseCompletedEventSchema>;

export const ModelRequestFailedPayloadSchema = z.object({
  kind: z.enum(MODEL_PROVIDER_ERROR_KINDS),
  retryable: z.boolean(),
  message: z.string().min(1),
});
export const ModelRequestFailedEventSchema = sessionEventSchema(
  MODEL_REQUEST_FAILED,
  ModelRequestFailedPayloadSchema,
);
export type ModelRequestFailedEvent = z.infer<typeof ModelRequestFailedEventSchema>;

export const MODEL_EVENT_SCHEMAS = [
  ModelRequestStartedEventSchema,
  ModelResponseCompletedEventSchema,
  ModelRequestFailedEventSchema,
] as const;
