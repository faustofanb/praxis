import { z } from "zod";
import { EventActorSchema } from "./actor";
import { EventIdSchema, SessionIdSchema } from "./ids";

/**
 * Event envelope (docs/02 §6.1). Events are facts; the envelope carries
 * identity, ordering, actor, and causality for every payload type.
 *
 * Invariants (enforced by the EventStore port and Core, not by parsing a
 * single event): (sessionId, seq) unique, seq starts at 1 and is monotonic
 * without gaps, events are immutable, and replay has no side effects.
 */

export const EVENT_SCHEMA_VERSION = 1;

/**
 * Bare envelope fields shared by every session event. Exported so the
 * versioned replay seam (`./replay`) can validate envelope identity —
 * including the schemaVersion window — before payload parsing.
 */
export const EventEnvelopeBaseSchema = z.object({
  id: EventIdSchema,
  sessionId: SessionIdSchema,
  seq: z.number().int().positive(),
  schemaVersion: z.number().int().positive(),
  occurredAt: z.number().int().nonnegative(),
  actor: EventActorSchema,
  causationId: EventIdSchema.optional(),
  correlationId: z.string().min(1).optional(),
});

/** Bare envelope fields shared by every session event. */
export type EventEnvelopeBase = z.infer<typeof EventEnvelopeBaseSchema>;

/**
 * Generic event shape for consumers that already know the payload type.
 * Payload validation itself is owned by the per-type schemas in
 * `./events/session-events`.
 */
export type SessionEvent<TType extends string, TPayload> = Omit<
  EventEnvelopeBase,
  "type" | "payload"
> & {
  type: TType;
  payload: TPayload;
};

/**
 * Build the envelope schema for one concrete event type. `type` is a literal
 * so the resulting discriminated union narrows payload access by `event.type`.
 */
export function sessionEventSchema<TType extends string, TPayloadSchema extends z.ZodType>(
  type: TType,
  payloadSchema: TPayloadSchema,
) {
  return EventEnvelopeBaseSchema.extend({
    type: z.literal(type),
    payload: payloadSchema,
  });
}
