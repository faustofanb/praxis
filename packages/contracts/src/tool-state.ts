import { z } from "zod";

/**
 * Tool execution status (docs/02 §8.2). Transition legality is enforced by
 * the Core reducer, not here. Key epistemic rule: a timeout or uncertain
 * external effect is INDETERMINATE, never auto-FAILED, and blind retry of a
 * non-idempotent write from INDETERMINATE is forbidden.
 */

export const TOOL_EXECUTION_STATUSES = [
  "PROPOSED",
  "AUTHORIZED",
  "REJECTED",
  "EXECUTING",
  "SUCCEEDED",
  "FAILED",
  "INDETERMINATE",
] as const;
export type ToolExecutionStatus = (typeof TOOL_EXECUTION_STATUSES)[number];

export const ToolExecutionStatusSchema = z.enum(TOOL_EXECUTION_STATUSES);
