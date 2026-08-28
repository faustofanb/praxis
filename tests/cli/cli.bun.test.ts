import { describe, expect, test } from "bun:test";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { type CliIo, main } from "@praxis/cli";
import type { SessionEventUnion } from "@praxis/contracts";
import { asEventId, asSessionId, asToolExecutionId, asTurnId } from "@praxis/contracts";
import { foldSessionEvents } from "@praxis/core";
import { openSessionStore } from "@praxis/store-sqlite";

/**
 * CLI composition-root tests (M2-T005). Run under Bun because @praxis/cli
 * pulls bun:sqlite transitively. These drive `main(argv, io)` directly —
 * the process entrypoint is a two-line wrapper around it.
 */

const SESSION_ID = asSessionId("session-cli-1");

type Run = { code: number; out: string[]; err: string[] };

async function cli(argv: string[]): Promise<Run> {
  const out: string[] = [];
  const err: string[] = [];
  const io: CliIo = {
    out: (line) => out.push(line),
    err: (line) => err.push(line),
  };
  const code = await main(argv, io);
  return { code, out, err };
}

type Fixture = {
  readonly db: string;
  readonly root: string;
  readonly script: (scripts: unknown) => string;
};

function fixture(): Fixture {
  const dir = mkdtempSync(join(tmpdir(), "praxis-cli-"));
  const root = join(dir, "root");
  mkdirSync(root);
  writeFileSync(join(root, "note.txt"), "cli note body");
  const scriptsDir = join(dir, "scripts");
  mkdirSync(scriptsDir);
  let scriptCount = 0;
  return {
    db: join(dir, "praxis.db"),
    root,
    script: (scripts: unknown) => {
      scriptCount += 1;
      const path = join(scriptsDir, `script-${scriptCount}.json`);
      writeFileSync(path, JSON.stringify(scripts));
      return path;
    },
  };
}

const READ_FILE_STEP = [
  { type: "toolCallStart", toolCallId: "call-1", name: "read_file" },
  { type: "toolCallDelta", toolCallId: "call-1", argumentsDelta: '{"path":"note.txt"}' },
  { type: "toolCallEnd", toolCallId: "call-1" },
  { type: "completed", finishReason: "toolCalls" },
];
const FINAL_STEP = (text: string) => [
  { type: "textDelta", text },
  { type: "completed", finishReason: "stop" },
];

describe("praxis run", () => {
  test("creates a session, runs the read_file vertical, streams events, exits 0", async () => {
    const fx = fixture();
    const script = fx.script([READ_FILE_STEP, FINAL_STEP("the note says: cli note body")]);

    const result = await cli([
      "run",
      "--db",
      fx.db,
      "--root",
      fx.root,
      "--script",
      script,
      "--input",
      "read the note",
    ]);

    expect(result.code).toBe(0);
    const stream = result.out.filter((line) => line.startsWith("[")).join("\n");
    expect(stream).toContain("SessionCreated");
    expect(stream).toContain("TurnStarted");
    expect(stream).toContain("ModelRequestStarted");
    expect(stream).toContain("ModelResponseCompleted 1 tool call(s)");
    expect(stream).toContain("ToolProposed read_file (read_only)");
    expect(stream).toContain("ToolSucceeded");
    expect(stream).toContain("TurnCompleted");
    expect(result.out.at(-1)).toBe("the note says: cli note body");

    const store = openSessionStore(fx.db);
    try {
      const sessions = store.listSessions();
      expect(sessions.length).toBe(1);
      const created = sessions[0];
      if (created === undefined) {
        throw new Error("expected the run to have created exactly one session");
      }
      const state = foldSessionEvents(await store.readStream(created.sessionId));
      expect(state.status).toBe("ACTIVE");
      expect(state.currentTurnId).toBeUndefined();
      expect(state.toolExecutions.size).toBe(1);
    } finally {
      store.close();
    }
  });

  test("resumes a crashed open turn, marks the dangling execution INDETERMINATE, never re-runs it", async () => {
    const fx = fixture();
    seedDanglingExecution(fx.db, fx.root);

    // Exactly one script: a second model call (which re-running history or
    // an extra loop step would trigger) would exhaust the script and fail.
    const script = fx.script([FINAL_STEP("recovered after crash")]);
    const result = await cli([
      "run",
      "--db",
      fx.db,
      "--root",
      fx.root,
      "--script",
      script,
      "--session",
      SESSION_ID.valueOf(),
    ]);

    expect(result.code).toBe(0);
    expect(result.out.some((line) => line.includes("ToolIndeterminate"))).toBe(true);
    expect(result.out.at(-1)).toBe("recovered after crash");

    const store = openSessionStore(fx.db);
    try {
      const state = foldSessionEvents(await store.readStream(SESSION_ID));
      expect(state.currentTurnId).toBeUndefined();
      const dangling = state.toolExecutions.get(asToolExecutionId("tool-exec-cli-1"));
      expect(dangling?.status).toBe("INDETERMINATE");
    } finally {
      store.close();
    }
  });

  test("sending input to an open turn is rejected with a CLI error", async () => {
    const fx = fixture();
    seedDanglingExecution(fx.db, fx.root);
    const script = fx.script([FINAL_STEP("irrelevant")]);
    const result = await cli([
      "run",
      "--db",
      fx.db,
      "--root",
      fx.root,
      "--script",
      script,
      "--session",
      SESSION_ID.valueOf(),
      "--input",
      "second message",
    ]);
    expect(result.code).toBe(1);
    expect(result.err.join("\n")).toMatch(/already open/u);
  });

  test("run without --script refuses to start", async () => {
    const fx = fixture();
    const result = await cli(["run", "--db", fx.db, "--root", fx.root, "--input", "hi"]);
    expect(result.code).toBe(1);
    expect(result.err.join("\n")).toMatch(/--script/u);
  });

  test("a malformed script file fails loudly", async () => {
    const fx = fixture();
    const script = fx.script([[{ type: "definitelyNotAModelEvent" }]]);
    const result = await cli([
      "run",
      "--db",
      fx.db,
      "--root",
      fx.root,
      "--script",
      script,
      "--input",
      "hi",
    ]);
    expect(result.code).toBe(1);
    expect(result.err.join("\n")).toMatch(/definitelyNotAModelEvent|invalid/u);
  });

  test("unknown commands print usage and exit non-zero", async () => {
    const result = await cli(["frobnicate"]);
    expect(result.code).toBe(1);
    expect(result.err.join("\n")).toContain("usage:");
    const help = await cli(["help"]);
    expect(help.code).toBe(0);
    expect(help.err.join("\n")).toContain("usage:");
  });
});

describe("praxis sessions", () => {
  test("an empty store lists no sessions", async () => {
    const fx = fixture();
    const result = await cli(["sessions", "--db", fx.db]);
    expect(result.code).toBe(0);
    expect(result.out).toEqual(["no sessions"]);
  });

  test("lists session ids with status and head seq after a run", async () => {
    const fx = fixture();
    const script = fx.script([FINAL_STEP("done")]);
    await cli(["run", "--db", fx.db, "--root", fx.root, "--script", script, "--input", "hi"]);

    const result = await cli(["sessions", "--db", fx.db]);
    expect(result.code).toBe(0);
    expect(result.out.length).toBe(1);
    expect(result.out[0]).toMatch(/session-[0-9a-f-]{36}\s+ACTIVE\s+head=5/u);
  });
});

/**
 * Hand-append a legal crashed-run prefix: the model asked for read_file,
 * the runtime proposed/authorized/started it, then the process died —
 * leaving the turn open with a dangling EXECUTING execution.
 */
function seedDanglingExecution(dbPath: string, root: string): void {
  writeFileSync(join(root, "note.txt"), "cli note body");
  const events: SessionEventUnion[] = [
    {
      id: asEventId("cli-seed-1"),
      sessionId: SESSION_ID,
      seq: 1,
      schemaVersion: 1,
      occurredAt: 1,
      actor: { kind: "user" },
      type: "SessionCreated",
      payload: {},
    },
    {
      id: asEventId("cli-seed-2"),
      sessionId: SESSION_ID,
      seq: 2,
      schemaVersion: 1,
      occurredAt: 2,
      actor: { kind: "user" },
      type: "TurnStarted",
      payload: { turnId: asTurnId("turn-cli-1"), input: "read the note" },
    },
    {
      id: asEventId("cli-seed-3"),
      sessionId: SESSION_ID,
      seq: 3,
      schemaVersion: 1,
      occurredAt: 3,
      actor: { kind: "system" },
      type: "ModelRequestStarted",
      payload: { model: "scripted-file" },
    },
    {
      id: asEventId("cli-seed-4"),
      sessionId: SESSION_ID,
      seq: 4,
      schemaVersion: 1,
      occurredAt: 4,
      actor: { kind: "system" },
      type: "ModelResponseCompleted",
      payload: {
        toolCalls: [{ id: "call-1", name: "read_file", argumentsJson: '{"path":"note.txt"}' }],
      },
    },
    {
      id: asEventId("cli-seed-5"),
      sessionId: SESSION_ID,
      seq: 5,
      schemaVersion: 1,
      occurredAt: 5,
      actor: { kind: "system" },
      type: "ToolProposed",
      payload: {
        toolExecutionId: asToolExecutionId("tool-exec-cli-1"),
        name: "read_file",
        argumentsJson: '{"path":"note.txt"}',
        effect: "read_only",
        toolCallId: "call-1",
      },
    },
    {
      id: asEventId("cli-seed-6"),
      sessionId: SESSION_ID,
      seq: 6,
      schemaVersion: 1,
      occurredAt: 6,
      actor: { kind: "system" },
      type: "ToolAuthorized",
      payload: { toolExecutionId: asToolExecutionId("tool-exec-cli-1") },
    },
    {
      id: asEventId("cli-seed-7"),
      sessionId: SESSION_ID,
      seq: 7,
      schemaVersion: 1,
      occurredAt: 7,
      actor: { kind: "system" },
      type: "ToolStarted",
      payload: { toolExecutionId: asToolExecutionId("tool-exec-cli-1") },
    },
  ];
  const store = openSessionStore(dbPath);
  try {
    store.append(events, 0);
  } finally {
    store.close();
  }
}
