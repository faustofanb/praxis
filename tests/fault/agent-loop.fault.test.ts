import type { EventStore, SessionEventUnion, ToolDefinition } from "@praxis/contracts";
import { asEventId, asSessionId, asToolExecutionId, asTurnId } from "@praxis/contracts";
import { type AgentLoopDeps, foldSessionEvents, runTurn } from "@praxis/core";
import { ScriptedModelProvider, type ScriptItem } from "@praxis/testkit";
import { describe, expect, test } from "vitest";
import { z } from "zod";
import { inMemoryEventStore } from "../helpers/in-memory-event-store";
import {
  modelRequestStarted,
  modelResponseCompleted,
  sessionCreated,
  turnStarted,
} from "../helpers/session-events";

const SESSION_ID = asSessionId("session-loop-fault");

type MemoryStore = ReturnType<typeof inMemoryEventStore>;

function faultDeps(
  store: EventStore,
  model: ScriptedModelProvider,
  tools: readonly ToolDefinition[] = [],
): AgentLoopDeps {
  let counter = 5000;
  let turns = 0;
  let executions = 0;
  return {
    store,
    sessionId: SESSION_ID,
    model,
    modelId: "scripted-model",
    systemPrompt: "fault harness",
    tools,
    now: () => {
      counter += 1;
      return counter;
    },
    newEventId: () => asEventId(`fault-event-${counter}`),
    newTurnId: () => {
      turns += 1;
      return asTurnId(`fault-turn-${turns}`);
    },
    newToolExecutionId: () => {
      executions += 1;
      return asToolExecutionId(`fault-exec-${executions}`);
    },
  };
}

async function seed(store: MemoryStore, events: SessionEventUnion[]): Promise<void> {
  await store.append(
    events.map((event) => ({ ...event, sessionId: SESSION_ID })),
    0,
  );
}

const TEXT = (text: string): ScriptItem => ({ kind: "event", event: { type: "textDelta", text } });
const COMPLETED: ScriptItem = { kind: "event", event: { type: "completed", finishReason: "stop" } };
const TOOL_CALL_STEP: ScriptItem[] = [
  { kind: "event", event: { type: "toolCallStart", toolCallId: "call-1", name: "probe" } },
  { kind: "event", event: { type: "toolCallDelta", toolCallId: "call-1", argumentsDelta: "{}" } },
  { kind: "event", event: { type: "toolCallEnd", toolCallId: "call-1" } },
  { kind: "event", event: { type: "completed", finishReason: "toolCalls" } },
];

const SIGNAL = { signal: new AbortController().signal };

const readTool = (calls: string[]): ToolDefinition => ({
  name: "probe",
  description: "fault probe",
  effect: "read_only",
  inputSchema: z.object({}),
  parametersJson: '{"type":"object"}',
  async execute(_context, _input) {
    calls.push("probe");
    return { status: "succeeded", resultJson: '"probed"' };
  },
});

describe("agent loop fault paths", () => {
  test("a provider crash after a tool round-trip leaves a recoverable pending request", async () => {
    const store = inMemoryEventStore();
    await seed(store, [sessionCreated(1)]);
    const calls: string[] = [];
    // Step 1 streams a tool call; step 2 has no script left, so the provider
    // throws while the loop already holds a dangling ModelRequestStarted.
    const crashed = new ScriptedModelProvider(TOOL_CALL_STEP);

    await expect(
      runTurn(faultDeps(store, crashed, [readTool(calls)]), { input: "hi" }, SIGNAL),
    ).rejects.toThrow(/script exhausted/u);
    expect(calls).toEqual(["probe"]);

    const afterCrash = foldSessionEvents(await store.readStream(SESSION_ID));
    expect(afterCrash.pendingModelRequest).toEqual({ model: "scripted-model" });

    const resumer = new ScriptedModelProvider([TEXT("recovered"), COMPLETED]);
    const outcome = await runTurn(faultDeps(store, resumer, [readTool(calls)]), {}, SIGNAL);
    expect(outcome).toEqual({ kind: "completed", finalText: "recovered" });

    const events = await store.readStream(SESSION_ID);
    const failure = events.find((event) => event.type === "ModelRequestFailed");
    expect(failure?.payload).toMatchObject({
      kind: "unknown",
      message: "process crashed before the model stream finished; response unknown",
    });
    expect(calls).toEqual(["probe"]);
  });

  test("a store crash mid-loop leaves a legal stream that recovery closes honestly", async () => {
    const real = inMemoryEventStore();
    await seed(real, [sessionCreated(1)]);
    const calls: string[] = [];
    const model = new ScriptedModelProvider(TOOL_CALL_STEP, [TEXT("done"), COMPLETED]);

    // Crash on the 4th loop append (TurnStarted, ModelRequestStarted,
    // ModelResponseCompleted, ToolProposed).
    let appends = 0;
    const crashing: EventStore = {
      append: async (events, expectedHeadSeq) => {
        appends += 1;
        if (appends === 4) {
          throw new Error("simulated store crash on append");
        }
        return real.append(events, expectedHeadSeq);
      },
      readStream: (sessionId) => real.readStream(sessionId),
    };

    await expect(
      runTurn(faultDeps(crashing, model, [readTool(calls)]), { input: "hi" }, SIGNAL),
    ).rejects.toThrow(/store crash/u);

    // The persisted prefix still folds: the model response landed, the tool
    // proposal did not, and nothing executed.
    const afterCrash = foldSessionEvents(await real.readStream(SESSION_ID));
    expect(afterCrash.pendingModelRequest).toBeUndefined();
    expect(afterCrash.toolExecutions.size).toBe(0);
    expect(calls).toEqual([]);

    const outcome = await runTurn(faultDeps(real, model, [readTool(calls)]), {}, SIGNAL);
    expect(outcome).toEqual({ kind: "completed", finalText: "done" });
  });

  test("a crash after ToolAuthorized recovers as an explicit rejection, not an assumption", async () => {
    const store = inMemoryEventStore();
    const calls: string[] = [];
    await seed(store, [
      sessionCreated(1),
      turnStarted(2, 1, "use the tool"),
      modelRequestStarted(3),
      modelResponseCompleted(4, {
        toolCalls: [{ id: "call-1", name: "probe", argumentsJson: "{}" }],
      }),
      toolProposedAt(5),
      toolAuthorizedAt(6),
    ]);

    const model = new ScriptedModelProvider([TEXT("recovered"), COMPLETED]);
    const outcome = await runTurn(faultDeps(store, model, [readTool(calls)]), {}, SIGNAL);

    expect(outcome).toEqual({ kind: "completed", finalText: "recovered" });
    expect(calls).toEqual([]);
    const events = await store.readStream(SESSION_ID);
    const rejection = events.find((event) => event.type === "ToolRejected");
    expect(rejection?.payload).toMatchObject({
      toolExecutionId: "tool-exec-1",
      reason: "abandoned at authorization by crash recovery; never executed",
    });
  });
});

function toolProposedAt(seq: number): SessionEventUnion {
  return {
    id: asEventId(`fault-proposed-${seq}`),
    sessionId: SESSION_ID,
    seq,
    schemaVersion: 1,
    occurredAt: 5000 + seq,
    actor: { kind: "system" },
    type: "ToolProposed",
    payload: {
      toolExecutionId: asToolExecutionId("tool-exec-1"),
      name: "probe",
      argumentsJson: "{}",
      effect: "read_only",
      toolCallId: "call-1",
    },
  };
}

function toolAuthorizedAt(seq: number): SessionEventUnion {
  return {
    id: asEventId(`fault-authorized-${seq}`),
    sessionId: SESSION_ID,
    seq,
    schemaVersion: 1,
    occurredAt: 5000 + seq,
    actor: { kind: "system" },
    type: "ToolAuthorized",
    payload: { toolExecutionId: asToolExecutionId("tool-exec-1") },
  };
}
