import type {
  EventActor,
  EventId,
  EventStore,
  SessionEventUnion,
  SessionId,
} from "@praxis/contracts";
import { EVENT_SCHEMA_VERSION } from "@praxis/contracts";
import type { DerivedSessionState } from "../state/reducer";
import { foldSessionEvents } from "../state/reducer";

/**
 * Single-writer append shared by the agent loop and recovery orchestration:
 * every event is sequenced from the current head and appended under an
 * expected head seq, then the derived state is re-folded from the stream —
 * never mutated locally.
 */

export type EventAppenderDeps = {
  readonly store: EventStore;
  readonly sessionId: SessionId;
  readonly now: () => number;
  readonly newEventId: () => EventId;
  readonly actor?: EventActor;
};

export function eventEnvelope(deps: EventAppenderDeps): {
  id: EventId;
  sessionId: SessionId;
  schemaVersion: number;
  occurredAt: number;
  actor: EventActor;
} {
  return {
    id: deps.newEventId(),
    sessionId: deps.sessionId,
    schemaVersion: EVENT_SCHEMA_VERSION,
    occurredAt: deps.now(),
    actor: deps.actor ?? { kind: "system" },
  };
}

export async function appendEvent(
  deps: EventAppenderDeps,
  init: Omit<SessionEventUnion, "seq">,
): Promise<DerivedSessionState> {
  const head = foldSessionEvents(await deps.store.readStream(deps.sessionId)).headSeq;
  const event = { ...init, seq: head + 1 } as SessionEventUnion;
  await deps.store.append([event], head);
  return foldSessionEvents(await deps.store.readStream(deps.sessionId));
}
