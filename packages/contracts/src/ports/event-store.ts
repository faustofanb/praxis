import type { SessionEventUnion } from "../events/session-events";
import type { SessionId } from "../ids";

/**
 * Port: append-only durable event store (ADR-0003, docs/02 §4.1).
 *
 * Contract for any adapter implementing this port:
 *
 * - `append` is atomic: either every event persists or none does.
 * - `(sessionId, seq)` is unique; seq starts at 1, is monotonic, and has no
 *   gaps within a session.
 * - `expectedHeadSeq` is the seq of the current last event of the session
 *   (0 for an empty stream) and enables optimistic concurrency: if the
 *   stored head differs, the adapter throws `EventStoreConflictError` and
 *   writes nothing.
 * - Events are immutable; there is no update or delete.
 * - `readStream` returns the session's events with seq strictly greater than
 *   `afterSeq` (default 0 = the whole stream), ordered by seq. Seq, not
 *   occurredAt, is the ordering authority.
 * - Reading and appending must never execute tool side effects; replay is
 *   pure reconstruction.
 */

export const EMPTY_STREAM_HEAD_SEQ = 0;

export class EventStoreConflictError extends Error {
  constructor(
    readonly sessionId: SessionId,
    readonly expectedHeadSeq: number,
    readonly actualHeadSeq: number,
  ) {
    super(
      `Event store conflict for session ${sessionId}: expected head seq ${expectedHeadSeq}, actual ${actualHeadSeq}`,
    );
    this.name = "EventStoreConflictError";
  }
}

export interface EventStore {
  append(events: readonly SessionEventUnion[], expectedHeadSeq: number): Promise<void>;
  readStream(sessionId: SessionId, afterSeq?: number): Promise<readonly SessionEventUnion[]>;
}
