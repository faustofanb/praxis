import { z } from "zod";

/**
 * Normalized model stream events (docs/02 section 10, ADR-0010). These are
 * transient stream events in camelCase, deliberately distinct from the
 * PascalCase durable event vocabulary of ADR-0009. `completed` and
 * `providerError` are terminal facts about one completion attempt.
 */

export const MODEL_PROVIDER_ERROR_KINDS = [
  "network",
  "rateLimit",
  "invalidRequest",
  "auth",
  "overloaded",
  "timeout",
  "unknown",
] as const;
export type ModelProviderErrorKind = (typeof MODEL_PROVIDER_ERROR_KINDS)[number];

export const ModelProviderErrorInfoSchema = z.object({
  kind: z.enum(MODEL_PROVIDER_ERROR_KINDS),
  retryable: z.boolean(),
  message: z.string(),
});
export type ModelProviderErrorInfo = z.infer<typeof ModelProviderErrorInfoSchema>;

export const TextDeltaEventSchema = z.object({
  type: z.literal("textDelta"),
  text: z.string(),
});
export type TextDeltaEvent = z.infer<typeof TextDeltaEventSchema>;

export const ToolCallStartEventSchema = z.object({
  type: z.literal("toolCallStart"),
  toolCallId: z.string().min(1),
  name: z.string().min(1),
});
export type ToolCallStartEvent = z.infer<typeof ToolCallStartEventSchema>;

export const ToolCallDeltaEventSchema = z.object({
  type: z.literal("toolCallDelta"),
  toolCallId: z.string().min(1),
  argumentsDelta: z.string(),
});
export type ToolCallDeltaEvent = z.infer<typeof ToolCallDeltaEventSchema>;

export const ToolCallEndEventSchema = z.object({
  type: z.literal("toolCallEnd"),
  toolCallId: z.string().min(1),
});
export type ToolCallEndEvent = z.infer<typeof ToolCallEndEventSchema>;

export const UsageEventSchema = z.object({
  type: z.literal("usage"),
  inputTokens: z.number().int().nonnegative(),
  outputTokens: z.number().int().nonnegative(),
});
export type UsageEvent = z.infer<typeof UsageEventSchema>;

export const MODEL_FINISH_REASONS = ["stop", "toolCalls", "length"] as const;
export type ModelFinishReason = (typeof MODEL_FINISH_REASONS)[number];

export const CompletedEventSchema = z.object({
  type: z.literal("completed"),
  finishReason: z.enum(MODEL_FINISH_REASONS),
});
export type CompletedEvent = z.infer<typeof CompletedEventSchema>;

export const ProviderErrorEventSchema = z.object({
  type: z.literal("providerError"),
  error: ModelProviderErrorInfoSchema,
});
export type ProviderErrorEvent = z.infer<typeof ProviderErrorEventSchema>;

export const ModelEventSchema = z.discriminatedUnion("type", [
  TextDeltaEventSchema,
  ToolCallStartEventSchema,
  ToolCallDeltaEventSchema,
  ToolCallEndEventSchema,
  UsageEventSchema,
  CompletedEventSchema,
  ProviderErrorEventSchema,
]);
export type ModelEvent = z.infer<typeof ModelEventSchema>;
