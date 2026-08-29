import type { EventStore, SessionEventUnion } from "@praxis/contracts";
import { EMPTY_STREAM_HEAD_SEQ, EventStoreConflictError } from "@praxis/contracts";

/**
 * Test-only in-memory EventStore implementing the contracts port semantics:
 * atomic batch append, (sessionId, seq) uniqueness via continuity, gap-free
 * sequences, and optimistic concurrency via expectedHeadSeq.
 */
export function inMemoryEventStore(): EventStore {
  const streams = new Map<string, SessionEventUnion[]>();
  return {
    async append(events, expectedHeadSeq) {
      const first = events[0];
      if (first === undefined) {
        return;
      }
      const sessionId = first.sessionId;
      if (events.some((event) => event.sessionId !== sessionId)) {
        throw new Error("append batch spans multiple sessions");
      }
      const stream = streams.get(sessionId) ?? [];
      const head = stream.at(-1)?.seq ?? EMPTY_STREAM_HEAD_SEQ;
      if (head !== expectedHeadSeq) {
        throw new EventStoreConflictError(sessionId, expectedHeadSeq, head);
      }
      let next = head;
      for (const event of events) {
        if (event.seq !== next + 1) {
          throw new Error(
            `append breaks stream continuity: expected seq ${next + 1}, got ${event.seq}`,
          );
        }
        next = event.seq;
        stream.push(event);
      }
      streams.set(sessionId, stream);
    },
    async readStream(sessionId, afterSeq = EMPTY_STREAM_HEAD_SEQ) {
      return (streams.get(sessionId) ?? []).filter((event) => event.seq > afterSeq);
    },
  };
}
