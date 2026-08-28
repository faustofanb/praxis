import { randomUUID } from "node:crypto";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import type {
  EventActor,
  EventId,
  EventStore,
  SessionEventUnion,
  SessionId,
  ToolDefinition,
  ToolExecutionId,
  TurnId,
} from "@praxis/contracts";
import {
  asEventId,
  asSessionId,
  asToolExecutionId,
  asTurnId,
  EVENT_SCHEMA_VERSION,
} from "@praxis/contracts";
import { type AgentLoopDeps, runTurn } from "@praxis/core";
import { openSessionStore, type SessionStore } from "@praxis/store-sqlite";
import { localReadTools } from "@praxis/tools-local";
import { ScriptFileModelProvider } from "./scripted-provider";

/**
 * @praxis/cli — composition root (docs/02 section 4.6). Owns process-level
 * concerns only: argv parsing, real random IDs and wall-clock time, the
 * SQLite store handle, SIGINT wiring, and stdout/stderr. Every durable rule
 * lives in core; the CLI adds no loop or recovery logic of its own.
 *
 * Commands (docs/03 M2.5):
 *   run [--db P] [--session ID] [--input TEXT] [--root DIR] --script FILE
 *   sessions [--db P]
 *
 * Exit codes: 0 completed/listed; 1 usage or runtime error; 2 paused or
 * cancelled (turn left open — resume with `run --session ID`).
 */

const DEFAULT_DB_PATH = "praxis.db";
const DEFAULT_SYSTEM_PROMPT = "You are a local Praxis agent. Use the provided tools.";

export const packageName = "@praxis/cli";

export type CliIo = {
  readonly out: (line: string) => void;
  readonly err: (line: string) => void;
};

export async function main(argv: readonly string[], io: CliIo): Promise<number> {
  const [command, ...flags] = argv;
  if (command === undefined || command === "help" || command.startsWith("-")) {
    usage(io);
    return command === "help" ? 0 : 1;
  }
  try {
    switch (command) {
      case "run":
        return await runCommand(flags, io);
      case "sessions":
        return sessionsCommand(flags, io);
      default:
        io.err(`unknown command: ${command}`);
        usage(io);
        return 1;
    }
  } catch (error) {
    io.err(error instanceof Error ? error.message : String(error));
    return 1;
  }
}

function usage(io: CliIo): void {
  io.err(
    [
      "usage:",
      "  praxis run [--db PATH] [--session ID] [--input TEXT] [--root DIR] --script FILE",
      "  praxis sessions [--db PATH]",
      "",
      "run: create a session (no --session), send a prompt (--input), or",
      "resume an open turn (--session without --input). Durable events",
      "stream to stdout as they append.",
      "sessions: list session ids with status and head seq.",
    ].join("\n"),
  );
}

function parseFlags(flags: readonly string[]): Map<string, string> {
  const parsed = new Map<string, string>();
  for (let index = 0; index < flags.length; index += 2) {
    const flag = flags[index];
    const value = flags[index + 1];
    if (flag === undefined || !flag.startsWith("--") || value === undefined) {
      throw new Error(`expected --flag value pairs, got: ${flags.join(" ")}`);
    }
    parsed.set(flag.slice(2), value);
  }
  return parsed;
}

/** Tee store: every successfully appended durable fact streams to stdout. */
function observingStore(store: SessionStore, io: CliIo): SessionStore {
  return {
    append: async (events, expectedHeadSeq) => {
      await store.append(events, expectedHeadSeq);
      for (const event of events) {
        io.out(describeEvent(event));
      }
    },
    readStream: (sessionId, afterSeq) => store.readStream(sessionId, afterSeq),
    listSessions: () => store.listSessions(),
    close: () => store.close(),
  };
}

function describeEvent(event: SessionEventUnion): string {
  let suffix = "";
  switch (event.type) {
    case "TurnStarted":
      suffix = `turn ${event.payload.turnId}${
        event.payload.input === undefined ? "" : ` input=${truncate(event.payload.input, 60)}`
      }`;
      break;
    case "TurnCompleted":
      suffix = `turn ${event.payload.turnId}`;
      break;
    case "ToolProposed":
      suffix = `${event.payload.name} (${event.payload.effect})`;
      break;
    case "ToolAuthorized":
    case "ToolStarted":
      suffix = event.payload.toolExecutionId;
      break;
    case "ToolSucceeded":
      suffix = `${event.payload.toolExecutionId} — ${truncate(event.payload.resultJson, 60)}`;
      break;
    case "ToolFailed":
      suffix = `${event.payload.toolExecutionId} — ${truncate(event.payload.message, 60)}`;
      break;
    case "ToolRejected":
    case "ToolIndeterminate":
      suffix = `${event.payload.toolExecutionId} — ${truncate(event.payload.reason, 60)}`;
      break;
    case "ModelRequestStarted":
      suffix = event.payload.model;
      break;
    case "ModelResponseCompleted": {
      const calls = event.payload.toolCalls.length;
      const text = event.payload.text === undefined ? "" : ` ${truncate(event.payload.text, 60)}`;
      suffix = `${calls} tool call(s)${text}`;
      break;
    }
    case "ModelRequestFailed":
      suffix = `${event.payload.kind} — ${truncate(event.payload.message, 60)}`;
      break;
    default:
      break;
  }
  return `[${String(event.seq).padStart(3, " ")}] ${event.type}${suffix === "" ? "" : ` ${suffix}`}`;
}

function truncate(text: string, max: number): string {
  return text.length <= max ? text : `${text.slice(0, max - 1)}…`;
}

async function runCommand(flags: readonly string[], io: CliIo): Promise<number> {
  const options = parseFlags(flags);
  const dbPath = options.get("db") ?? DEFAULT_DB_PATH;
  const root = resolve(options.get("root") ?? process.cwd());
  const scriptPath = options.get("script");
  const sessionFlag = options.get("session");
  const input = options.get("input");

  if (scriptPath === undefined) {
    throw new Error("run requires --script FILE (no live provider is configured until M2-T006)");
  }
  if (sessionFlag === undefined && input === undefined) {
    throw new Error("run without --session requires --input to start the first turn");
  }

  const rawScripts: unknown = JSON.parse(await readFile(scriptPath, "utf8"));
  const model = new ScriptFileModelProvider(rawScripts, scriptPath);

  const store = observingStore(openSessionStore(dbPath), io);
  try {
    const sessionId =
      sessionFlag !== undefined ? asSessionId(sessionFlag) : await createSession(store);

    const controller = new AbortController();
    const onInterrupt = () => controller.abort();
    process.on("SIGINT", onInterrupt);
    try {
      const outcome = await runTurn(
        loopDeps(store, sessionId, model, root),
        input === undefined ? {} : { input },
        { signal: controller.signal },
      );
      switch (outcome.kind) {
        case "completed":
          io.out(outcome.finalText);
          return 0;
        case "paused":
          io.err(`paused: ${outcome.reason}`);
          io.err(`resume with: praxis run --session ${sessionId.valueOf()} --script ${scriptPath}`);
          return 2;
        case "cancelled":
          io.err("cancelled: the attempt is recorded and the turn stays open");
          io.err(`resume with: praxis run --session ${sessionId.valueOf()} --script ${scriptPath}`);
          return 2;
      }
    } finally {
      process.off("SIGINT", onInterrupt);
    }
  } finally {
    store.close();
  }
}

async function createSession(store: EventStore): Promise<SessionId> {
  const sessionId = asSessionId(`session-${randomUUID()}`);
  await store.append(
    [
      {
        id: asEventId(`event-${randomUUID()}`),
        sessionId,
        seq: 1,
        schemaVersion: EVENT_SCHEMA_VERSION,
        occurredAt: Date.now(),
        actor: { kind: "user" } satisfies EventActor,
        type: "SessionCreated",
        payload: { reason: "created by praxis CLI" },
      },
    ],
    0,
  );
  return sessionId;
}

function loopDeps(
  store: EventStore,
  sessionId: SessionId,
  model: ScriptFileModelProvider,
  root: string,
): AgentLoopDeps {
  const tools: readonly ToolDefinition[] = localReadTools(root);
  return {
    store,
    sessionId,
    model,
    modelId: "scripted-file",
    systemPrompt: DEFAULT_SYSTEM_PROMPT,
    tools,
    now: () => Date.now(),
    newEventId: (): EventId => asEventId(`event-${randomUUID()}`),
    newTurnId: (): TurnId => asTurnId(`turn-${randomUUID().slice(0, 8)}`),
    newToolExecutionId: (): ToolExecutionId =>
      asToolExecutionId(`tool-exec-${randomUUID().slice(0, 8)}`),
  };
}

function sessionsCommand(flags: readonly string[], io: CliIo): number {
  const options = parseFlags(flags);
  const store = openSessionStore(options.get("db") ?? DEFAULT_DB_PATH);
  try {
    const sessions = store.listSessions();
    if (sessions.length === 0) {
      io.out("no sessions");
      return 0;
    }
    for (const session of sessions) {
      io.out(`${session.sessionId.valueOf()}  ${session.status.padEnd(9)} head=${session.headSeq}`);
    }
    return 0;
  } finally {
    store.close();
  }
}

if (import.meta.main) {
  const code = await main(process.argv.slice(2), {
    out: (line) => console.log(line),
    err: (line) => console.error(line),
  });
  process.exit(code);
}
