import type { ToolDefinition, ToolEffect } from "@praxis/contracts";

/**
 * Effect-class contract enforcement (ADR-0006, docs/02 sections 8.2-8.3 and
 * 17). Pure tables and validation only — no I/O, no state. The runtime
 * (recovery orchestration, M3-T004) consumes these; they are what keeps
 * indeterminate-effect handling from depending on model self-discipline.
 */

/**
 * What the runtime may do with a tool whose previous execution ended
 * INDETERMINATE, before reconciliation says otherwise:
 *
 * - `safe_to_repeat` — the effect class itself makes re-execution harmless
 *   (read-only work, or a write whose idempotency the tool declares).
 * - `repeat_only_after_reconciled_absence` — re-execution is unlocked only by
 *   a ToolReconciled `failed` fact proving the effect never happened.
 * - `never_repeat` — no automatic re-execution, whatever reconciliation
 *   finds; repeating is a human escalation decision.
 */
export type EffectRetryPolicy =
  | "safe_to_repeat"
  | "repeat_only_after_reconciled_absence"
  | "never_repeat";

const RETRY_POLICIES: Readonly<Record<ToolEffect, EffectRetryPolicy>> = {
  read_only: "safe_to_repeat",
  idempotent_write: "safe_to_repeat",
  reconcilable_write: "repeat_only_after_reconciled_absence",
  non_idempotent_write: "never_repeat",
};

/** Total over TOOL_EFFECTS by construction: a new class breaks compilation. */
export function retryPolicyForEffect(effect: ToolEffect): EffectRetryPolicy {
  return RETRY_POLICIES[effect];
}

/**
 * Registration-time enforcement of ADR-0006 ("writes must define idempotency
 * and/or reconciliation behavior before merge") and ADR-0007 (capability
 * enforcement is Core, never prompt or tool-author discipline):
 *
 * - `reconcilable_write` promises reconciliation, so a definition without
 *   `reconcile` is rejected — the class name would be a lie.
 * - `non_idempotent_write` with `reconcile` is legal: reconciliation there
 *   settles facts for escalation; it never unlocks repetition, and the retry
 *   policy stays `never_repeat` regardless.
 * - every write-effect tool must declare `requiredCapability`; a write that
 *   polices itself would be prompt-only security.
 * - duplicate names would make registry lookup ambiguous.
 *
 * Throws Error on the first violation; callers run this before any tool is
 * executable.
 */
export function validateToolDefinitions(tools: readonly ToolDefinition[]): void {
  const names = new Set<string>();
  for (const tool of tools) {
    if (names.has(tool.name)) {
      throw new Error(`duplicate tool definition: ${tool.name}`);
    }
    names.add(tool.name);
    if (tool.effect === "reconcilable_write" && tool.reconcile === undefined) {
      throw new Error(
        `tool ${tool.name} declares effect reconcilable_write but defines no reconcile`,
      );
    }
    if (tool.effect !== "read_only" && tool.requiredCapability === undefined) {
      throw new Error(
        `tool ${tool.name} has effect ${tool.effect} but declares no requiredCapability`,
      );
    }
  }
}
