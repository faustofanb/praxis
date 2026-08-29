import { afterEach, beforeEach, describe, expect, test } from "bun:test";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { EventStore, ReconciliationOutcome, ToolDefinition } from "@praxis/contracts";
import { asEventId, asToolExecutionId, asTurnId, EMPTY_STREAM_HEAD_SEQ } from "@praxis/contracts";
import type { AgentLoopDeps, ToolAuthorizer } from "@praxis/core";
import { foldSessionEvents, runTurn } from "@praxis/core";
import type { SessionStore } from "@praxis/store-sqlite";
import { openSessionStore } from "@praxis/store-sqlite";
import { ScriptedModelProvider, type ScriptItem } from "@praxis/testkit";
import { z } from "zod";
import { sessionCreated, TEST_SESSION_ID } from "../helpers/session-events";

/**
 * Durable recovery evidence (docs/02 section 17 steps 1-6): a crash between
 * durable events must survive an actual store close/reopen — the persisted
 * prefix replays to the same derived state, the dangling execution settles
 * through reconciliation, and the side effect happens exactly once across
 * the process boundary. The fault matrix runs in memory; this is the same
 * crown-jewel cell (success in hand, terminal append lost) on real storage.
 */

type Counters = { executes: number; reconciles: number };

const allowEverything: ToolAuthorizer = () => ({ decision: "authorized" });

const RUN_OPTIONS = {
  signal: new AbortController().signal,
  authorizer: allowEverything,
};

const TEXT = (text: string): ScriptItem => ({ kind: "event", event: { type: "textDelta", text } });
const COMPLETED: ScriptItem = { kind: "event", event: { type: "completed", finishReason: "stop" } };
const TOOL_CALL_STEP: ScriptItem[] = [
  { kind: "event", event: { type: "toolCallStart", toolCallId: "call-1", name: "persist" } },
  {
    kind: "event",
    event: { type: "toolCallDelta", toolCallId: "call-1", argumentsDelta: '{"path":"out.txt"}' },
  },
  { kind: "event", event: { type: "toolCallEnd", toolCallId: "call-1" } },
  { kind: "event", event: { type: "completed", finishReason: "toolCalls" } },
];

/** Each simulated boot gets its own id stream — a resumed process never reuses dead ids. */
function idSource(prefix: string) {
  let counter = 0;
  let turns = 0;
  let executions = 0;
  return {
    now: () => {
      counter += 1;
      return 9000 + counter;
    },
    newEventId: () => asEventId(`${prefix}-event-${counter}`),
    newTurnId: () => {
      turns += 1;
      return asTurnId(`${prefix}-turn-${turns}`);
    },
    newToolExecutionId: () => {
      executions += 1;
      return asToolExecutionId(`tool-exec-${executions}`);
    },
  };
}

function persistTool(counters: Counters): ToolDefinition {
  return {
    name: "persist",
    description: "durability write tool",
    effect: "reconcilable_write",
    requiredCapability: { name: "files.persist" },
    inputSchema: z.object({ path: z.string() }),
    parametersJson: '{"type":"object"}',
    async execute() {
      counters.executes += 1;
      return { status: "succeeded", resultJson: '{"written":true}' };
    },
    async reconcile(): Promise<ReconciliationOutcome> {
      counters.reconciles += 1;
      return { status: "succeeded", resultJson: '{"verified":true}' };
    },
  };
}

function loopDeps(
  store: EventStore,
  model: ScriptedModelProvider,
  tools: readonly ToolDefinition[],
  ids: ReturnType<typeof idSource>,
): AgentLoopDeps {
  return {
    store,
    sessionId: TEST_SESSION_ID,
    model,
    modelId: "scripted-model",
    systemPrompt: "durability harness",
    tools,
    ...ids,
  };
}

let dir: string;
let dbPath: string;

beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), "praxis-crash-recovery-"));
  dbPath = join(dir, "store.sqlite");
});

afterEach(() => {
  rmSync(dir, { recursive: true, force: true });
});

describe("durable crash recovery across store reopen", () => {
  test("a crash before the result append survives close/reopen and settles via reconciliation, executed exactly once", async () => {
    const counters: Counters = { executes: 0, reconciles: 0 };
    const tool = persistTool(counters);
    const bootA = idSource("boot-a");

    // Boot A: the tool runs and returns success; the terminal append dies
    // with the process. Wrapper counts only appends made through runTurn
    // (the seed append goes straight to the real store).
    const storeA = openSessionStore(dbPath);
    await storeA.append([sessionCreated(1)], EMPTY_STREAM_HEAD_SEQ);
    let appends = 0;
    const crashing: EventStore = {
      append: async (events, expectedHeadSeq) => {
        appends += 1;
        if (appends === 7) {
          throw new Error("power lost before the terminal append");
        }
        return storeA.append(events, expectedHeadSeq);
      },
      readStream: (sessionId) => storeA.readStream(sessionId),
    };

    await expect(
      runTurn(
        loopDeps(crashing, new ScriptedModelProvider(TOOL_CALL_STEP), [tool], bootA),
        { input: "hi" },
        RUN_OPTIONS,
      ),
    ).rejects.toThrow(/power lost/u);
    expect(counters.executes).toBe(1);

    // Process death: the store is closed with the dangling execution on disk.
    const onDiskAtDeath = await storeA.readStream(TEST_SESSION_ID);
    storeA.close();

    // Boot B: reopen the same file — the persisted prefix replays unchanged
    // (section 17 steps 1-4) and the execution dangles as EXECUTING.
    const storeB: SessionStore = openSessionStore(dbPath);
    const replayed = await storeB.readStream(TEST_SESSION_ID);
    expect(replayed).toEqual(onDiskAtDeath);
    const state = foldSessionEvents(replayed);
    expect(state.status).toBe("ACTIVE");
    expect(state.currentTurnId).toBeDefined();
    expect(state.toolExecutions.get(asToolExecutionId("tool-exec-1"))?.status).toBe("EXECUTING");

    // Steps 5-6: dangling EXECUTING closes as ToolIndeterminate, the
    // verification-only reconcile settles it, the turn completes — the side
    // effect is never repeated across the process boundary.
    const bootB = idSource("boot-b");
    const outcome = await runTurn(
      loopDeps(storeB, new ScriptedModelProvider([TEXT("recovered"), COMPLETED]), [tool], bootB),
      {},
      RUN_OPTIONS,
    );
    expect(outcome).toEqual({ kind: "completed", finalText: "recovered" });
    expect(counters).toEqual({ executes: 1, reconciles: 1 });

    const events = await storeB.readStream(TEST_SESSION_ID);
    const types = events.map((event) => event.type);
    expect(types.includes("ToolSucceeded")).toBe(false);
    expect(types).toEqual([
      "SessionCreated",
      "TurnStarted",
      "ModelRequestStarted",
      "ModelResponseCompleted",
      "ToolProposed",
      "ToolAuthorized",
      "ToolStarted",
      "ToolIndeterminate",
      "ToolReconciled",
      "ModelRequestStarted",
      "ModelResponseCompleted",
      "TurnCompleted",
    ]);
    const settled = foldSessionEvents(events);
    expect(settled.toolExecutions.get(asToolExecutionId("tool-exec-1"))?.status).toBe("SUCCEEDED");
    storeB.close();
  });
});
