import { z } from "zod";
import { sessionEventSchema } from "../envelope";
import { ToolExecutionIdSchema } from "../ids";
import { ToolEffectSchema } from "../tools/tool-effect";

/**
 * v1 durable event vocabulary: the tool execution lifecycle slice
 * (docs/02 section 8.2). Tool results enter the stream as facts here; how the
 * model sees them is decided later by the ContextBuilder, never by replay.
 *
 * State machine (hard rules in docs/02 section 8.2):
 * ToolProposed -> ToolAuthorized -> ToolStarted -> ToolSucceeded |
 * ToolFailed | ToolIndeterminate, with ToolProposed -> ToolRejected as the
 * pre-execution denial path. INDETERMINATE is a first-class outcome, never
 * coerced to FAILED, and is the only state ToolReconciled may settle; it may
 * be reconciled repeatedly while it stays indeterminate. SUCCEEDED and FAILED
 * are terminal whether reached by execution or by reconciliation — terminals
 * never resurrect.
 */

export const TOOL_PROPOSED = "ToolProposed";
export const TOOL_AUTHORIZED = "ToolAuthorized";
export const TOOL_REJECTED = "ToolRejected";
export const TOOL_STARTED = "ToolStarted";
export const TOOL_SUCCEEDED = "ToolSucceeded";
export const TOOL_FAILED = "ToolFailed";
export const TOOL_INDETERMINATE = "ToolIndeterminate";
export const TOOL_RECONCILED = "ToolReconciled";

export const TOOL_EVENT_TYPES = [
  TOOL_PROPOSED,
  TOOL_AUTHORIZED,
  TOOL_REJECTED,
  TOOL_STARTED,
  TOOL_SUCCEEDED,
  TOOL_FAILED,
  TOOL_INDETERMINATE,
  TOOL_RECONCILED,
] as const;
export type ToolEventType = (typeof TOOL_EVENT_TYPES)[number];

export const ToolProposedPayloadSchema = z.object({
  toolExecutionId: ToolExecutionIdSchema,
  name: z.string().min(1),
  argumentsJson: z.string(),
  effect: ToolEffectSchema,
  /** Correlates the proposal with the model tool call that caused it. */
  toolCallId: z.string().min(1).optional(),
});
export const ToolProposedEventSchema = sessionEventSchema(TOOL_PROPOSED, ToolProposedPayloadSchema);
export type ToolProposedEvent = z.infer<typeof ToolProposedEventSchema>;

export const ToolAuthorizedPayloadSchema = z.object({
  toolExecutionId: ToolExecutionIdSchema,
});
export const ToolAuthorizedEventSchema = sessionEventSchema(
  TOOL_AUTHORIZED,
  ToolAuthorizedPayloadSchema,
);
export type ToolAuthorizedEvent = z.infer<typeof ToolAuthorizedEventSchema>;

export const ToolRejectedPayloadSchema = z.object({
  toolExecutionId: ToolExecutionIdSchema,
  reason: z.string().min(1),
});
export const ToolRejectedEventSchema = sessionEventSchema(TOOL_REJECTED, ToolRejectedPayloadSchema);
export type ToolRejectedEvent = z.infer<typeof ToolRejectedEventSchema>;

export const ToolStartedPayloadSchema = z.object({
  toolExecutionId: ToolExecutionIdSchema,
});
export const ToolStartedEventSchema = sessionEventSchema(TOOL_STARTED, ToolStartedPayloadSchema);
export type ToolStartedEvent = z.infer<typeof ToolStartedEventSchema>;

export const ToolSucceededPayloadSchema = z.object({
  toolExecutionId: ToolExecutionIdSchema,
  resultJson: z.string(),
});
export const ToolSucceededEventSchema = sessionEventSchema(
  TOOL_SUCCEEDED,
  ToolSucceededPayloadSchema,
);
export type ToolSucceededEvent = z.infer<typeof ToolSucceededEventSchema>;

export const ToolFailedPayloadSchema = z.object({
  toolExecutionId: ToolExecutionIdSchema,
  message: z.string().min(1),
});
export const ToolFailedEventSchema = sessionEventSchema(TOOL_FAILED, ToolFailedPayloadSchema);
export type ToolFailedEvent = z.infer<typeof ToolFailedEventSchema>;

export const ToolIndeterminatePayloadSchema = z.object({
  toolExecutionId: ToolExecutionIdSchema,
  reason: z.string().min(1),
});
export const ToolIndeterminateEventSchema = sessionEventSchema(
  TOOL_INDETERMINATE,
  ToolIndeterminatePayloadSchema,
);
export type ToolIndeterminateEvent = z.infer<typeof ToolIndeterminateEventSchema>;

/**
 * The reconciliation fact (docs/02 sections 8.2-8.3): what a reconciliation
 * attempt provably established about an INDETERMINATE execution. Each variant
 * must state proof, not hope — `succeeded`/`failed` assert the effect did /
 * did not happen; anything short of proof stays `indeterminate`.
 */
export const ToolReconciledPayloadSchema = z.discriminatedUnion("outcome", [
  z.object({
    toolExecutionId: ToolExecutionIdSchema,
    outcome: z.literal("succeeded"),
    resultJson: z.string(),
  }),
  z.object({
    toolExecutionId: ToolExecutionIdSchema,
    outcome: z.literal("failed"),
    message: z.string().min(1),
  }),
  z.object({
    toolExecutionId: ToolExecutionIdSchema,
    outcome: z.literal("indeterminate"),
    reason: z.string().min(1),
  }),
]);
export type ToolReconciledPayload = z.infer<typeof ToolReconciledPayloadSchema>;
export const ToolReconciledEventSchema = sessionEventSchema(
  TOOL_RECONCILED,
  ToolReconciledPayloadSchema,
);
export type ToolReconciledEvent = z.infer<typeof ToolReconciledEventSchema>;

export const TOOL_EVENT_SCHEMAS = [
  ToolProposedEventSchema,
  ToolAuthorizedEventSchema,
  ToolRejectedEventSchema,
  ToolStartedEventSchema,
  ToolSucceededEventSchema,
  ToolFailedEventSchema,
  ToolIndeterminateEventSchema,
  ToolReconciledEventSchema,
] as const;
