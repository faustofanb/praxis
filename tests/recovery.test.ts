import type {
  ReconciliationOutcome,
  SessionEventUnion,
  ToolDefinition,
  ToolExecutionContext,
  ToolExecutionOutcome,
} from "@praxis/contracts";
import { asEventId, asToolExecutionId } from "@praxis/contracts";
import {
  foldSessionEvents,
  pauseForUnresolvedIndeterminates,
  type RecoveryDeps,
  reconcileIndeterminateExecutions,
} from "@praxis/core";
import { describe, expect, test } from "vitest";
import { z } from "zod";
import { inMemoryEventStore } from "./helpers/in-memory-event-store";
import {
  sessionCreated,
  TEST_SESSION_ID,
  toolAuthorized,
  toolIndeterminate,
  toolProposed,
  toolStarted,
  turnCompleted,
  turnStarted,
} from "./helpers/session-events";

/**
 * Unit law of crash-after-side-effect recovery (docs/02 sections 17 and
 * 8.3): reconciliation verifies and records, never re-executes; anything
 * short of proof stays honestly indeterminate; unresolved indeterminates
 * escalate by closing the turn and pausing the session.
 */

type Store = ReturnType<typeof inMemoryEventStore>;
type Behavior = (input: unknown) => Promise<ReconciliationOutcome>;

type Counters = { executes: number; reconciles: number };

function reconcilingTool(name: string, behavior: Behavior, counters: Counters): ToolDefinition {
  return {
    name,
    description: "unit-test fake write tool",
    effect: "reconcilable_write",
    inputSchema: z.object({ path: z.string() }),
    parametersJson: "{}",
    async execute(): Promise<ToolExecutionOutcome> {
      counters.executes += 1;
      return { status: "succeeded", resultJson: "{}" };
    },
    async reconcile(
      _context: ToolExecutionContext,
      input: unknown,
    ): Promise<ReconciliationOutcome> {
      counters.reconciles += 1;
      return behavior(input);
    },
  };
}

function bareTool(name: string): ToolDefinition {
  return {
    name,
    description: "unit-test fake tool without reconcile",
    effect: "read_only",
    inputSchema: z.object({ path: z.string() }),
    parametersJson: "{}",
    async execute(): Promise<ToolExecutionOutcome> {
      return { status: "succeeded", resultJson: "{}" };
    },
  };
}

function indeterminateStream(
  executions: ReadonlyArray<{ execution: number; name: string; argumentsJson: string }>,
  closed = false,
): SessionEventUnion[] {
  const events: SessionEventUnion[] = [sessionCreated(1), turnStarted(2, 1)];
  let seq = 2;
  for (const item of executions) {
    seq += 1;
    const proposed = toolProposed(seq, item.execution, {
      name: item.name,
      argumentsJson: item.argumentsJson,
      effect: "reconcilable_write",
    });
    seq += 1;
    const authorized = toolAuthorized(seq, item.execution);
    seq += 1;
    const started = toolStarted(seq, item.execution);
    seq += 1;
    const indeterminate = toolIndeterminate(seq, item.execution, "response lost");
    events.push(proposed, authorized, started, indeterminate);
  }
  if (closed) {
    seq += 1;
    events.push(turnCompleted(seq, 1));
  }
  return events;
}

function recoveryDeps(store: Store, tools: readonly ToolDefinition[]): RecoveryDeps {
  let counter = 500;
  return {
    store,
    sessionId: TEST_SESSION_ID,
    now: () => {
      counter += 1;
      return counter;
    },
    newEventId: () => asEventId(`recovery-unit-${counter}`),
    tools,
  };
}

async function seed(store: Store, events: SessionEventUnion[]) {
  await store.append(events, 0);
}

const SIGNAL = { signal: new AbortController().signal };

describe("reconcileIndeterminateExecutions", () => {
  test("settles an indeterminate execution via reconcile without re-executing", async () => {
    const store = inMemoryEventStore();
    const counters: Counters = { executes: 0, reconciles: 0 };
    await seed(
      store,
      indeterminateStream([
        { execution: 1, name: "write_file", argumentsJson: '{"path":"a.txt"}' },
      ]),
    );
    const deps = recoveryDeps(store, [
      reconcilingTool(
        "write_file",
        async () => ({ status: "succeeded", resultJson: '{"verified":true}' }),
        counters,
      ),
    ]);

    const report = await reconcileIndeterminateExecutions(deps, SIGNAL);

    expect(report.settled).toEqual([
      { toolExecutionId: asToolExecutionId("tool-exec-1"), outcome: "succeeded" },
    ]);
    expect(report.unresolved).toEqual([]);
    expect(counters).toEqual({ executes: 0, reconciles: 1 });

    const events = await store.readStream(TEST_SESSION_ID);
    const reconciled = events.find((event) => event.type === "ToolReconciled");
    expect(reconciled?.payload).toMatchObject({
      toolExecutionId: "tool-exec-1",
      outcome: "succeeded",
      resultJson: '{"verified":true}',
    });
    const state = foldSessionEvents(events);
    expect(state.toolExecutions.get(asToolExecutionId("tool-exec-1"))?.status).toBe("SUCCEEDED");
    expect(state.toolExecutions.get(asToolExecutionId("tool-exec-1"))?.reconciliationCount).toBe(1);
  });

  test("a provable absence settles as failed with the failure message", async () => {
    const store = inMemoryEventStore();
    const counters: Counters = { executes: 0, reconciles: 0 };
    await seed(
      store,
      indeterminateStream([
        { execution: 1, name: "write_file", argumentsJson: '{"path":"a.txt"}' },
      ]),
    );
    const deps = recoveryDeps(store, [
      reconcilingTool(
        "write_file",
        async () => ({ status: "failed", error: { message: "did not take effect" } }),
        counters,
      ),
    ]);

    const report = await reconcileIndeterminateExecutions(deps, SIGNAL);

    expect(report.settled).toEqual([
      { toolExecutionId: asToolExecutionId("tool-exec-1"), outcome: "failed" },
    ]);
    const state = foldSessionEvents(await store.readStream(TEST_SESSION_ID));
    const snapshot = state.toolExecutions.get(asToolExecutionId("tool-exec-1"));
    expect(snapshot?.status).toBe("FAILED");
    expect(snapshot?.failureMessage).toBe("did not take effect");
  });

  test("an unregistered tool stays unresolved with no settling fact", async () => {
    const store = inMemoryEventStore();
    await seed(
      store,
      indeterminateStream([
        { execution: 1, name: "ghost_tool", argumentsJson: '{"path":"a.txt"}' },
      ]),
    );
    const deps = recoveryDeps(store, []);

    const report = await reconcileIndeterminateExecutions(deps, SIGNAL);

    expect(report.settled).toEqual([]);
    expect(report.unresolved).toEqual([
      {
        toolExecutionId: asToolExecutionId("tool-exec-1"),
        reason: expect.stringContaining("not registered"),
      },
    ]);
    const events = await store.readStream(TEST_SESSION_ID);
    expect(events.some((event) => event.type === "ToolReconciled")).toBe(false);
    expect(
      foldSessionEvents(events).toolExecutions.get(asToolExecutionId("tool-exec-1"))?.status,
    ).toBe("INDETERMINATE");
  });

  test("a tool without reconcile stays unresolved", async () => {
    const store = inMemoryEventStore();
    await seed(
      store,
      indeterminateStream([{ execution: 1, name: "read_file", argumentsJson: '{"path":"a.txt"}' }]),
    );
    const deps = recoveryDeps(store, [bareTool("read_file")]);

    const report = await reconcileIndeterminateExecutions(deps, SIGNAL);

    expect(report.unresolved).toEqual([
      {
        toolExecutionId: asToolExecutionId("tool-exec-1"),
        reason: expect.stringContaining("defines no reconcile"),
      },
    ]);
  });

  test("unparseable recorded input leaves an honest indeterminate fact", async () => {
    const store = inMemoryEventStore();
    const counters: Counters = { executes: 0, reconciles: 0 };
    await seed(
      store,
      indeterminateStream([{ execution: 1, name: "write_file", argumentsJson: '{"path": ' }]),
    );
    const deps = recoveryDeps(store, [
      reconcilingTool(
        "write_file",
        async () => ({ status: "succeeded", resultJson: "{}" }),
        counters,
      ),
    ]);

    const report = await reconcileIndeterminateExecutions(deps, SIGNAL);

    expect(report.settled).toEqual([]);
    expect(report.unresolved).toEqual([
      {
        toolExecutionId: asToolExecutionId("tool-exec-1"),
        reason: expect.stringContaining("recorded input no longer parses"),
      },
    ]);
    expect(counters.reconciles).toBe(0);
    const events = await store.readStream(TEST_SESSION_ID);
    const reconciled = events.find((event) => event.type === "ToolReconciled");
    expect(reconciled?.payload).toMatchObject({
      outcome: "indeterminate",
      reason: expect.stringContaining("recorded input no longer parses"),
    });
  });

  test("a crashing reconcile leaves an honest indeterminate fact, never a guess", async () => {
    const store = inMemoryEventStore();
    await seed(
      store,
      indeterminateStream([
        { execution: 1, name: "write_file", argumentsJson: '{"path":"a.txt"}' },
      ]),
    );
    const deps = recoveryDeps(store, [
      reconcilingTool(
        "write_file",
        async () => {
          throw new Error("disk vanished");
        },
        { executes: 0, reconciles: 0 },
      ),
    ]);

    const report = await reconcileIndeterminateExecutions(deps, SIGNAL);

    expect(report.unresolved).toEqual([
      {
        toolExecutionId: asToolExecutionId("tool-exec-1"),
        reason: expect.stringContaining("reconcile attempt failed: disk vanished"),
      },
    ]);
    const events = await store.readStream(TEST_SESSION_ID);
    const reconciled = events.find((event) => event.type === "ToolReconciled");
    expect(reconciled?.payload).toMatchObject({
      outcome: "indeterminate",
      reason: "reconcile attempt failed: disk vanished",
    });
  });

  test("an inconclusive reconcile outcome is recorded and stays unresolved", async () => {
    const store = inMemoryEventStore();
    await seed(
      store,
      indeterminateStream([
        { execution: 1, name: "write_file", argumentsJson: '{"path":"a.txt"}' },
      ]),
    );
    const deps = recoveryDeps(store, [
      reconcilingTool(
        "write_file",
        async () => ({ status: "indeterminate", reason: "provider unreachable" }),
        { executes: 0, reconciles: 0 },
      ),
    ]);

    const report = await reconcileIndeterminateExecutions(deps, SIGNAL);

    expect(report.unresolved).toEqual([
      {
        toolExecutionId: asToolExecutionId("tool-exec-1"),
        reason: "provider unreachable",
      },
    ]);
    const events = await store.readStream(TEST_SESSION_ID);
    const reconciled = events.find((event) => event.type === "ToolReconciled");
    expect(reconciled?.payload).toMatchObject({
      outcome: "indeterminate",
      reason: "provider unreachable",
    });
  });

  test("multiple indeterminates are handled in insertion order", async () => {
    const store = inMemoryEventStore();
    await seed(
      store,
      indeterminateStream([
        { execution: 1, name: "ghost_tool", argumentsJson: '{"path":"a.txt"}' },
        { execution: 2, name: "write_file", argumentsJson: '{"path":"b.txt"}' },
      ]),
    );
    const deps = recoveryDeps(store, [
      reconcilingTool(
        "write_file",
        async () => ({ status: "succeeded", resultJson: '{"verified":true}' }),
        { executes: 0, reconciles: 0 },
      ),
    ]);

    const report = await reconcileIndeterminateExecutions(deps, SIGNAL);

    expect(report.settled).toEqual([
      { toolExecutionId: asToolExecutionId("tool-exec-2"), outcome: "succeeded" },
    ]);
    expect(report.unresolved.map((entry) => entry.toolExecutionId)).toEqual([
      asToolExecutionId("tool-exec-1"),
    ]);
  });

  test("a second pass settles nothing new", async () => {
    const store = inMemoryEventStore();
    await seed(
      store,
      indeterminateStream([
        { execution: 1, name: "write_file", argumentsJson: '{"path":"a.txt"}' },
      ]),
    );
    const deps = recoveryDeps(store, [
      reconcilingTool(
        "write_file",
        async () => ({ status: "succeeded", resultJson: '{"verified":true}' }),
        { executes: 0, reconciles: 0 },
      ),
    ]);
    await reconcileIndeterminateExecutions(deps, SIGNAL);

    const second = await reconcileIndeterminateExecutions(deps, SIGNAL);

    expect(second).toEqual({ settled: [], unresolved: [] });
  });
});

describe("pauseForUnresolvedIndeterminates", () => {
  test("closes the open turn and pauses the session", async () => {
    const store = inMemoryEventStore();
    await seed(
      store,
      indeterminateStream([
        { execution: 1, name: "write_file", argumentsJson: '{"path":"a.txt"}' },
      ]),
    );
    const deps = recoveryDeps(store, []);

    const state = await pauseForUnresolvedIndeterminates(deps, [
      { toolExecutionId: asToolExecutionId("tool-exec-1") },
    ]);

    expect(state.status).toBe("PAUSED");
    expect(state.currentTurnId).toBeUndefined();
    const events = await store.readStream(TEST_SESSION_ID);
    expect(events.at(-2)?.type).toBe("TurnCompleted");
    expect(events.at(-1)?.type).toBe("SessionPaused");
  });

  test("without an open turn it pauses without inventing turn closure", async () => {
    const store = inMemoryEventStore();
    await seed(
      store,
      indeterminateStream(
        [{ execution: 1, name: "write_file", argumentsJson: '{"path":"a.txt"}' }],
        true,
      ),
    );
    const deps = recoveryDeps(store, []);

    const state = await pauseForUnresolvedIndeterminates(deps, [
      { toolExecutionId: asToolExecutionId("tool-exec-1") },
    ]);

    expect(state.status).toBe("PAUSED");
    const events = await store.readStream(TEST_SESSION_ID);
    expect(events.filter((event) => event.type === "TurnCompleted")).toHaveLength(1);
    expect(events.at(-1)?.type).toBe("SessionPaused");
  });

  test("is a no-op when nothing is unresolved", async () => {
    const store = inMemoryEventStore();
    await seed(
      store,
      indeterminateStream([
        { execution: 1, name: "write_file", argumentsJson: '{"path":"a.txt"}' },
      ]),
    );
    const deps = recoveryDeps(store, []);
    const before = await store.readStream(TEST_SESSION_ID);

    const state = await pauseForUnresolvedIndeterminates(deps, []);

    expect(state.status).toBe("ACTIVE");
    expect(state.currentTurnId).toBeDefined();
    expect(await store.readStream(TEST_SESSION_ID)).toEqual(before);
  });
});
