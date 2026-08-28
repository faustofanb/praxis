import { z } from "zod";

/**
 * Normalized model request boundary (docs/02 section 10, ADR-0010). Core
 * builds these messages; providers translate to their wire format. Tool
 * arguments travel as JSON strings — parsing owns to the tool runtime.
 */

export const ToolCallRequestSchema = z.object({
  id: z.string().min(1),
  name: z.string().min(1),
  argumentsJson: z.string(),
});
export type ToolCallRequest = z.infer<typeof ToolCallRequestSchema>;

export const SystemMessageSchema = z.object({
  role: z.literal("system"),
  text: z.string(),
});
export type SystemMessage = z.infer<typeof SystemMessageSchema>;

export const UserMessageSchema = z.object({
  role: z.literal("user"),
  text: z.string(),
});
export type UserMessage = z.infer<typeof UserMessageSchema>;

export const AssistantMessageSchema = z.object({
  role: z.literal("assistant"),
  text: z.string().optional(),
  toolCalls: z.array(ToolCallRequestSchema).optional(),
});
export type AssistantMessage = z.infer<typeof AssistantMessageSchema>;

export const ToolResultMessageSchema = z.object({
  role: z.literal("tool"),
  toolCallId: z.string().min(1),
  text: z.string(),
});
export type ToolResultMessage = z.infer<typeof ToolResultMessageSchema>;

export const ModelMessageSchema = z.discriminatedUnion("role", [
  SystemMessageSchema,
  UserMessageSchema,
  AssistantMessageSchema,
  ToolResultMessageSchema,
]);
export type ModelMessage = z.infer<typeof ModelMessageSchema>;

export const ModelToolDefinitionSchema = z.object({
  name: z.string().min(1),
  description: z.string(),
  parametersJson: z.string(),
});
export type ModelToolDefinition = z.infer<typeof ModelToolDefinitionSchema>;

export const ModelRequestSchema = z.object({
  model: z.string().min(1),
  messages: z.array(ModelMessageSchema).min(1),
  tools: z.array(ModelToolDefinitionSchema).optional(),
  maxOutputTokens: z.number().int().positive().optional(),
  providerOptions: z.record(z.string(), z.unknown()).optional(),
  correlationId: z.string().min(1).optional(),
});
export type ModelRequest = z.infer<typeof ModelRequestSchema>;
