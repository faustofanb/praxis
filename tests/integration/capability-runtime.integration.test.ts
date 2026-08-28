import type { ToolDefinition } from "@praxis/contracts";
import { asCapabilityLeaseId, asEventId, asSessionId, asToolExecutionId } from "@praxis/contracts";
import type { ToolAuthorizer, ToolRuntimeDeps } from "@praxis/core";
import { capabilityAuthorizer, executeToolCall, projectSessionState } from "@praxis/core";
import { describe, expect, test } from "vitest";
import { z } from "zod";
import { inMemoryEventStore } from "../helpers/in-memory-event-store";
import { sessionCreated, turnStarted } from "../helpers/session-events";

const SESSION_ID = asSessionId("session-capability");
const NOW = 10_000;
const workspace = (root: string) => ({ kind: "workspace" as const, root });

/**
 * End-to-end capability gating through the real tool runtime (docs/02
 * section 9.3 layer 1): the authorizer decides before ToolStarted, every
 * decision lands as a durable fact, and headSeq moves exactly as far as the
 * decision warrants — nothing executes past a closed gate.
 */

function makeDeps(store: ReturnType<typeof inMemoryEventStore>): ToolRuntimeDeps {
  let counter = 100;
  let executions = 0;
  return {
    store,
    sessionId: SESSION_ID,
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

const writeTool: ToolDefinition = {
  name: "write_file",
  description: "integration write tool",
  effect: "idempotent_write",
  inputSchema: z.object({}),
  parametersJson: '{"type":"object"}',
  requiredCapability: { name: "fs.write", scope: workspace("/w") },
  async execute() {
    return { status: "succeeded", resultJson: '{"bytes":4}' };
  },
};

async function openSession(): Promise<ReturnType<typeof inMemoryEventStore>> {
  const store = inMemoryEventStore();
  await store.append(
    [sessionCreated(1), turnStarted(2, 1)].map((event) => ({
      ...event,
      sessionId: SESSION_ID,
    })),
    0,
  );
  return store;
}

describe("capability-gated tool calls through the runtime", () => {
  test("a granted capability authorizes, executes, and lands SUCCEEDED", async () => {
    const store = await openSession();
    const deps = { ...makeDeps(store), tools: [writeTool] };
    const authorizer: ToolAuthorizer = capabilityAuthorizer({
      policy: {
        workspaceRoots: ["/w"],
        grants: [{ name: "fs.write", scope: workspace("/w") }],
        leases: [],
        approvableCapabilities: [],
      },
      now: () => NOW,
    });

    const summary = await executeToolCall(
      deps,
      { name: "write_file", argumentsJson: "{}" },
      { signal: new AbortController().signal, authorizer },
    );

    expect(summary.status).toBe("SUCCEEDED");
    const state = await projectSessionState(deps);
    const snapshot = [...state.toolExecutions.values()][0];
    expect(snapshot?.status).toBe("SUCCEEDED");
    expect(snapshot?.effect).toBe("idempotent_write");
    expect(snapshot?.resultJson).toContain("bytes");
  });

  test("a leased capability authorizes only while the lease lives; expiry rejects", async () => {
    const lease = {
      id: asCapabilityLeaseId("lease-integration"),
      capability: "fs.write",
      scope: workspace("/w"),
      issuedAt: 0,
      expiresAt: NOW + 1,
      reason: "integration lease",
    };
    const authorizer = capabilityAuthorizer({
      policy: { workspaceRoots: ["/w"], grants: [], leases: [lease], approvableCapabilities: [] },
      now: () => NOW,
    });

    const liveStore = await openSession();
    const liveDeps = { ...makeDeps(liveStore), tools: [writeTool] };
    const liveSummary = await executeToolCall(
      liveDeps,
      { name: "write_file", argumentsJson: "{}" },
      { signal: new AbortController().signal, authorizer },
    );
    expect(liveSummary.status).toBe("SUCCEEDED");

    // Same policy, one tick later: the lease is expired and the gate closes.
    const expiredAuthorizer = capabilityAuthorizer({
      policy: { workspaceRoots: ["/w"], grants: [], leases: [lease], approvableCapabilities: [] },
      now: () => NOW + 1,
    });
    const deadStore = await openSession();
    const deadDeps = { ...makeDeps(deadStore), tools: [writeTool] };
    const deadSummary = await executeToolCall(
      deadDeps,
      { name: "write_file", argumentsJson: "{}" },
      { signal: new AbortController().signal, authorizer: expiredAuthorizer },
    );
    expect(deadSummary.status).toBe("REJECTED");
    const deadState = await projectSessionState(deadDeps);
    const deadSnapshot = [...deadState.toolExecutions.values()][0];
    expect(deadSnapshot?.status).toBe("REJECTED");
    expect(deadSnapshot?.rejectionReason).toContain("expired");
    // Proposed + rejected: no ToolStarted, no terminal — headSeq stops at 4.
    expect(deadState.headSeq).toBe(4);
  });

  test("requires_approval rejects fail-closed and records why in the stream", async () => {
    const store = await openSession();
    const deps = { ...makeDeps(store), tools: [writeTool] };
    const authorizer = capabilityAuthorizer({
      policy: {
        workspaceRoots: ["/w"],
        grants: [],
        leases: [],
        approvableCapabilities: ["fs.write"],
      },
      now: () => NOW,
    });

    const summary = await executeToolCall(
      deps,
      { name: "write_file", argumentsJson: "{}" },
      { signal: new AbortController().signal, authorizer },
    );

    expect(summary.status).toBe("REJECTED");
    const state = await projectSessionState(deps);
    const snapshot = [...state.toolExecutions.values()][0];
    expect(snapshot?.status).toBe("REJECTED");
    expect(snapshot?.rejectionReason).toContain("requires human approval");
    expect(snapshot?.rejectionReason).toContain("fail closed");
    const events = await store.readStream(SESSION_ID, 0);
    const types = events.map((event) => event.type);
    expect(types).toContain("ToolRejected");
    const rejection = events.find((event) => event.type === "ToolRejected");
    if (rejection?.type === "ToolRejected") {
      expect(rejection.payload.reason).toContain("requires human approval");
    }
  });

  test("a scope-escaping capability request is denied before any tool starts", async () => {
    const escapingTool: ToolDefinition = {
      name: "write_outside",
      description: "integration escape tool",
      effect: "idempotent_write",
      inputSchema: z.object({}),
      parametersJson: '{"type":"object"}',
      requiredCapability: { name: "fs.write", scope: workspace("/etc") },
      async execute() {
        return { status: "succeeded", resultJson: '"escaped"' };
      },
    };
    const store = await openSession();
    const deps = { ...makeDeps(store), tools: [escapingTool] };
    const authorizer = capabilityAuthorizer({
      policy: {
        workspaceRoots: ["/w"],
        grants: [{ name: "fs.write" }],
        leases: [],
        approvableCapabilities: [],
      },
      now: () => NOW,
    });

    const summary = await executeToolCall(
      deps,
      { name: "write_outside", argumentsJson: "{}" },
      { signal: new AbortController().signal, authorizer },
    );

    // Even a global grant cannot carry a request outside the workspace.
    expect(summary.status).toBe("REJECTED");
    const state = await projectSessionState(deps);
    const snapshot = [...state.toolExecutions.values()][0];
    expect(snapshot?.status).toBe("REJECTED");
    expect(snapshot?.rejectionReason).toContain("escapes the configured workspace");
    const events = await store.readStream(SESSION_ID, 0);
    expect(events.map((event) => event.type)).not.toContain("ToolStarted");
  });
});
