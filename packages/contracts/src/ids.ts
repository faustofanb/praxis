import { z } from "zod";

/**
 * Branded IDs (docs/02 §4.1). Contracts only validates and brands; generating
 * fresh IDs involves randomness and belongs to adapters/CLI, deterministic
 * generators to packages/testkit.
 */

export const SessionIdSchema = z.string().min(1).brand<"SessionId">();
export type SessionId = z.infer<typeof SessionIdSchema>;
export function asSessionId(value: string): SessionId {
  return SessionIdSchema.parse(value);
}

export const EventIdSchema = z.string().min(1).brand<"EventId">();
export type EventId = z.infer<typeof EventIdSchema>;
export function asEventId(value: string): EventId {
  return EventIdSchema.parse(value);
}

export const TurnIdSchema = z.string().min(1).brand<"TurnId">();
export type TurnId = z.infer<typeof TurnIdSchema>;
export function asTurnId(value: string): TurnId {
  return TurnIdSchema.parse(value);
}

export const StepIdSchema = z.string().min(1).brand<"StepId">();
export type StepId = z.infer<typeof StepIdSchema>;
export function asStepId(value: string): StepId {
  return StepIdSchema.parse(value);
}

export const ToolExecutionIdSchema = z.string().min(1).brand<"ToolExecutionId">();
export type ToolExecutionId = z.infer<typeof ToolExecutionIdSchema>;
export function asToolExecutionId(value: string): ToolExecutionId {
  return ToolExecutionIdSchema.parse(value);
}
