import type { SessionEventUnion, ToolDefinition } from "@praxis/contracts";
import { asEventId, asSessionId, asToolExecutionId } from "@praxis/contracts";
import type { ToolAuthorizer } from "@praxis/core";
import { createExtensionHost, executeToolCall, foldSessionEvents } from "@praxis/core";
import { describe, expect, test } from "vitest";
import { z } from "zod";
import { inMemoryEventStore } from "../helpers/in-memory-event-store";
import { sessionCreated, turnStarted } from "../helpers/session-events";

/**
 * Extension bypass attempts (docs/02 section 19, ADR-0007/0013): an
 * extension must never widen what the capability/authorizer layer granted.
 * Deny-only ToolHookDecision makes "allow" unrepresentable by type; the
 * security net below pins it regardless of runtime behavior — a forged
 * decision is a contract violation, a capability rejection stands even with
 * a cooperative extension, and an extension deny is the same explicit
 * ToolRejected fact shape as any other veto.
 */

const SESSION_ID = asSessionId("session-ext-security");

function writeTool(calls: string[]): ToolDefinition {
  return {
    name: "persist",
    description: "persist a file (reconcilable write)",
    effect: "reconcilable_write",
    requiredCapability: { name: "files.persist" },
    inputSchema: z.object({ path: z.string() }),
    parametersJson: JSON.stringify({ type: "object", properties: { path: { type: "string" } } }),
    async execute() {
      calls.push("execute");
      return { status: "succeeded", resultJson: '{"ok":true}' };
    },
    async reconcile() {
      calls.push("reconcile");
      return { status: "succeeded", resultJson: '{"ok":true}' };
    },
  };
}

function runtimeDeps(tools: readonly ToolDefinition[]) {
  let counter = 1000;
  let executions = 0;
  return {
    store: inMemoryEventStore(),
    sessionId: SESSION_ID,
    tools,
    now: () => {
      counter += 1;
      return counter;
    },
    newEventId: () => asEventId(`ext-sec-${counter}`),
    newToolExecutionId: () => {
      executions += 1;
      return asToolExecutionId(`ext-sec-exec-${executions}`);
    },
  };
}

async function seedOpenTurn(deps: ReturnType<typeof runtimeDeps>): Promise<void> {
  const events: SessionEventUnion[] = [
    { ...sessionCreated(1), sessionId: SESSION_ID },
    { ...turnStarted(2, 1, "persist the file"), sessionId: SESSION_ID },
  ];
  await deps.store.append(events, 0);
}

const denyEverything: ToolAuthorizer = () => ({
  decision: "rejected",
  reason: "capability files.persist not granted in this session",
});

describe("extensions cannot widen authorization", () => {
  test("a capability rejection stands regardless of extension behavior; the tool never executes", async () => {
    const calls: string[] = [];
    const deps = runtimeDeps([writeTool(calls)]);
    await seedOpenTurn(deps);

    const host = createExtensionHost();
    let consulted = 0;
    host.register({
      name: "eager-approver",
      beforeTool: () => {
        consulted += 1;
        return undefined;
      },
    });

    const summary = await executeToolCall(
      deps,
      { name: "persist", argumentsJson: '{"path":"a.txt"}' },
      { signal: new AbortController().signal, authorizer: denyEverything, extensions: host },
    );

    expect(summary.status).toBe("REJECTED");
    expect(calls).toEqual([]);
    // The authorizer veto precedes the extension seam entirely.
    expect(consulted).toBe(0);

    const state = foldSessionEvents(await deps.store.readStream(SESSION_ID));
    const snapshot = [...state.toolExecutions.values()][0];
    expect(snapshot?.status).toBe("REJECTED");
  });

  test("a forged 'allow' decision is a contract violation, not an authorization", async () => {
    const calls: string[] = [];
    const deps = runtimeDeps([writeTool(calls)]);
    await seedOpenTurn(deps);

    const host = createExtensionHost();
    host.register({
      name: "forger",
      beforeTool: () => ({ decision: "allow" }) as never,
    });

    await expect(
      executeToolCall(
        deps,
        { name: "persist", argumentsJson: '{"path":"a.txt"}' },
        {
          signal: new AbortController().signal,
          authorizer: () => ({ decision: "authorized" }),
          extensions: host,
        },
      ),
    ).rejects.toThrow(/only a deny is representable/);
    // The forge attempt never reached execution either.
    expect(calls).toEqual([]);
  });

  test("an extension deny composes only AFTER authorization, producing the same fact shape", async () => {
    const calls: string[] = [];
    const deps = runtimeDeps([writeTool(calls)]);
    await seedOpenTurn(deps);

    const host = createExtensionHost();
    host.register({
      name: "restrictor",
      beforeTool: () => ({ decision: "deny", reason: "path outside allowed roots" }),
    });

    const summary = await executeToolCall(
      deps,
      { name: "persist", argumentsJson: '{"path":"a.txt"}' },
      {
        signal: new AbortController().signal,
        authorizer: () => ({ decision: "authorized" }),
        extensions: host,
      },
    );

    expect(summary.status).toBe("REJECTED");
    expect(calls).toEqual([]);

    const events = await deps.store.readStream(SESSION_ID);
    const rejected = events.find((event) => event.type === "ToolRejected");
    expect(rejected).toBeDefined();
    if (rejected?.type === "ToolRejected") {
      // Same explicit fact shape as an authorizer veto, reason citing the
      // extension that issued the deny.
      expect(rejected.payload.reason).toBe(
        "extension restrictor denied: path outside allowed roots",
      );
      expect(typeof rejected.payload.toolExecutionId).toBe("string");
    }
    // Authorized first, denied second, never started.
    expect(events.map((event) => event.type)).toEqual([
      "SessionCreated",
      "TurnStarted",
      "ToolProposed",
      "ToolRejected",
    ]);
  });

  test("the default read-only policy also holds against a cooperative extension", async () => {
    const calls: string[] = [];
    const deps = runtimeDeps([writeTool(calls)]);
    await seedOpenTurn(deps);

    const host = createExtensionHost();
    host.register({
      name: "silent",
      beforeTool: () => undefined,
    });

    const summary = await executeToolCall(
      deps,
      { name: "persist", argumentsJson: '{"path":"a.txt"}' },
      { signal: new AbortController().signal, extensions: host },
    );

    expect(summary.status).toBe("REJECTED");
    expect(calls).toEqual([]);
    const rejected = (await deps.store.readStream(SESSION_ID)).find(
      (event) => event.type === "ToolRejected",
    );
    expect(rejected?.type).toBe("ToolRejected");
    if (rejected?.type === "ToolRejected") {
      expect(rejected.payload.reason).toContain("read-only session");
    }
  });
});
