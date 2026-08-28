import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type {
  ModelMessage,
  ModelRequest,
  SessionEventUnion,
  ToolDefinition,
  ToolExecutionContext,
  ToolExecutionOutcome,
} from "@praxis/contracts";
import {
  asEventId,
  asSessionId,
  asToolExecutionId,
  asTurnId,
  ModelRequestSchema,
} from "@praxis/contracts";
import { type AgentLoopDeps, foldSessionEvents, runTurn } from "@praxis/core";
import { ScriptedModelProvider, type ScriptItem } from "@praxis/testkit";
import { localReadTools, localWriteTools } from "@praxis/tools-local";
import { afterEach, beforeEach, describe, expect, test } from "vitest";
import { inMemoryEventStore } from "../helpers/in-memory-event-store";
import {
  modelRequestStarted,
  modelResponseCompleted,
  sessionCreated,
  sessionResumed,
  toolAuthorized,
  toolProposed,
  toolReconciled,
  toolStarted,
  turnStarted,
} from "../helpers/session-events";

/**
 * Cross-package crash-after-side-effect recovery (docs/02 section 17): a
 * hand-appended stream simulates a process crash mid-tool-execution, then
 * runTurn over the real tools-local adapters. The recovered process closes
 * the dangling work as INDETERMINATE, reconciles what can be verified, and
 * escalates to a paused session when an unknown effect cannot be settled —
 * never silently continuing the turn over it.
 */

const SESSION_ID = asSessionId("session-loop-recovery");

let root: string;
beforeEach(async () => {
  root = await mkdtemp(join(tmpdir(), "praxis-loop-"));
  await writeFile(join(root, "note.txt"), "loop recovery note body");
});
afterEach(async () => {
  await rm(root, { recursive: true, force: true });
});

function countingTools(tools: readonly ToolDefinition[], calls: string[]): ToolDefinition[] {
  return tools.map((tool) => ({
    ...tool,
    async execute(context: ToolExecutionContext, input: unknown): Promise<ToolExecutionOutcome> {
      calls.push(tool.name);
      return tool.execute(context, input);
    },
  }));
}

function integrationDeps(
  store: ReturnType<typeof inMemoryEventStore>,
  model: ScriptedModelProvider,
  tools: readonly ToolDefinition[],
): AgentLoopDeps {
  let counter = 9000;
  let turns = 0;
  let executions = 0;
  return {
    store,
    sessionId: SESSION_ID,
    model,
    modelId: "scripted-model",
    systemPrompt: "You are the recovery integration harness.",
    tools,
    now: () => {
      counter += 1;
      return counter;
    },
    newEventId: () => asEventId(`loop-int-${counter}`),
    newTurnId: () => {
      turns += 1;
      return asTurnId(`loop-int-turn-${turns}`);
    },
    newToolExecutionId: () => {
      executions += 1;
      return asToolExecutionId(`loop-int-exec-${executions}`);
    },
  };
}

const SIGNAL = { signal: new AbortController().signal };
const TEXT = (text: string): ScriptItem => ({ kind: "event", event: { type: "textDelta", text } });
const COMPLETED: ScriptItem = { kind: "event", event: { type: "completed", finishReason: "stop" } };
const CRASHED_READ: SessionEventUnion[] = [
  sessionCreated(1),
  turnStarted(2, 1, "read the note"),
  modelRequestStarted(3),
  modelResponseCompleted(4, {
    toolCalls: [{ id: "call-1", name: "read_file", argumentsJson: '{"path":"note.txt"}' }],
  }),
  toolProposed(5, 1, {
    name: "read_file",
    argumentsJson: '{"path":"note.txt"}',
    effect: "read_only",
    toolCallId: "call-1",
  }),
  toolAuthorized(6, 1),
  toolStarted(7, 1),
];

async function seed(store: ReturnType<typeof inMemoryEventStore>, events: SessionEventUnion[]) {
  await store.append(
    events.map((event) => ({ ...event, sessionId: SESSION_ID })),
    0,
  );
}

function toolBodiesOf(request: ModelRequest | undefined): unknown[] {
  return (
    request?.messages
      .filter(
        (message): message is Extract<ModelMessage, { role: "tool" }> => message.role === "tool",
      )
      .map((message) => JSON.parse(message.text) as unknown) ?? []
  );
}

describe("agent loop crash recovery across packages", () => {
  test("an unresolvable dangling execution pauses the session instead of continuing the turn", async () => {
    const store = inMemoryEventStore();
    const calls: string[] = [];
    // A legal prefix of a crashed run: the model asked for read_file, the
    // runtime proposed, authorized, and started it — then the process died.
    // read_file declares no reconcile, so its outcome cannot be verified.
    await seed(store, CRASHED_READ);

    const model = new ScriptedModelProvider([TEXT("recovered after crash"), COMPLETED]);
    const outcome = await runTurn(
      integrationDeps(store, model, countingTools(localReadTools(root), calls)),
      {},
      SIGNAL,
    );

    expect(outcome).toEqual({
      kind: "paused",
      reason: expect.stringContaining("could not be reconciled"),
    });
    // Escalation, not silent continuation: the historical execution was
    // never re-executed and the model was never consulted over the unknown.
    expect(calls).toEqual([]);
    expect(model.requests.length).toBe(0);

    const events = await store.readStream(SESSION_ID);
    const indeterminate = events.find((event) => event.type === "ToolIndeterminate");
    expect(indeterminate?.payload).toMatchObject({
      toolExecutionId: "tool-exec-1",
      reason: "process crashed before a terminal tool event; outcome unknown",
    });
    // The open turn is closed and the session is parked for human decision.
    expect(events.at(-2)?.type).toBe("TurnCompleted");
    expect(events.at(-1)?.type).toBe("SessionPaused");

    const finalState = foldSessionEvents(events);
    expect(finalState.status).toBe("PAUSED");
    expect(finalState.currentTurnId).toBeUndefined();
    expect(finalState.toolExecutions.get(asToolExecutionId("tool-exec-1"))?.status).toBe(
      "INDETERMINATE",
    );
  });

  test("a crashed write_file reconciles at the next turn entry and the turn completes on the settled fact", async () => {
    const store = inMemoryEventStore();
    const calls: string[] = [];
    const content = "written before the crash";
    // The crash happened after the atomic rename landed on disk but before
    // ToolSucceeded was appended: the effect exists, the fact does not.
    await writeFile(join(root, "out.txt"), content);
    const argumentsJson = JSON.stringify({ path: "out.txt", content });
    await seed(store, [
      sessionCreated(1),
      turnStarted(2, 1, "write the note"),
      modelRequestStarted(3),
      modelResponseCompleted(4, {
        toolCalls: [{ id: "call-1", name: "write_file", argumentsJson }],
      }),
      toolProposed(5, 1, {
        name: "write_file",
        argumentsJson,
        effect: "reconcilable_write",
        toolCallId: "call-1",
      }),
      toolAuthorized(6, 1),
      toolStarted(7, 1),
    ]);

    const model = new ScriptedModelProvider([TEXT("recovered and settled"), COMPLETED]);
    const outcome = await runTurn(
      integrationDeps(store, model, countingTools(localWriteTools(root), calls)),
      {},
      SIGNAL,
    );

    expect(outcome).toEqual({ kind: "completed", finalText: "recovered and settled" });
    // Recovery verified the effect without re-executing the tool.
    expect(calls).toEqual([]);

    const events = await store.readStream(SESSION_ID);
    const reconciled = events.find((event) => event.type === "ToolReconciled");
    expect(reconciled?.payload).toMatchObject({
      toolExecutionId: "tool-exec-1",
      outcome: "succeeded",
    });
    expect(events.at(-1)?.type).toBe("TurnCompleted");

    const finalState = foldSessionEvents(events);
    const snapshot = finalState.toolExecutions.get(asToolExecutionId("tool-exec-1"));
    expect(snapshot?.status).toBe("SUCCEEDED");
    expect(snapshot?.reconciliationCount).toBe(1);

    // The model saw both facts in order — the honest unknown first, then the
    // verified conclusion, never a silent replacement of the former.
    expect(model.requests.length).toBe(1);
    ModelRequestSchema.parse(model.requests[0]);
    const bodies = toolBodiesOf(model.requests[0]);
    expect(bodies[0]).toEqual({
      status: "indeterminate",
      reason: "process crashed before a terminal tool event; outcome unknown",
    });
    expect(bodies[1]).toMatchObject({
      status: "succeeded",
      reconciled: true,
      result: { verified: true },
    });
  });

  test("a paused session only proceeds after a human settles the indeterminate and resumes", async () => {
    const store = inMemoryEventStore();
    const calls: string[] = [];
    await seed(store, CRASHED_READ);

    const model = new ScriptedModelProvider([TEXT("resumed after human decision"), COMPLETED]);
    const deps = integrationDeps(store, model, countingTools(localReadTools(root), calls));
    const first = await runTurn(deps, {}, SIGNAL);
    expect(first).toMatchObject({ kind: "paused" });

    // While paused the loop refuses to run: resume is the only unlock.
    await expect(runTurn(deps, {}, SIGNAL)).rejects.toThrow("requires an ACTIVE session");

    // Off-band human action, in the only legal order: resume first (tool
    // facts are only legal in an ACTIVE session), then settle the unknown
    // with a durable fact. The next turn re-attempts nothing — the fact
    // holds; a bare resume without settling would just re-pause on entry.
    await store.append(
      [
        sessionResumed(11),
        toolReconciled(12, 1, "succeeded", JSON.stringify({ verified: true })),
      ].map((event) => ({ ...event, sessionId: SESSION_ID })),
      10,
    );

    const second = await runTurn(deps, { input: "resume the session" }, SIGNAL);
    expect(second).toEqual({ kind: "completed", finalText: "resumed after human decision" });
    expect(calls).toEqual([]);

    const events = await store.readStream(SESSION_ID);
    const finalState = foldSessionEvents(events);
    expect(finalState.status).toBe("ACTIVE");
    expect(finalState.toolExecutions.get(asToolExecutionId("tool-exec-1"))?.status).toBe(
      "SUCCEEDED",
    );
    expect(events.at(-1)?.type).toBe("TurnCompleted");

    // The resumed turn's model request carries the settled fact chain.
    expect(model.requests.length).toBe(1);
    const bodies = toolBodiesOf(model.requests[0]);
    expect(bodies.at(-1)).toMatchObject({ status: "succeeded", reconciled: true });
  });

  test("a fresh session runs a full read_file round trip through the real adapter", async () => {
    const store = inMemoryEventStore();
    await seed(store, [sessionCreated(1)]);
    const calls: string[] = [];
    const model = new ScriptedModelProvider(
      [
        {
          kind: "event",
          event: { type: "toolCallStart", toolCallId: "call-1", name: "read_file" },
        },
        {
          kind: "event",
          event: {
            type: "toolCallDelta",
            toolCallId: "call-1",
            argumentsDelta: '{"path":"note.txt"}',
          },
        },
        { kind: "event", event: { type: "toolCallEnd", toolCallId: "call-1" } },
        { kind: "event", event: { type: "completed", finishReason: "toolCalls" } },
      ],
      [TEXT("I read the note"), COMPLETED],
    );

    const outcome = await runTurn(
      integrationDeps(store, model, countingTools(localReadTools(root), calls)),
      { input: "read the note" },
      SIGNAL,
    );

    expect(outcome).toEqual({ kind: "completed", finalText: "I read the note" });
    expect(calls).toEqual(["read_file"]);
    const secondRequest = model.requests[1];
    const toolMessage = secondRequest?.messages.find((message) => message.role === "tool");
    if (toolMessage?.role !== "tool") {
      throw new Error("expected a tool result message in the second request");
    }
    const body: unknown = JSON.parse(toolMessage.text);
    expect(body).toEqual({
      status: "succeeded",
      result: { path: "note.txt", content: "loop recovery note body" },
    });
  });
});
