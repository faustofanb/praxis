import type {
  EventStore,
  ReconciliationOutcome,
  SessionEventUnion,
  ToolDefinition,
} from "@praxis/contracts";
import { asEventId, asToolExecutionId, asTurnId } from "@praxis/contracts";
import type { ToolAuthorizer } from "@praxis/core";
import { type AgentLoopDeps, foldSessionEvents, runTurn } from "@praxis/core";
import { ScriptedModelProvider, type ScriptItem } from "@praxis/testkit";
import { describe, expect, test } from "vitest";
import { z } from "zod";
import { inMemoryEventStore } from "../helpers/in-memory-event-store";
import {
  modelRequestStarted,
  modelResponseCompleted,
  sessionCreated,
  sessionResumed,
  TEST_SESSION_ID,
  toolAuthorized,
  toolProposed,
  toolStarted,
  turnStarted,
} from "../helpers/session-events";

/**
 * Crash matrix (docs/03 M5.3; docs/02 section 17): a crash injected at each
 * critical boundary of the durable tool lifecycle. Every cell asserts the
 * same four laws — the persisted prefix folds legally, resume appends the
 * honest terminal fact for that boundary, the dangerous tool's execute
 * counter never grows past its pre-crash count (no duplicated side effect),
 * and recovery is idempotent (a later turn appends no new recovery facts).
 */

type MemoryStore = ReturnType<typeof inMemoryEventStore>;
type Counters = { executes: number; reconciles: number };
type IdSource = Pick<AgentLoopDeps, "now" | "newEventId" | "newTurnId" | "newToolExecutionId">;

const SESSION_ID = TEST_SESSION_ID;

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

/** One id source per test: turn/execution counters must survive across runTurn calls. */
function idSource(): IdSource {
  let counter = 7000;
  let turns = 0;
  let executions = 0;
  return {
    now: () => {
      counter += 1;
      return counter;
    },
    newEventId: () => asEventId(`matrix-event-${counter}`),
    newTurnId: () => {
      turns += 1;
      return asTurnId(`matrix-turn-${turns}`);
    },
    newToolExecutionId: () => {
      executions += 1;
      return asToolExecutionId(`tool-exec-${executions}`);
    },
  };
}

/** The dangerous tool under matrix: a reconcilable write with counters. */
function persistTool(
  counters: Counters,
  behavior: {
    execute?: () => Promise<never>;
    reconcile?: () => Promise<ReconciliationOutcome>;
  } = {},
): ToolDefinition {
  return {
    name: "persist",
    description: "matrix write tool",
    effect: "reconcilable_write",
    requiredCapability: { name: "files.persist" },
    inputSchema: z.object({ path: z.string() }),
    parametersJson: '{"type":"object"}',
    async execute() {
      counters.executes += 1;
      if (behavior.execute) {
        return behavior.execute();
      }
      return { status: "succeeded", resultJson: '{"written":true}' };
    },
    async reconcile(): Promise<ReconciliationOutcome> {
      counters.reconciles += 1;
      if (behavior.reconcile) {
        return behavior.reconcile();
      }
      return { status: "succeeded", resultJson: '{"verified":true}' };
    },
  };
}

function matrixDeps(
  store: EventStore,
  model: ScriptedModelProvider,
  tools: readonly ToolDefinition[],
  ids: IdSource,
): AgentLoopDeps {
  return {
    store,
    sessionId: SESSION_ID,
    model,
    modelId: "scripted-model",
    systemPrompt: "crash matrix",
    tools,
    ...ids,
  };
}

/** Fail exactly the nth append (1-based, across the whole store) like a process dying mid-append. */
function crashOnAppend(real: MemoryStore, n: number): EventStore {
  let appends = 0;
  return {
    append: async (events, expectedHeadSeq) => {
      appends += 1;
      if (appends === n) {
        throw new Error(`matrix crash before append #${n}`);
      }
      return real.append(events, expectedHeadSeq);
    },
    readStream: (sessionId) => real.readStream(sessionId),
  };
}

async function readEvents(store: EventStore): Promise<readonly SessionEventUnion[]> {
  return store.readStream(SESSION_ID);
}

function typesOf(events: readonly SessionEventUnion[]): string[] {
  return events.map((event) => event.type);
}

/** No recovery fact may appear in what a later turn appends — recovery is done once. */
const RECOVERY_TYPES = new Set(["ToolRejected", "ToolIndeterminate", "ModelRequestFailed"]);

async function nextTurnAppendsNoRecoveryFacts(
  store: EventStore,
  tools: readonly ToolDefinition[],
  ids: IdSource,
  tail: readonly ScriptItem[],
): Promise<void> {
  const before = await readEvents(store);
  const outcome = await runTurn(
    matrixDeps(store, new ScriptedModelProvider(tail), tools, ids),
    { input: "next" },
    RUN_OPTIONS,
  );
  expect(outcome.kind).toBe("completed");
  const appended = (await readEvents(store)).slice(before.length);
  expect(appended.filter((event) => RECOVERY_TYPES.has(event.type))).toEqual([]);
}

describe("crash matrix (docs/03 M5.3)", () => {
  test("before append: crash before ToolProposed persists — nothing to recover, model re-asked, zero executions", async () => {
    const real = inMemoryEventStore();
    await real.append([sessionCreated(1)], 0);
    const counters: Counters = { executes: 0, reconciles: 0 };
    const tool = persistTool(counters);
    const ids = idSource();
    // Appends: TurnStarted(1) ModelRequestStarted(2) ModelResponseCompleted(3)
    // ToolProposed(4 — crashes). The tool-call intent is durable, the
    // execution never became a fact.
    const crashing = crashOnAppend(real, 4);

    await expect(
      runTurn(
        matrixDeps(crashing, new ScriptedModelProvider(TOOL_CALL_STEP), [tool], ids),
        { input: "hi" },
        RUN_OPTIONS,
      ),
    ).rejects.toThrow(/matrix crash/u);

    const prefix = foldSessionEvents(await readEvents(real));
    expect(prefix.headSeq).toBe(4);
    expect(prefix.toolExecutions.size).toBe(0);

    const outcome = await runTurn(
      matrixDeps(real, new ScriptedModelProvider([TEXT("done"), COMPLETED]), [tool], ids),
      {},
      RUN_OPTIONS,
    );
    expect(outcome).toEqual({ kind: "completed", finalText: "done" });
    expect(counters).toEqual({ executes: 0, reconciles: 0 });
    expect(typesOf(await readEvents(real)).includes("ToolProposed")).toBe(false);
    await nextTurnAppendsNoRecoveryFacts(real, [tool], ids, [TEXT("steady"), COMPLETED]);
  });

  test("before execute (at proposal): dangling PROPOSED recovers as an explicit rejection, never executed", async () => {
    const real = inMemoryEventStore();
    await real.append([sessionCreated(1)], 0);
    const counters: Counters = { executes: 0, reconciles: 0 };
    const tool = persistTool(counters);
    const ids = idSource();
    // ToolProposed(4) lands; ToolAuthorized(5 — crashes).
    const crashing = crashOnAppend(real, 5);

    await expect(
      runTurn(
        matrixDeps(crashing, new ScriptedModelProvider(TOOL_CALL_STEP), [tool], ids),
        { input: "hi" },
        RUN_OPTIONS,
      ),
    ).rejects.toThrow(/matrix crash/u);

    const prefix = foldSessionEvents(await readEvents(real));
    expect(prefix.toolExecutions.get(asToolExecutionId("tool-exec-1"))?.status).toBe("PROPOSED");

    const outcome = await runTurn(
      matrixDeps(real, new ScriptedModelProvider([TEXT("recovered"), COMPLETED]), [tool], ids),
      {},
      RUN_OPTIONS,
    );
    expect(outcome).toEqual({ kind: "completed", finalText: "recovered" });
    expect(counters.executes).toBe(0);

    const events = await readEvents(real);
    const rejection = events.find((event) => event.type === "ToolRejected");
    expect(rejection?.payload).toMatchObject({
      toolExecutionId: "tool-exec-1",
      reason: "abandoned at proposal by crash recovery; never executed",
    });
    await nextTurnAppendsNoRecoveryFacts(real, [tool], ids, [TEXT("steady"), COMPLETED]);
  });

  test("before execute (at authorization): dangling AUTHORIZED recovers as an explicit rejection, never executed", async () => {
    const real = inMemoryEventStore();
    await real.append([sessionCreated(1)], 0);
    const counters: Counters = { executes: 0, reconciles: 0 };
    const tool = persistTool(counters);
    const ids = idSource();
    // ToolAuthorized(5) lands; ToolStarted(6 — crashes).
    const crashing = crashOnAppend(real, 6);

    await expect(
      runTurn(
        matrixDeps(crashing, new ScriptedModelProvider(TOOL_CALL_STEP), [tool], ids),
        { input: "hi" },
        RUN_OPTIONS,
      ),
    ).rejects.toThrow(/matrix crash/u);

    const prefix = foldSessionEvents(await readEvents(real));
    expect(prefix.toolExecutions.get(asToolExecutionId("tool-exec-1"))?.status).toBe("AUTHORIZED");

    const outcome = await runTurn(
      matrixDeps(real, new ScriptedModelProvider([TEXT("recovered"), COMPLETED]), [tool], ids),
      {},
      RUN_OPTIONS,
    );
    expect(outcome).toEqual({ kind: "completed", finalText: "recovered" });
    expect(counters.executes).toBe(0);

    const events = await readEvents(real);
    const rejection = events.find((event) => event.type === "ToolRejected");
    expect(rejection?.payload).toMatchObject({
      toolExecutionId: "tool-exec-1",
      reason: "abandoned at authorization by crash recovery; never executed",
    });
    await nextTurnAppendsNoRecoveryFacts(real, [tool], ids, [TEXT("steady"), COMPLETED]);
  });

  test("after side effect (outcome unknown): executor crash records ToolIndeterminate in flight; the next entry settles via reconcile, no re-execution", async () => {
    const store = inMemoryEventStore();
    await store.append([sessionCreated(1)], 0);
    const counters: Counters = { executes: 0, reconciles: 0 };
    const ids = idSource();
    const tool = persistTool(counters, {
      execute: () => Promise.reject(new Error("connection lost mid-write")),
    });

    // The crash happens inside execute: the runtime itself records the
    // honest indeterminate fact, the turn continues over the brief.
    const first = await runTurn(
      matrixDeps(
        store,
        new ScriptedModelProvider(TOOL_CALL_STEP, [TEXT("queued"), COMPLETED]),
        [tool],
        ids,
      ),
      { input: "hi" },
      RUN_OPTIONS,
    );
    expect(first).toEqual({ kind: "completed", finalText: "queued" });
    expect(counters).toEqual({ executes: 1, reconciles: 0 });

    const events = await readEvents(store);
    const indeterminate = events.find((event) => event.type === "ToolIndeterminate");
    expect(indeterminate?.payload).toMatchObject({
      toolExecutionId: "tool-exec-1",
      reason: "executor crashed before outcome was known: connection lost mid-write",
    });

    // The next runTurn entry re-enters reconciliation and verifies.
    const second = await runTurn(
      matrixDeps(store, new ScriptedModelProvider([TEXT("verified"), COMPLETED]), [tool], ids),
      { input: "check" },
      RUN_OPTIONS,
    );
    expect(second).toEqual({ kind: "completed", finalText: "verified" });
    expect(counters).toEqual({ executes: 1, reconciles: 1 });

    const reconciled = (await readEvents(store)).find((event) => event.type === "ToolReconciled");
    expect(reconciled?.payload).toMatchObject({
      toolExecutionId: "tool-exec-1",
      outcome: "succeeded",
      resultJson: '{"verified":true}',
    });
    await nextTurnAppendsNoRecoveryFacts(store, [tool], ids, [TEXT("steady"), COMPLETED]);
  });

  test("before result append: success in hand but append crashes — resumes indeterminate-then-reconciled, never an unverified ToolSucceeded", async () => {
    const real = inMemoryEventStore();
    await real.append([sessionCreated(1)], 0);
    const counters: Counters = { executes: 0, reconciles: 0 };
    const tool = persistTool(counters);
    const ids = idSource();
    // The tool ran and returned success; the terminal append(7 — crashes).
    // Nobody may trust the in-memory outcome after the process died.
    const crashing = crashOnAppend(real, 7);

    await expect(
      runTurn(
        matrixDeps(crashing, new ScriptedModelProvider(TOOL_CALL_STEP), [tool], ids),
        { input: "hi" },
        RUN_OPTIONS,
      ),
    ).rejects.toThrow(/matrix crash/u);
    expect(counters.executes).toBe(1);

    const prefix = foldSessionEvents(await readEvents(real));
    expect(prefix.toolExecutions.get(asToolExecutionId("tool-exec-1"))?.status).toBe("EXECUTING");

    const outcome = await runTurn(
      matrixDeps(real, new ScriptedModelProvider([TEXT("recovered"), COMPLETED]), [tool], ids),
      {},
      RUN_OPTIONS,
    );
    expect(outcome).toEqual({ kind: "completed", finalText: "recovered" });
    // Executed once before the crash, verified once after — never re-executed.
    expect(counters).toEqual({ executes: 1, reconciles: 1 });

    const events = await readEvents(real);
    expect(typesOf(events).includes("ToolSucceeded")).toBe(false);
    const indeterminate = events.find((event) => event.type === "ToolIndeterminate");
    expect(indeterminate?.payload).toMatchObject({ toolExecutionId: "tool-exec-1" });
    const reconciled = events.find((event) => event.type === "ToolReconciled");
    expect(reconciled?.payload).toMatchObject({
      toolExecutionId: "tool-exec-1",
      outcome: "succeeded",
      resultJson: '{"verified":true}',
    });
    await nextTurnAppendsNoRecoveryFacts(real, [tool], ids, [TEXT("steady"), COMPLETED]);
  });

  test("after result append: terminal fact durable — resume appends nothing new for the execution, tool ran exactly once", async () => {
    const real = inMemoryEventStore();
    await real.append([sessionCreated(1)], 0);
    const counters: Counters = { executes: 0, reconciles: 0 };
    const tool = persistTool(counters);
    const ids = idSource();
    // The full execution settles (append 7 lands); the next
    // ModelRequestStarted(8 — crashes) — nothing about the tool dangles.
    const crashing = crashOnAppend(real, 8);

    await expect(
      runTurn(
        matrixDeps(crashing, new ScriptedModelProvider(TOOL_CALL_STEP), [tool], ids),
        { input: "hi" },
        RUN_OPTIONS,
      ),
    ).rejects.toThrow(/matrix crash/u);
    expect(counters.executes).toBe(1);

    const prefix = foldSessionEvents(await readEvents(real));
    expect(prefix.toolExecutions.get(asToolExecutionId("tool-exec-1"))?.status).toBe("SUCCEEDED");

    const outcome = await runTurn(
      matrixDeps(real, new ScriptedModelProvider([TEXT("recovered"), COMPLETED]), [tool], ids),
      {},
      RUN_OPTIONS,
    );
    expect(outcome).toEqual({ kind: "completed", finalText: "recovered" });
    expect(counters).toEqual({ executes: 1, reconciles: 0 });

    const appended = (await readEvents(real)).slice(8);
    expect(typesOf(appended)).toEqual([
      "ModelRequestStarted",
      "ModelResponseCompleted",
      "TurnCompleted",
    ]);
    await nextTurnAppendsNoRecoveryFacts(real, [tool], ids, [TEXT("steady"), COMPLETED]);
  });

  test("mixed dangling: one PROPOSED and one EXECUTING recover in insertion order — rejection then indeterminate, then reconciliation", async () => {
    const store = inMemoryEventStore();
    const counters: Counters = { executes: 0, reconciles: 0 };
    const tool = persistTool(counters);
    const ids = idSource();
    // A crash between two executions of the same model response: exec 1
    // never reached execution, exec 2 crossed ToolStarted.
    await store.append(
      [
        sessionCreated(1),
        turnStarted(2, 1, "use the tools"),
        modelRequestStarted(3),
        modelResponseCompleted(4, {
          toolCalls: [
            { id: "call-1", name: "persist", argumentsJson: '{"path":"a.txt"}' },
            { id: "call-2", name: "persist", argumentsJson: '{"path":"b.txt"}' },
          ],
        }),
        toolProposed(5, 1, {
          name: "persist",
          argumentsJson: '{"path":"a.txt"}',
          effect: "reconcilable_write",
          toolCallId: "call-1",
        }),
        toolAuthorized(6, 1),
        toolProposed(7, 2, {
          name: "persist",
          argumentsJson: '{"path":"b.txt"}',
          effect: "reconcilable_write",
          toolCallId: "call-2",
        }),
        toolAuthorized(8, 2),
        toolStarted(9, 2),
      ],
      0,
    );

    const outcome = await runTurn(
      matrixDeps(store, new ScriptedModelProvider([TEXT("recovered"), COMPLETED]), [tool], ids),
      {},
      RUN_OPTIONS,
    );
    expect(outcome).toEqual({ kind: "completed", finalText: "recovered" });
    // Neither execution ran after the crash; the crossed one is verified.
    expect(counters).toEqual({ executes: 0, reconciles: 1 });

    const events = await readEvents(store);
    expect(typesOf(events.slice(9))).toEqual([
      "ToolRejected",
      "ToolIndeterminate",
      "ToolReconciled",
      "ModelRequestStarted",
      "ModelResponseCompleted",
      "TurnCompleted",
    ]);
    const rejection = events.find((event) => event.type === "ToolRejected");
    expect(rejection?.payload).toMatchObject({ toolExecutionId: "tool-exec-1" });
    const reconciled = events.find((event) => event.type === "ToolReconciled");
    expect(reconciled?.payload).toMatchObject({
      toolExecutionId: "tool-exec-2",
      outcome: "succeeded",
    });
    await nextTurnAppendsNoRecoveryFacts(store, [tool], ids, [TEXT("steady"), COMPLETED]);
  });

  test("the human loop: unresolved indeterminate pauses the session; only SessionResumed re-attempts reconciliation (docs/02 section 17 step 9)", async () => {
    const store = inMemoryEventStore();
    await store.append([sessionCreated(1)], 0);
    const counters: Counters = { executes: 0, reconciles: 0 };
    const ids = idSource();
    let verifierReachable = false;
    const tool = persistTool(counters, {
      execute: () => Promise.reject(new Error("connection lost mid-write")),
      reconcile: () =>
        verifierReachable
          ? Promise.resolve({ status: "succeeded", resultJson: '{"verified":true}' })
          : Promise.resolve({ status: "indeterminate", reason: "external verifier unreachable" }),
    });

    // Turn 1: the write crosses its side effect and dies unknown; the turn
    // itself completes over the brief carrying the pending indeterminate.
    const first = await runTurn(
      matrixDeps(
        store,
        new ScriptedModelProvider(TOOL_CALL_STEP, [TEXT("queued"), COMPLETED]),
        [tool],
        ids,
      ),
      { input: "hi" },
      RUN_OPTIONS,
    );
    expect(first).toEqual({ kind: "completed", finalText: "queued" });
    expect(counters).toEqual({ executes: 1, reconciles: 0 });

    // Turn 2 entry: reconciliation cannot verify -> escalate, pause, no model
    // call consumed (a wrong resolution would exhaust the script and throw).
    const second = await runTurn(
      matrixDeps(store, new ScriptedModelProvider([]), [tool], ids),
      { input: "check" },
      RUN_OPTIONS,
    );
    expect(second).toMatchObject({ kind: "paused" });
    expect(counters).toEqual({ executes: 1, reconciles: 1 });
    expect(foldSessionEvents(await readEvents(store)).status).toBe("PAUSED");
    expect((await readEvents(store)).at(-1)?.type).toBe("SessionPaused");

    // A paused session refuses to run.
    await expect(
      runTurn(
        matrixDeps(store, new ScriptedModelProvider([]), [tool], ids),
        { input: "sneak" },
        RUN_OPTIONS,
      ),
    ).rejects.toThrow(/requires an ACTIVE session/u);

    // The only unlock: a human-initiated SessionResumed fact.
    const head = foldSessionEvents(await readEvents(store)).headSeq;
    await store.append([sessionResumed(head + 1)], head);

    // The resumed runtime re-enters recovery; the verifier is reachable now,
    // the fact settles, and the turn continues without re-execution.
    verifierReachable = true;
    const third = await runTurn(
      matrixDeps(store, new ScriptedModelProvider([TEXT("all good"), COMPLETED]), [tool], ids),
      { input: "check again" },
      RUN_OPTIONS,
    );
    expect(third).toEqual({ kind: "completed", finalText: "all good" });
    expect(counters).toEqual({ executes: 1, reconciles: 2 });

    const events = await readEvents(store);
    expect(
      events.filter((event) => event.type === "ToolReconciled").map((event) => event.payload),
    ).toEqual([
      expect.objectContaining({ toolExecutionId: "tool-exec-1", outcome: "indeterminate" }),
      expect.objectContaining({ toolExecutionId: "tool-exec-1", outcome: "succeeded" }),
    ]);
    expect(
      foldSessionEvents(events).toolExecutions.get(asToolExecutionId("tool-exec-1"))?.status,
    ).toBe("SUCCEEDED");
  });
});
