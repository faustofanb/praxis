import type { z } from "zod";
import type { CapabilityRequirement } from "../capability/capability";
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

/**
 * What a reconciliation attempt provably established about an INDETERMINATE
 * execution (docs/02 sections 8.3 and 17). Same epistemic rule as
 * ToolExecutionOutcome: `succeeded`/`failed` assert the external effect did /
 * did not happen; anything short of proof stays `indeterminate`. The result
 * lands in the stream as a ToolReconciled event.
 */
export type ReconciliationOutcome =
  | { status: "succeeded"; resultJson: string }
  | { status: "failed"; error: { message: string } }
  | { status: "indeterminate"; reason: string };

export interface ToolDefinition {
  readonly name: string;
  readonly description: string;
  readonly effect: ToolEffect;
  /**
   * Capability this tool needs before it may execute (docs/02 section 9).
   * Required for every write-effect tool — registration rejects a write tool
   * without one, so enforcement never depends on tool-author discipline.
   * Read-only tools may omit it.
   */
  readonly requiredCapability?: CapabilityRequirement;
  readonly inputSchema: z.ZodType<unknown>;
  /**
   * JSON-encoded JSON Schema advertised to the model (the parametersJson of
   * ModelToolDefinition). Must be valid JSON; Core never parses it, providers
   * pass it through verbatim.
   */
  readonly parametersJson: string;
  execute(context: ToolExecutionContext, input: unknown): Promise<ToolExecutionOutcome>;
  /**
   * Optional reconciliation for write effects (ADR-0006). Required for
   * `reconcilable_write` tools — registration rejects the definition without
   * it. Receives the same parsed input as `execute` so it can look up the
   * external object (idempotency key, provider-side state) and compare
   * expected versus actual.
   *
   * Contract rules:
   *
   * - Reconciliation verifies; it must not perform new external effects.
   * - It runs only after the execution is INDETERMINATE, and replay never
   *   calls it (its conclusion is already a ToolReconciled fact).
   * - Returning `failed` asserts the effect provably never happened; it is
   *   the only outcome that can unlock re-execution, and only for effects
   *   whose retry policy allows repeating.
   */
  reconcile?(context: ToolExecutionContext, input: unknown): Promise<ReconciliationOutcome>;
}
