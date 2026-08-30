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

  test("escalates an unresolvable dangling execution to a paused session, never re-runs it", async () => {
    const fx = fixture();
    seedDanglingExecution(fx.db, fx.root);

    // read_file declares no reconcile, so section 17 escalation applies: the
    // turn closes, the session pauses (CLI exit code 2), and the model is
    // never consulted — the script stays unconsumed.
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

    expect(result.code).toBe(2);
    expect(result.err.join("\n")).toMatch(/paused: .*could not be reconciled/u);
    expect(result.out.some((line) => line.includes("ToolIndeterminate"))).toBe(true);
    expect(result.out.some((line) => line.includes("SessionPaused"))).toBe(true);
    expect(result.out.some((line) => line === "recovered after crash")).toBe(false);

    const store = openSessionStore(fx.db);
    try {
      const state = foldSessionEvents(await store.readStream(SESSION_ID));
      expect(state.status).toBe("PAUSED");
      expect(state.currentTurnId).toBeUndefined();
      const dangling = state.toolExecutions.get(asToolExecutionId("tool-exec-cli-1"));
      expect(dangling?.status).toBe("INDETERMINATE");
    } finally {
      store.close();
    }
  });

  test("sending input to an open turn is rejected with a CLI error", async () => {
    const fx = fixture();
    // A dangling model request leaves an open turn with no indeterminates:
    // recovery closes the request fact, then the input-on-open-turn guard
    // fires — the section 17 pause path is not taken.
    seedDanglingModelRequest(fx.db);
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

describe("capability approval surface (M8-T002)", () => {
  const WRITE_STEP = [
    { type: "toolCallStart", toolCallId: "call-1", name: "write_file" },
    {
      type: "toolCallDelta",
      toolCallId: "call-1",
      argumentsDelta: '{"path":"out.txt","content":"written by cli"}',
    },
    { type: "toolCallEnd", toolCallId: "call-1" },
    { type: "completed", finishReason: "toolCalls" },
  ];

  test("--allow-write authorizes the write: durable SUCCEEDED fact plus filesystem effect", async () => {
    const fx = fixture();
    const script = fx.script([WRITE_STEP, FINAL_STEP("the file is written")]);

    const result = await cli([
      "run",
      "--db",
      fx.db,
      "--root",
      fx.root,
      "--allow-write",
      "--script",
      script,
      "--input",
      "write out.txt",
    ]);

    expect(result.code).toBe(0);
    const stream = result.out.filter((line) => line.startsWith("[")).join("\n");
    expect(stream).toContain("ToolProposed write_file (reconcilable_write)");
    expect(stream).toContain("ToolAuthorized");
    expect(stream).toContain("ToolSucceeded");
    const store = openSessionStore(fx.db);
    try {
      const sessions = store.listSessions();
      const created = sessions[0];
      if (created === undefined) {
        throw new Error("expected one session");
      }
      const state = foldSessionEvents(await store.readStream(created.sessionId));
      const snapshot = [...state.toolExecutions.values()][0];
      expect(snapshot?.status).toBe("SUCCEEDED");
    } finally {
      store.close();
    }
    expect(await Bun.file(join(fx.root, "out.txt")).text()).toBe("written by cli");
  });

  test("without the flag the write is a durable ToolRejected fact and no file appears", async () => {
    const fx = fixture();
    const script = fx.script([WRITE_STEP, FINAL_STEP("acknowledged the rejection")]);

    const result = await cli([
      "run",
      "--db",
      fx.db,
      "--root",
      fx.root,
      "--script",
      script,
      "--input",
      "write out.txt",
    ]);

    expect(result.code).toBe(0);
    const stream = result.out.filter((line) => line.startsWith("[")).join("\n");
    expect(stream).toContain("ToolProposed write_file (reconcilable_write)");
    expect(stream).toContain("ToolRejected");
    expect(stream).toContain("requires human approval");
    expect(stream).not.toContain("ToolSucceeded write");
    expect(await Bun.file(join(fx.root, "out.txt")).exists()).toBe(false);
  });

  test("--allow-bash grants shell.exec for a bash round-trip", async () => {
    const fx = fixture();
    const BASH_STEP = [
      { type: "toolCallStart", toolCallId: "call-1", name: "bash" },
      {
        type: "toolCallDelta",
        toolCallId: "call-1",
        argumentsDelta: '{"command":"echo cli-bash-ok"}',
      },
      { type: "toolCallEnd", toolCallId: "call-1" },
      { type: "completed", finishReason: "toolCalls" },
    ];
    const script = fx.script([BASH_STEP, FINAL_STEP("bash ran")]);

    const result = await cli([
      "run",
      "--db",
      fx.db,
      "--root",
      fx.root,
      "--allow-bash",
      "--script",
      script,
      "--input",
      "run echo",
    ]);

    expect(result.code).toBe(0);
    const stream = result.out.filter((line) => line.startsWith("[")).join("\n");
    expect(stream).toContain("ToolProposed bash (non_idempotent_write)");
    expect(stream).toContain("ToolSucceeded");
    const store = openSessionStore(fx.db);
    try {
      const sessions = store.listSessions();
      const created = sessions[0];
      if (created === undefined) {
        throw new Error("expected one session");
      }
      const state = foldSessionEvents(await store.readStream(created.sessionId));
      const snapshot = [...state.toolExecutions.values()][0];
      expect(snapshot?.status).toBe("SUCCEEDED");
      expect(snapshot?.resultJson ?? "").toContain("cli-bash-ok");
    } finally {
      store.close();
    }
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

describe("praxis run --model", () => {
  test("refuses --model together with --script", async () => {
    const fx = fixture();
    const script = fx.script([FINAL_STEP("x")]);
    const result = await cli([
      "run",
      "--db",
      fx.db,
      "--script",
      script,
      "--model",
      "test-model",
      "--input",
      "hi",
    ]);
    expect(result.code).toBe(1);
    expect(result.err.join("\n")).toContain("not both");
  });

  test("refuses --model without --api-key or OPENAI_API_KEY", async () => {
    const fx = fixture();
    const previous = process.env.OPENAI_API_KEY;
    delete process.env.OPENAI_API_KEY;
    try {
      const result = await cli(["run", "--db", fx.db, "--model", "test-model", "--input", "hi"]);
      expect(result.code).toBe(1);
      expect(result.err.join("\n")).toContain("OPENAI_API_KEY");
    } finally {
      if (previous !== undefined) {
        process.env.OPENAI_API_KEY = previous;
      }
    }
  });

  test("runs the read_file vertical against a local OpenAI-compatible endpoint", async () => {
    const fx = fixture();
    let modelRequests = 0;
    const server = Bun.serve({
      port: 0,
      fetch: async (request) => {
        if (!request.url.endsWith("/chat/completions")) {
          return new Response("not found", { status: 404 });
        }
        if (request.headers.get("authorization") !== "Bearer cli-test-key") {
          return new Response(JSON.stringify({ error: { message: "bad key" } }), { status: 401 });
        }
        const body: unknown = await request.json();
        if (!isObject(body) || body.model !== "test-model") {
          return new Response(JSON.stringify({ error: { message: "wrong model" } }), {
            status: 400,
          });
        }
        modelRequests += 1;
        const lastMessage = lastMessageRole(body);
        const chunks =
          lastMessage === "user"
            ? [
                {
                  choices: [
                    {
                      index: 0,
                      delta: {
                        tool_calls: [
                          {
                            index: 0,
                            id: "call-1",
                            function: { name: "read_file", arguments: '{"path":"note.txt"}' },
                          },
                        ],
                      },
                      finish_reason: null,
                    },
                  ],
                },
                { choices: [{ index: 0, delta: {}, finish_reason: "tool_calls" }] },
              ]
            : [
                {
                  choices: [
                    {
                      index: 0,
                      delta: { content: "the note says: live note body" },
                      finish_reason: null,
                    },
                  ],
                },
                { choices: [{ index: 0, delta: {}, finish_reason: "stop" }] },
              ];
        const sse = chunks
          .map((chunk) => `data: ${JSON.stringify(chunk)}\n\n`)
          .concat("data: [DONE]\n\n")
          .join("");
        return new Response(sse, {
          status: 200,
          headers: { "content-type": "text/event-stream" },
        });
      },
    });

    try {
      const result = await cli([
        "run",
        "--db",
        fx.db,
        "--root",
        fx.root,
        "--model",
        "test-model",
        "--api-key",
        "cli-test-key",
        "--base-url",
        `${server.url.origin}/v1`,
        "--input",
        "read the note",
      ]);

      expect(result.code).toBe(0);
      expect(modelRequests).toBe(2);
      const stream = result.out.filter((line) => line.startsWith("[")).join("\n");
      expect(stream).toContain("ModelRequestStarted test-model");
      expect(stream).toContain("ToolProposed read_file (read_only)");
      expect(stream).toContain("ToolSucceeded");
      expect(stream).toContain("TurnCompleted");
      expect(result.out.at(-1)).toBe("the note says: live note body");
    } finally {
      server.stop(true);
    }
  });
});

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function lastMessageRole(body: Record<string, unknown>): string {
  const messages = body.messages;
  if (!Array.isArray(messages) || messages.length === 0) {
    throw new Error("expected chat messages in the request body");
  }
  const last = messages.at(-1);
  if (!isObject(last) || typeof last.role !== "string") {
    throw new Error("expected a role on the last message");
  }
  return last.role;
}

/**
 * Hand-append a legal crashed-run prefix: the model asked for read_file,
 * the runtime proposed/authorized/started it, then the process died —
 * leaving the turn open with a dangling EXECUTING execution.
 */
function seedDanglingModelRequest(dbPath: string): void {
  const events: SessionEventUnion[] = [
    {
      id: asEventId("cli-seed-mr-1"),
      sessionId: SESSION_ID,
      seq: 1,
      schemaVersion: 1,
      occurredAt: 1,
      actor: { kind: "user" },
      type: "SessionCreated",
      payload: {},
    },
    {
      id: asEventId("cli-seed-mr-2"),
      sessionId: SESSION_ID,
      seq: 2,
      schemaVersion: 1,
      occurredAt: 2,
      actor: { kind: "user" },
      type: "TurnStarted",
      payload: { turnId: asTurnId("turn-cli-1"), input: "read the note" },
    },
    {
      id: asEventId("cli-seed-mr-3"),
      sessionId: SESSION_ID,
      seq: 3,
      schemaVersion: 1,
      occurredAt: 3,
      actor: { kind: "system" },
      type: "ModelRequestStarted",
      payload: { model: "scripted-file" },
    },
  ];
  const store = openSessionStore(dbPath);
  try {
    store.append(events, 0);
  } finally {
    store.close();
  }
}

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
