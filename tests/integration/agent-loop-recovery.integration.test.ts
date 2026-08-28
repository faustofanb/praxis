import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type {
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
import { localReadTools } from "@praxis/tools-local";
import { afterEach, beforeEach, describe, expect, test } from "vitest";
import { inMemoryEventStore } from "../helpers/in-memory-event-store";
import {
  modelRequestStarted,
  modelResponseCompleted,
  sessionCreated,
  turnStarted,
} from "../helpers/session-events";

/**
 * Cross-package recovery integration (M2-T004): a hand-appended stream that
 * simulates a process crash mid-tool-execution, then runTurn over the real
 * tools-local adapters. The recovered process must close the dangling work
 * as INDETERMINATE, never re-execute the historical tool, and still finish
 * the turn through the model.
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

function countingTools(calls: string[]): ToolDefinition[] {
  return localReadTools(root).map((tool) => ({
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

describe("agent loop crash recovery across packages", () => {
  test("a dangling EXECUTING tool becomes INDETERMINATE, is not re-executed, and the turn still completes", async () => {
    const store = inMemoryEventStore();
    const calls: string[] = [];
    // A legal prefix of a crashed run: the model asked for read_file, the
    // runtime proposed, authorized, and started it — then the process died.
    const crashedEvents: SessionEventUnion[] = [
      sessionCreated(1),
      turnStarted(2, 1, "read the note"),
      modelRequestStarted(3),
      modelResponseCompleted(4, {
        toolCalls: [{ id: "call-1", name: "read_file", argumentsJson: '{"path":"note.txt"}' }],
      }),
      {
        id: asEventId("recovery-proposed"),
        sessionId: SESSION_ID,
        seq: 5,
        schemaVersion: 1,
        occurredAt: 9005,
        actor: { kind: "system" },
        type: "ToolProposed",
        payload: {
          toolExecutionId: asToolExecutionId("tool-exec-1"),
          name: "read_file",
          argumentsJson: '{"path":"note.txt"}',
          effect: "read_only",
          toolCallId: "call-1",
        },
      },
      {
        id: asEventId("recovery-authorized"),
        sessionId: SESSION_ID,
        seq: 6,
        schemaVersion: 1,
        occurredAt: 9006,
        actor: { kind: "system" },
        type: "ToolAuthorized",
        payload: { toolExecutionId: asToolExecutionId("tool-exec-1") },
      },
      {
        id: asEventId("recovery-started"),
        sessionId: SESSION_ID,
        seq: 7,
        schemaVersion: 1,
        occurredAt: 9007,
        actor: { kind: "system" },
        type: "ToolStarted",
        payload: { toolExecutionId: asToolExecutionId("tool-exec-1") },
      },
    ];
    await store.append(
      crashedEvents.map((event) => ({ ...event, sessionId: SESSION_ID })),
      0,
    );

    const model = new ScriptedModelProvider([TEXT("recovered after crash"), COMPLETED]);
    const outcome = await runTurn(integrationDeps(store, model, countingTools(calls)), {}, SIGNAL);

    expect(outcome).toEqual({ kind: "completed", finalText: "recovered after crash" });
    // The historical execution was never re-run; only the recovery model
    // call happened, and it produced no new tool calls.
    expect(calls).toEqual([]);

    const events = await store.readStream(SESSION_ID);
    const indeterminate = events.find((event) => event.type === "ToolIndeterminate");
    expect(indeterminate?.payload).toMatchObject({
      toolExecutionId: "tool-exec-1",
      reason: "process crashed before a terminal tool event; outcome unknown",
    });
    expect(events.at(-1)?.type).toBe("TurnCompleted");

    const finalState = foldSessionEvents(events);
    expect(finalState.currentTurnId).toBeUndefined();
    expect(finalState.toolExecutions.get(asToolExecutionId("tool-exec-1"))?.status).toBe(
      "INDETERMINATE",
    );

    // Every request the recovered process sent parses through the public
    // contract, and the model saw the indeterminate outcome as a tool fact.
    expect(model.requests.length).toBe(1);
    ModelRequestSchema.parse(model.requests[0]);
    const toolMessage = model.requests[0]?.messages.find((message) => message.role === "tool");
    expect(toolMessage).toEqual({
      role: "tool",
      toolCallId: "call-1",
      text: JSON.stringify({
        status: "indeterminate",
        reason: "process crashed before a terminal tool event; outcome unknown",
      }),
    });
  });

  test("a fresh session runs a full read_file round trip through the real adapter", async () => {
    const store = inMemoryEventStore();
    await store.append(
      [sessionCreated(1)].map((event) => ({ ...event, sessionId: SESSION_ID })),
      0,
    );
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
      integrationDeps(store, model, countingTools(calls)),
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
