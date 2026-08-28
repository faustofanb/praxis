import { z } from "zod";

/**
 * Effect classes for tools (docs/02 section 8.1). The class is recorded as a
 * fact on ToolProposed and drives recovery policy: only read_only effects may
 * fail fast; unknown outcomes of write effects must surface INDETERMINATE.
 */

export const TOOL_EFFECTS = [
  "read_only",
  "idempotent_write",
  "reconcilable_write",
  "non_idempotent_write",
] as const;
export type ToolEffect = (typeof TOOL_EFFECTS)[number];

export const ToolEffectSchema = z.enum(TOOL_EFFECTS);
