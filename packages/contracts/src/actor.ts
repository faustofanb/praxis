import { z } from "zod";
import { ToolExecutionIdSchema } from "./ids";

/**
 * Who caused a factual event (docs/02 §6.1 `EventActor`). The actor is
 * recorded truth, not an authorization decision.
 */

export const UserActorSchema = z.object({ kind: z.literal("user") });
export type UserActor = z.infer<typeof UserActorSchema>;

export const SystemActorSchema = z.object({ kind: z.literal("system") });
export type SystemActor = z.infer<typeof SystemActorSchema>;

export const ModelActorSchema = z.object({
  kind: z.literal("model"),
  provider: z.string().min(1),
  model: z.string().min(1),
});
export type ModelActor = z.infer<typeof ModelActorSchema>;

export const ToolActorSchema = z.object({
  kind: z.literal("tool"),
  toolExecutionId: ToolExecutionIdSchema,
});
export type ToolActor = z.infer<typeof ToolActorSchema>;

export const EventActorSchema = z.discriminatedUnion("kind", [
  UserActorSchema,
  SystemActorSchema,
  ModelActorSchema,
  ToolActorSchema,
]);
export type EventActor = z.infer<typeof EventActorSchema>;
