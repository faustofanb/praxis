import type { z } from "zod";
import type { ToolEffect } from "../tools/tool-effect";

/**
 * Tool port (docs/02 section 8.1). Adapters implement this; Core drives the
 * lifecycle and owns the events. The runtime treats tool results as opaque
 * JSON facts — it never parses resultJson.
 *
 * Contract rules:
 *
 * - `execute` runs at most once per ToolStarted event; replay never calls it.
 * - A returned `failed` outcome must mean the effect provably did not happen;
 *   if the outcome is unknowable, return `indeterminate` instead. Never
 *   coerce unknown to failed.
 * - `inputSchema` parses from `unknown` at the runtime boundary; malformed
 *   input is rejected before any execute call.
 * - `context.signal` is the turn's cancellation signal; read-only tools may
 *   fail fast on abort, write-capable tools must not assume failure means
 *   "no effect happened".
 */

export interface ToolExecutionContext {
  readonly signal: AbortSignal;
}

export type ToolExecutionOutcome =
  | { status: "succeeded"; resultJson: string }
  | { status: "failed"; error: { message: string } }
  | { status: "indeterminate"; reason: string };

export interface ToolDefinition {
  readonly name: string;
  readonly description: string;
  readonly effect: ToolEffect;
  readonly inputSchema: z.ZodType<unknown>;
  execute(context: ToolExecutionContext, input: unknown): Promise<ToolExecutionOutcome>;
}
