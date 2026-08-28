import type { Database, Statement } from "bun:sqlite";
import type { EventStore, SessionEventUnion, SessionId } from "@praxis/contracts";
import {
  asSessionId,
  EMPTY_STREAM_HEAD_SEQ,
  EventStoreConflictError,
  SessionEventUnionSchema,
} from "@praxis/contracts";

/**
 * Local SQLite EventStore adapter implementing the contracts port.
 *
 * - append is one transaction: session head check (optimistic concurrency),
 *   gap-free seq enforcement, event inserts, and head_seq/status metadata
 *   update all commit or roll back together.
 * - readStream re-validates every row through SessionEventUnionSchema:
 *   persisted bytes are an untrusted boundary, never coerced.
 * - append-only: this class exposes no UPDATE/DELETE path for events.
 * - sessions rows are metadata cache, created lazily by the first append;
 *   facts stay authoritative in events.
 */

type SessionRow = {
  head_seq: number;
  status: string;
};

type SessionListRow = {
  id: string;
  head_seq: number;
  status: string;
  updated_at: number;
};

/** Metadata projection for listing; facts stay authoritative in events. */
export type SessionSummary = {
  readonly sessionId: SessionId;
  readonly status: string;
  readonly headSeq: number;
  readonly updatedAt: number;
};

const STATUS_BY_EVENT: Partial<Record<SessionEventUnion["type"], string>> = {
  SessionCreated: "ACTIVE",
  SessionResumed: "ACTIVE",
  SessionPaused: "PAUSED",
  SessionCompleted: "COMPLETED",
};

export class SqliteEventStore implements EventStore {
  private readonly insertEvent: Statement;
  private readonly selectSession: Statement;
  private readonly insertSession: Statement;
  private readonly updateSession: Statement;
  private readonly selectEvents: Statement;
  private readonly selectSessionList: Statement;

  constructor(private readonly db: Database) {
    this.insertEvent = db.prepare(`
      INSERT INTO events (
        id, session_id, seq, type, schema_version, occurred_at,
        actor_json, causation_id, correlation_id, payload_json
      ) VALUES (
        $id, $sessionId, $seq, $type, $schemaVersion, $occurredAt,
        $actorJson, $causationId, $correlationId, $payloadJson
      );
    `);
    this.selectSession = db.prepare("SELECT head_seq, status FROM sessions WHERE id = $sessionId;");
    this.insertSession = db.prepare(`
      INSERT INTO sessions (id, created_at, updated_at, head_seq, status)
      VALUES ($sessionId, $occurredAt, $updatedAt, $headSeq, $status);
    `);
    this.updateSession = db.prepare(`
      UPDATE sessions
      SET head_seq = $headSeq, updated_at = $updatedAt, status = $status
      WHERE id = $sessionId;
    `);
    this.selectEvents = db.prepare(`
      SELECT id, session_id, seq, type, schema_version, occurred_at,
             actor_json, causation_id, correlation_id, payload_json
      FROM events
      WHERE session_id = $sessionId AND seq > $afterSeq
      ORDER BY seq ASC;
    `);
    this.appendTx = db.transaction(this.#appendWithinTransaction);
    this.selectSessionList = db.prepare(`
      SELECT id, head_seq, status, updated_at FROM sessions
      ORDER BY updated_at ASC, id ASC;
    `);
  }

  private readonly appendTx: (
    events: readonly SessionEventUnion[],
    expectedHeadSeq: number,
  ) => void;

  async append(events: readonly SessionEventUnion[], expectedHeadSeq: number): Promise<void> {
    const first = events[0];
    if (first === undefined) {
      return;
    }
    if (events.some((event) => event.sessionId !== first.sessionId)) {
      throw new Error("append batch spans multiple sessions");
    }
    this.appendTx(events, expectedHeadSeq);
  }

  async readStream(
    sessionId: SessionId,
    afterSeq: number = EMPTY_STREAM_HEAD_SEQ,
  ): Promise<readonly SessionEventUnion[]> {
    const rows = this.selectEvents.all({
      sessionId: sessionId.valueOf(),
      afterSeq,
    }) as unknown as Array<EventRow>;
    return rows.map(rowToEvent);
  }

  listSessions(): readonly SessionSummary[] {
    const rows = this.selectSessionList.all() as unknown as Array<SessionListRow>;
    return rows.map((row) => ({
      sessionId: asSessionId(row.id),
      status: row.status,
      headSeq: row.head_seq,
      updatedAt: row.updated_at,
    }));
  }

  close(): void {
    this.db.close();
  }

  // #private keeps the transaction body off the public prototype surface.
  readonly #appendWithinTransaction = (
    events: readonly SessionEventUnion[],
    expectedHeadSeq: number,
  ): void => {
    const sessionId = events[0]?.sessionId;
    if (sessionId === undefined) {
      return;
    }
    const existing = this.selectSession.get({
      sessionId: sessionId.valueOf(),
    }) as unknown as SessionRow | null;
    const head = existing?.head_seq ?? EMPTY_STREAM_HEAD_SEQ;

    if (head !== expectedHeadSeq) {
      throw new EventStoreConflictError(sessionId, expectedHeadSeq, head);
    }

    const firstEvent = events[0];
    if (firstEvent === undefined) {
      return;
    }
    // The events FK needs the sessions row to exist first; for a new stream
    // insert a provisional row (head 0) and let the mandatory update below
    // finalize it — all within this transaction, so nothing in between is
    // observable.
    if (existing === null) {
      this.insertSession.run({
        sessionId: sessionId.valueOf(),
        occurredAt: firstEvent.occurredAt,
        updatedAt: firstEvent.occurredAt,
        headSeq: EMPTY_STREAM_HEAD_SEQ,
        status: "ACTIVE",
      });
    }
    let next = head;
    let status = existing?.status ?? "ACTIVE";
    for (const event of events) {
      if (event.seq !== next + 1) {
        throw new Error(
          `append breaks stream continuity: expected seq ${next + 1}, got ${event.seq}`,
        );
      }
      const mapped = STATUS_BY_EVENT[event.type];
      if (mapped !== undefined) {
        status = mapped;
      }
      this.insertEvent.run(toRow(event));
      next = event.seq;
    }

    const lastEvent = events.at(-1);
    if (lastEvent === undefined) {
      return;
    }
    this.updateSession.run({
      sessionId: sessionId.valueOf(),
      updatedAt: lastEvent.occurredAt,
      headSeq: next,
      status,
    });
  };
}

type EventRow = {
  id: string;
  session_id: string;
  seq: number;
  type: string;
  schema_version: number;
  occurred_at: number;
  actor_json: string;
  causation_id: string | null;
  correlation_id: string | null;
  payload_json: string;
};

function toRow(event: SessionEventUnion) {
  return {
    id: event.id.valueOf(),
    sessionId: event.sessionId.valueOf(),
    seq: event.seq,
    type: event.type,
    schemaVersion: event.schemaVersion,
    occurredAt: event.occurredAt,
    actorJson: JSON.stringify(event.actor),
    causationId: event.causationId === undefined ? null : event.causationId.valueOf(),
    correlationId: event.correlationId === undefined ? null : event.correlationId.valueOf(),
    payloadJson: JSON.stringify(event.payload),
  };
}

function rowToEvent(row: EventRow): SessionEventUnion {
  return SessionEventUnionSchema.parse({
    id: row.id,
    sessionId: row.session_id,
    seq: row.seq,
    type: row.type,
    schemaVersion: row.schema_version,
    occurredAt: row.occurred_at,
    actor: JSON.parse(row.actor_json),
    causationId: row.causation_id ?? undefined,
    correlationId: row.correlation_id ?? undefined,
    payload: JSON.parse(row.payload_json),
  });
}
