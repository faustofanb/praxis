import type {
  ToolDefinition,
  ToolEffect,
  ToolExecutionContext,
  ToolExecutionOutcome,
} from "@praxis/contracts";
import { asEventId, asToolExecutionId } from "@praxis/contracts";
import type { ToolAuthorizer, ToolRuntimeDeps } from "@praxis/core";
import { executeToolCall, projectSessionState } from "@praxis/core";
import { describe, expect, test } from "vitest";
import { z } from "zod";
import { inMemoryEventStore } from "../helpers/in-memory-event-store";
import { sessionCreated, turnStarted } from "../helpers/session-events";

const TEST_SESSION_ID = sessionCreated(1).sessionId;

type MemoryStore = ReturnType<typeof inMemoryEventStore>;

function deterministicDeps(store: MemoryStore): ToolRuntimeDeps {
  let counter = 100;
  let executions = 0;
  return {
    store,
    sessionId: TEST_SESSION_ID,
    tools: [],
    now: () => {
      counter += 1;
      return counter;
    },
    newEventId: () => asEventId(`event-${counter}`),
    newToolExecutionId: () => {
      executions += 1;
      return asToolExecutionId(`tool-exec-${executions}`);
    },
  };
}

async function openTurn(store: MemoryStore): Promise<void> {
  await store.append([sessionCreated(1), turnStarted(2, 1)], 0);
}

function fakeTool(options: {
  name: string;
  effect?: ToolEffect;
  behavior: (signal: AbortSignal) => ToolExecutionOutcome | Promise<ToolExecutionOutcome>;
}): ToolDefinition {
  return {
    name: options.name,
    description: "fault-injection fake",
    effect: options.effect ?? "read_only",
    inputSchema: z.object({}),
    parametersJson: '{"type":"object"}',
    async execute(context: ToolExecutionContext, _input: unknown): Promise<ToolExecutionOutcome> {
      return options.behavior(context.signal);
    },
  };
}

const allowEverything: ToolAuthorizer = () => ({ decision: "authorized" });

function firstSnapshot(deps: ToolRuntimeDeps) {
  return projectSessionState(deps).then((state) => [...state.toolExecutions.values()][0]);
}

describe("tool runtime fault paths", () => {
  test("a store crash after ToolStarted leaves the true EXECUTING state recoverable", async () => {
    const real = inMemoryEventStore();
    await openTurn(real);
    let appends = 0;
    const crashing: MemoryStore = {
      async readStream(sessionId, afterSeq) {
        return real.readStream(sessionId, afterSeq);
      },
      async append(events, expectedHeadSeq) {
        appends += 1;
        if (appends >= 4) {
          throw new Error("simulated crash before terminal append");
        }
        return real.append(events, expectedHeadSeq);
      },
    };
    const deps = { ...deterministicDeps(real), store: real };
    const tool = fakeTool({
      name: "flaky_read",
      behavior: () => ({ status: "succeeded", resultJson: '{"content":"x"}' }),
    });

    await expect(
      executeToolCall(
        { ...deps, store: crashing, tools: [tool] },
        { name: "flaky_read", argumentsJson: "{}" },
        { signal: new AbortController().signal },
      ),
    ).rejects.toThrow(/simulated crash/u);

    const state = await projectSessionState(deps);
    expect([...state.toolExecutions.values()][0]?.status).toBe("EXECUTING");
    expect(state.headSeq).toBe(5);
  });

  test("a crashing read-only executor records FAILED, not a fabricated success", async () => {
    const store = inMemoryEventStore();
    await openTurn(store);
    const deps = deterministicDeps(store);
    const tool = fakeTool({
      name: "crashing_read",
      behavior: () => {
        throw new Error("kaboom");
      },
    });

    const summary = await executeToolCall(
      { ...deps, tools: [tool] },
      { name: "crashing_read", argumentsJson: "{}" },
      { signal: new AbortController().signal },
    );

    expect(summary.status).toBe("FAILED");
    const snapshot = await firstSnapshot(deps);
    expect(snapshot?.status).toBe("FAILED");
    expect(snapshot?.failureMessage).toContain("kaboom");
  });

  test("a crashing write-capable tool stays INDETERMINATE, never coerced to FAILED", async () => {
    const store = inMemoryEventStore();
    await openTurn(store);
    const deps = deterministicDeps(store);
    const tool = fakeTool({
      name: "dangerous_write",
      effect: "non_idempotent_write",
      behavior: () => {
        throw new Error("died mid-request");
      },
    });

    const summary = await executeToolCall(
      { ...deps, tools: [tool] },
      { name: "dangerous_write", argumentsJson: "{}" },
      { signal: new AbortController().signal, authorizer: allowEverything },
    );

    expect(summary.status).toBe("INDETERMINATE");
    const snapshot = await firstSnapshot(deps);
    expect(snapshot?.status).toBe("INDETERMINATE");
    expect(snapshot?.indeterminateReason).toContain("died mid-request");
  });

  test("an unknown external outcome surfaces as a first-class INDETERMINATE fact", async () => {
    const store = inMemoryEventStore();
    await openTurn(store);
    const deps = deterministicDeps(store);
    const tool = fakeTool({
      name: "remote_ping",
      effect: "non_idempotent_write",
      behavior: () => ({ status: "indeterminate", reason: "connection lost" }),
    });

    const summary = await executeToolCall(
      { ...deps, tools: [tool] },
      { name: "remote_ping", argumentsJson: "{}" },
      { signal: new AbortController().signal, authorizer: allowEverything },
    );

    expect(summary.status).toBe("INDETERMINATE");
    const snapshot = await firstSnapshot(deps);
    expect(snapshot?.status).toBe("INDETERMINATE");
    expect(snapshot?.indeterminateReason).toBe("connection lost");
  });
});
