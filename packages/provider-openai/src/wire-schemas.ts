import { z } from "zod";

/**
 * Wire schemas for the OpenAI-compatible Chat Completions boundary, verified
 * against the openai-node types (generated from the OpenAPI spec). These are
 * the owning schemas for a third-party boundary: everything arriving from the
 * network is parsed from `unknown` here; unknown fields are stripped, never
 * trusted (AGENTS.md parse rule).
 */

const WireToolCallDeltaSchema = z.object({
  index: z.number().int().nonnegative(),
  id: z.string().min(1).optional(),
  function: z
    .object({
      name: z.string().min(1).optional(),
      arguments: z.string().optional(),
    })
    .optional(),
});
export type WireToolCallDelta = z.infer<typeof WireToolCallDeltaSchema>;

const WireDeltaSchema = z.object({
  content: z.string().optional(),
  tool_calls: z.array(WireToolCallDeltaSchema).optional(),
});

const WireChoiceSchema = z.object({
  delta: WireDeltaSchema,
  finish_reason: z.string().nullable().optional(),
});

const WireUsageSchema = z.object({
  prompt_tokens: z.number().int().nonnegative(),
  completion_tokens: z.number().int().nonnegative(),
});

export const WireChunkSchema = z.object({
  choices: z.array(WireChoiceSchema).default([]),
  usage: WireUsageSchema.nullish(),
});

/** Best-effort error body shape; providers differ, so everything is optional. */
export const WireErrorBodySchema = z.object({
  error: z
    .object({
      message: z.string().optional(),
      type: z.string().optional(),
    })
    .optional(),
});
