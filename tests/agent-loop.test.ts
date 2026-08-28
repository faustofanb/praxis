import type { ToolDefinition, ToolExecutionContext, ToolExecutionOutcome } from "@praxis/contracts";
import {
  asEventId,
  asSessionId,
  asToolExecutionId,
  asTurnId,
  type SessionEventUnion,
} from "@praxis/contracts";
import {
  type AgentLoopDeps,
  InvalidTurnGuardsError,
  projectConversation,
  runTurn,
  validateTurnGuards,
} from "@praxis/core";
import { ScriptedModelProvider, type ScriptItem } from "@praxis/testkit";
import { describe, expect, test } from "vitest";
import { z } from "zod";
import { inMemoryEventStore } from "./helpers/in-memory-event-store";
import {
  modelRequestStarted,
  modelResponseCompleted,
  sessionCreated,
  toolFailed,
  toolIndeterminate,
  toolProposed,
  toolReconciled,
  toolRejected,
  toolSucceeded,
  turnStarted,
} from "./helpers/session-events";

const SESSION_ID = asSessionId("session-loop");

type MemoryStore = ReturnType<typeof inMemoryEventStore>;

function loopDeps(
  store: MemoryStore,
  model: ScriptedModelProvider,
  tools: readonly ToolDefinition[] = [],
): AgentLoopDeps {
  let counter = 1000;
  let turns = 0;
  let executions = 0;
  return {
    store,
    sessionId: SESSION_ID,
    model,
    modelId: "scripted-model",
    systemPrompt: "You are a test harness.",
    tools,
    now: () => {
      counter += 1;
      return counter;
    },
    newEventId: () => asEventId(`loop-event-${counter}`),
    newTurnId: () => {
      turns += 1;
      return asTurnId(`loop-turn-${turns}`);
    },
    newToolExecutionId: () => {
      executions += 1;
      return asToolExecutionId(`loop-exec-${executions}`);
    },
  };
}

async function createdSession(store: MemoryStore): Promise<void> {
  const event = sessionCreated(1);
  await store.append([{ ...event, sessionId: SESSION_ID }], 0);
}

const TEXT = (text: string): ScriptItem => ({ kind: "event", event: { type: "textDelta", text } });
const COMPLETED: ScriptItem = { kind: "event", event: { type: "completed", finishReason: "stop" } };
const TOOL_CALLS_COMPLETED: ScriptItem = {
  kind: "event",
  event: { type: "completed", finishReason: "toolCalls" },
};
const PROVIDER_ERROR: ScriptItem = {
  kind: "event",
  event: {
    type: "providerError",
    error: { kind: "network", retryable: true, message: "socket reset" },
  },
};
const WAIT_FOR_ABORT: ScriptItem = { kind: "waitForAbort" };

function echoTool(records: string[]): ToolDefinition {
  return {
    name: "echo",
    description: "echoes its input",
    effect: "read_only",
    inputSchema: z.object({ message: z.string() }),
    parametersJson:
      '{"type":"object","properties":{"message":{"type":"string"}},"required":["message"]}',
    async execute(_context: ToolExecutionContext, input: unknown): Promise<ToolExecutionOutcome> {
      const { message } = z.object({ message: z.string() }).parse(input);
      records.push(message);
      return { status: "succeeded", resultJson: JSON.stringify({ echoed: message }) };
    },
  };
}

const SIGNAL = (): { signal: AbortSignal } => ({ signal: new AbortController().signal });

describe("runTurn vertical behavior", () => {
  test("a text-only turn completes and closes the turn", async () => {
    const store = inMemoryEventStore();
    await createdSession(store);
    const model = new ScriptedModelProvider([TEXT("hello"), COMPLETED]);
    const deps = loopDeps(store, model);

    const outcome = await runTurn(deps, { input: "hi" }, SIGNAL());

    expect(outcome).toEqual({ kind: "completed", finalText: "hello" });
    const events = await store.readStream(SESSION_ID);
    expect(events.map((event) => event.type)).toEqual([
      "SessionCreated",
      "TurnStarted",
      "ModelRequestStarted",
      "ModelResponseCompleted",
      "TurnCompleted",
    ]);
    const turnStart = events[1];
    if (turnStart?.type !== "TurnStarted") {
      throw new Error("expected a TurnStarted event");
    }
    expect(turnStart.payload).toStrictEqual({
      turnId: turnStart.payload.turnId,
      input: "hi",
    });
    expect(model.requests.length).toBe(1);
    expect(model.requests[0]?.messages[0]).toEqual({
      role: "system",
      text: "You are a test harness.",
    });
    expect(model.requests[0]?.messages[1]).toEqual({ role: "user", text: "hi" });
  });

  test("a tool call round-trip executes the tool once and feeds the result back", async () => {
    const store = inMemoryEventStore();
    await createdSession(store);
    const records: string[] = [];
    const model = new ScriptedModelProvider(
      [
        { kind: "event", event: { type: "toolCallStart", toolCallId: "call-1", name: "echo" } },
        {
          kind: "event",
          event: {
            type: "toolCallDelta",
            toolCallId: "call-1",
            argumentsDelta: '{"message":"ping"',
          },
        },
        {
          kind: "event",
          event: { type: "toolCallDelta", toolCallId: "call-1", argumentsDelta: "}" },
        },
        { kind: "event", event: { type: "toolCallEnd", toolCallId: "call-1" } },
        TOOL_CALLS_COMPLETED,
      ],
      [TEXT("done"), COMPLETED],
    );
    const deps = loopDeps(store, model, [echoTool(records)]);

    const outcome = await runTurn(deps, { input: "echo ping" }, SIGNAL());

    expect(outcome).toEqual({ kind: "completed", finalText: "done" });
    expect(records).toEqual(["ping"]);

    const events = await store.readStream(SESSION_ID);
    const proposal = events.find((event) => event.type === "ToolProposed");
    expect(proposal?.payload).toMatchObject({ name: "echo", toolCallId: "call-1" });

    const secondRequest = model.requests[1];
    const toolMessage = secondRequest?.messages.find((message) => message.role === "tool");
    expect(toolMessage).toEqual({
      role: "tool",
      toolCallId: "call-1",
      text: JSON.stringify({ status: "succeeded", result: { echoed: "ping" } }),
    });
  });

  test("a retryable provider failure is retried within the same turn", async () => {
    const store = inMemoryEventStore();
    await createdSession(store);
    const model = new ScriptedModelProvider([PROVIDER_ERROR], [TEXT("recovered"), COMPLETED]);
    const deps = loopDeps(store, model);

    const outcome = await runTurn(deps, { input: "hi" }, SIGNAL());

    expect(outcome).toEqual({ kind: "completed", finalText: "recovered" });
    const types = (await store.readStream(SESSION_ID)).map((event) => event.type);
    expect(types).toContain("ModelRequestFailed");
    expect(types.filter((type) => type === "ModelRequestStarted")).toHaveLength(2);
  });

  test("consecutive model failures pause the turn and leave it open", async () => {
    const store = inMemoryEventStore();
    await createdSession(store);
    const model = new ScriptedModelProvider([PROVIDER_ERROR], [PROVIDER_ERROR]);
    const deps = loopDeps(store, model);

    const outcome = await runTurn(
      deps,
      { input: "hi" },
      {
        signal: new AbortController().signal,
        guards: { maxStepsPerTurn: 8, maxConsecutiveModelFailures: 2 },
      },
    );

    expect(outcome).toEqual({
      kind: "paused",
      reason: "model failed 2 times in a row (network)",
    });
    const events = await store.readStream(SESSION_ID);
    expect(events.some((event) => event.type === "TurnCompleted")).toBe(false);
  });

  test("a paused open turn resumes without a new TurnStarted and without input", async () => {
    const store = inMemoryEventStore();
    await createdSession(store);
    const failTwice = new ScriptedModelProvider([PROVIDER_ERROR], [PROVIDER_ERROR]);
    const deps = loopDeps(store, failTwice);
    await runTurn(
      deps,
      { input: "hi" },
      {
        signal: new AbortController().signal,
        guards: { maxStepsPerTurn: 8, maxConsecutiveModelFailures: 2 },
      },
    );

    const resumer = new ScriptedModelProvider([TEXT("later"), COMPLETED]);
    const resumeDeps = loopDeps(store, resumer);
    const outcome = await runTurn(resumeDeps, {}, SIGNAL());

    expect(outcome).toEqual({ kind: "completed", finalText: "later" });
    const events = await store.readStream(SESSION_ID);
    expect(events.filter((event) => event.type === "TurnStarted")).toHaveLength(1);
  });

  test("a cancelled stream is recorded as a failed request and returns cancelled", async () => {
    const store = inMemoryEventStore();
    await createdSession(store);
    const model = new ScriptedModelProvider([WAIT_FOR_ABORT]);
    const deps = loopDeps(store, model);

    const controller = new AbortController();
    const outcomePromise = runTurn(deps, { input: "hi" }, { signal: controller.signal });
    controller.abort();
    const outcome = await outcomePromise;

    expect(outcome).toEqual({ kind: "cancelled" });
    const events = await store.readStream(SESSION_ID);
    const failure = events.find((event) => event.type === "ModelRequestFailed");
    expect(failure?.payload).toMatchObject({ kind: "unknown" });
    expect(events.some((event) => event.type === "TurnCompleted")).toBe(false);
  });

  test("the step budget pauses a turn that never stops calling tools", async () => {
    const store = inMemoryEventStore();
    await createdSession(store);
    const records: string[] = [];
    const toolLoop: ScriptItem[] = [
      { kind: "event", event: { type: "toolCallStart", toolCallId: "call-loop", name: "echo" } },
      {
        kind: "event",
        event: {
          type: "toolCallDelta",
          toolCallId: "call-loop",
          argumentsDelta: '{"message":"again"}',
        },
      },
      { kind: "event", event: { type: "toolCallEnd", toolCallId: "call-loop" } },
      TOOL_CALLS_COMPLETED,
    ];
    const model = new ScriptedModelProvider(toolLoop, toolLoop, toolLoop);
    const deps = loopDeps(store, model, [echoTool(records)]);

    const outcome = await runTurn(
      deps,
      { input: "loop forever" },
      {
        signal: new AbortController().signal,
        guards: { maxStepsPerTurn: 2, maxConsecutiveModelFailures: 5 },
      },
    );

    expect(outcome).toEqual({
      kind: "paused",
      reason: "turn exceeded 2 model steps without a final answer",
    });
    expect(records).toEqual(["again", "again"]);
  });

  test("passing input while a turn is open fails fast", async () => {
    const store = inMemoryEventStore();
    await createdSession(store);
    const model = new ScriptedModelProvider([PROVIDER_ERROR]);
    const deps = loopDeps(store, model);
    await runTurn(
      deps,
      { input: "hi" },
      {
        signal: new AbortController().signal,
        guards: { maxStepsPerTurn: 8, maxConsecutiveModelFailures: 1 },
      },
    );

    await expect(runTurn(deps, { input: "again" }, SIGNAL())).rejects.toThrow(/already open/u);
  });

  test("runTurn refuses sessions that are not ACTIVE", async () => {
    const store = inMemoryEventStore();
    const model = new ScriptedModelProvider([TEXT("x"), COMPLETED]);
    const deps = loopDeps(store, model);
    await expect(runTurn(deps, { input: "hi" }, SIGNAL())).rejects.toThrow(
      /requires an ACTIVE session/u,
    );
  });

  test("tools with invalid parametersJson are rejected before any event is appended", async () => {
    const store = inMemoryEventStore();
    await createdSession(store);
    const model = new ScriptedModelProvider([TEXT("x"), COMPLETED]);
    const broken: ToolDefinition = {
      ...echoTool([]),
      parametersJson: "{not json",
    };
    const deps = loopDeps(store, model, [broken]);
    await expect(runTurn(deps, { input: "hi" }, SIGNAL())).rejects.toThrow(SyntaxError);
    expect((await store.readStream(SESSION_ID)).length).toBe(1);
  });

  test("guard validation is fail-closed", () => {
    expect(() =>
      validateTurnGuards({ maxStepsPerTurn: 0, maxConsecutiveModelFailures: 1 }),
    ).toThrow(InvalidTurnGuardsError);
    expect(() =>
      validateTurnGuards({ maxStepsPerTurn: 1.5, maxConsecutiveModelFailures: 1 }),
    ).toThrow(InvalidTurnGuardsError);
    expect(() =>
      validateTurnGuards({ maxStepsPerTurn: 1, maxConsecutiveModelFailures: 0 }),
    ).toThrow(InvalidTurnGuardsError);
  });
});

describe("projectConversation", () => {
  const stream = (): SessionEventUnion[] =>
    [
      sessionCreated(1),
      turnStarted(2, 1, "list the workspace"),
      modelRequestStarted(3),
      modelResponseCompleted(4, {
        toolCalls: [{ id: "call-1", name: "list_dir", argumentsJson: '{"path":"."}' }],
      }),
      toolProposed(5, 1, { name: "list_dir", argumentsJson: '{"path":"."}', toolCallId: "call-1" }),
      toolSucceeded(6, 1, '{"entries":[]}'),
      modelRequestStarted(7),
      modelResponseCompleted(8, {
        toolCalls: [{ id: "call-2", name: "write_file", argumentsJson: "{}" }],
      }),
      toolProposed(9, 2, { name: "write_file", argumentsJson: "{}", toolCallId: "call-2" }),
      toolRejected(10, 2, "effect non_idempotent_write is not permitted"),
      modelResponseCompleted(11, { text: "done listing" }),
    ].map((event) => ({ ...event, sessionId: SESSION_ID }));

  test("rebuilds user, assistant, and tool messages in event order", () => {
    const messages = projectConversation(stream());
    expect(messages).toEqual([
      { role: "user", text: "list the workspace" },
      {
        role: "assistant",
        toolCalls: [{ id: "call-1", name: "list_dir", argumentsJson: '{"path":"."}' }],
      },
      {
        role: "tool",
        toolCallId: "call-1",
        text: JSON.stringify({ status: "succeeded", result: { entries: [] } }),
      },
      {
        role: "assistant",
        toolCalls: [{ id: "call-2", name: "write_file", argumentsJson: "{}" }],
      },
      {
        role: "tool",
        toolCallId: "call-2",
        text: JSON.stringify({
          status: "rejected",
          reason: "effect non_idempotent_write is not permitted",
        }),
      },
      { role: "assistant", text: "done listing" },
    ]);
  });

  test("is a pure projection: the same stream yields the same messages twice", () => {
    expect(projectConversation(stream())).toEqual(projectConversation(stream()));
  });

  test("tool executions without a model correlation fall back to the execution id", () => {
    const messages = projectConversation(
      [toolProposed(1, 7), toolFailed(2, 7, "boom")].map((event) => ({
        ...event,
        sessionId: SESSION_ID,
      })),
    );
    expect(messages).toEqual([
      {
        role: "tool",
        toolCallId: "tool-exec-7",
        text: JSON.stringify({ status: "failed", message: "boom" }),
      },
    ]);
  });

  test("a reconciled execution appends the settled fact after the indeterminate one", () => {
    const messages = projectConversation(
      [
        toolProposed(1, 3, { name: "send_payment", toolCallId: "call-3" }),
        toolIndeterminate(2, 3, "response lost after send"),
        toolReconciled(3, 3, "succeeded", '{"paymentId":"pay_1"}'),
      ].map((event) => ({ ...event, sessionId: SESSION_ID })),
    );
    expect(messages).toEqual([
      {
        role: "tool",
        toolCallId: "call-3",
        text: JSON.stringify({ status: "indeterminate", reason: "response lost after send" }),
      },
      {
        role: "tool",
        toolCallId: "call-3",
        text: JSON.stringify({
          status: "succeeded",
          reconciled: true,
          result: { paymentId: "pay_1" },
        }),
      },
    ]);
  });

  test("a reconciliation that stays indeterminate reports the new reason honestly", () => {
    const messages = projectConversation(
      [
        toolProposed(1, 3, { name: "send_payment" }),
        toolIndeterminate(2, 3, "response lost after send"),
        toolReconciled(3, 3, "indeterminate", "provider query timed out too"),
      ].map((event) => ({ ...event, sessionId: SESSION_ID })),
    );
    expect(messages.at(-1)).toEqual({
      role: "tool",
      toolCallId: "tool-exec-3",
      text: JSON.stringify({
        status: "indeterminate",
        reconciled: true,
        reason: "provider query timed out too",
      }),
    });
  });
});
