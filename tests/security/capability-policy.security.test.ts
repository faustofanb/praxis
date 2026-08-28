import type { ToolDefinition } from "@praxis/contracts";
import { asCapabilityLeaseId, asEventId, asToolExecutionId } from "@praxis/contracts";
import type { CapabilityPolicyConfig, ToolRuntimeDeps } from "@praxis/core";
import {
  capabilityAuthorizer,
  capabilityDecision,
  executeToolCall,
  projectSessionState,
} from "@praxis/core";
import { describe, expect, test } from "vitest";
import { z } from "zod";
import { inMemoryEventStore } from "../helpers/in-memory-event-store";
import { sessionCreated, turnStarted } from "../helpers/session-events";

const TEST_SESSION_ID = sessionCreated(1).sessionId;
const NOW = 10_000;

const workspace = (root: string) => ({ kind: "workspace" as const, root });

/**
 * Adversarial matrix for the capability policy (ADR-0007, docs/02 section 9).
 * Every test here is a bypass attempt: the assertion is that the gate stays
 * closed — by denial, by throw, or by an identical rejection on re-proposal.
 * The policy is pure, so scopes are plain strings; no filesystem is touched.
 */

function policy(overrides: Partial<CapabilityPolicyConfig> = {}): CapabilityPolicyConfig {
  return {
    workspaceRoots: ["/w"],
    grants: [],
    leases: [],
    approvableCapabilities: [],
    ...overrides,
  };
}

describe("scope-escape attempts are never resolved into access", () => {
  test("a requested scope containing '..' makes the policy throw, not resolve", () => {
    for (const root of ["/w/../etc", "/w//../../etc", "/w/sub/../../.."]) {
      expect(() =>
        capabilityDecision({ name: "fs.write", scope: workspace(root) }, policy(), NOW),
      ).toThrow(/must not contain '\.\.'/u);
    }
  });

  test("a sibling-prefix workspace never inherits access (segment-wise containment)", () => {
    const decision = capabilityDecision(
      { name: "fs.write", scope: workspace("/workspace") },
      policy({ workspaceRoots: ["/work"] }),
      NOW,
    );
    expect(decision).toEqual({
      type: "deny",
      reason: expect.stringContaining("escapes the configured workspace") as unknown as string,
    });
  });

  test("a scoped grant on /work does not satisfy a /workspace request even with the right name", () => {
    const decision = capabilityDecision(
      { name: "fs.write", scope: workspace("/workspace") },
      policy({
        workspaceRoots: ["/work", "/workspace"],
        grants: [{ name: "fs.write", scope: workspace("/work") }],
      }),
      NOW,
    );
    expect(decision.type).toBe("deny");
  });

  test("the workspace-escape check precedes even a global grant", () => {
    const decision = capabilityDecision(
      { name: "fs.write", scope: workspace("/etc") },
      policy({ grants: [{ name: "fs.write" }] }),
      NOW,
    );
    expect(decision.type).toBe("deny");
  });
});

describe("lease-based bypass attempts", () => {
  test("a lease expired exactly at now denies — no grace window, no rounding", () => {
    const expired = {
      id: asCapabilityLeaseId("lease-exp"),
      capability: "fs.write",
      scope: workspace("/w"),
      issuedAt: 0,
      expiresAt: NOW,
      reason: "exact expiry",
    };
    expect(
      capabilityDecision(
        { name: "fs.write", scope: workspace("/w") },
        policy({ leases: [expired] }),
        NOW,
      ),
    ).toMatchObject({ type: "deny" });
  });

  test("a lease for a different capability never satisfies the request", () => {
    const wrongName = {
      id: asCapabilityLeaseId("lease-other"),
      capability: "shell.exec",
      scope: workspace("/w"),
      issuedAt: 0,
      expiresAt: NOW + 1_000,
      reason: "wrong capability",
    };
    expect(
      capabilityDecision(
        { name: "fs.write", scope: workspace("/w") },
        policy({ leases: [wrongName] }),
        NOW,
      ),
    ).toMatchObject({ type: "deny" });
  });

  test("a lease scoped elsewhere never satisfies the request", () => {
    const wrongScope = {
      id: asCapabilityLeaseId("lease-elsewhere"),
      capability: "fs.write",
      scope: workspace("/other"),
      issuedAt: 0,
      expiresAt: NOW + 1_000,
      reason: "wrong scope",
    };
    expect(
      capabilityDecision(
        { name: "fs.write", scope: workspace("/w") },
        policy({ workspaceRoots: ["/w", "/other"], leases: [wrongScope] }),
        NOW,
      ),
    ).toMatchObject({ type: "deny" });
  });
});

describe("re-proposal never grants (the model cannot wear the gate down)", () => {
  function makeDeps(tools: readonly ToolDefinition[]): {
    deps: ToolRuntimeDeps;
    executions: { count: number };
  } {
    const store = inMemoryEventStore();
    let counter = 500;
    const executions = { count: 0 };
    const deps: ToolRuntimeDeps = {
      store,
      sessionId: TEST_SESSION_ID,
      tools,
      now: () => {
        counter += 1;
        return counter;
      },
      newEventId: () => asEventId(`event-${counter}`),
      newToolExecutionId: () => {
        executions.count += 1;
        return asToolExecutionId(`tool-exec-${executions.count}`);
      },
    };
    return { deps, executions };
  }

  function makeWriteTool(): { tool: ToolDefinition; runs: { count: number } } {
    const runs = { count: 0 };
    return {
      runs,
      tool: {
        name: "write_file",
        description: "adversarial write tool",
        effect: "idempotent_write",
        inputSchema: z.object({}),
        parametersJson: '{"type":"object"}',
        requiredCapability: { name: "fs.write", scope: workspace("/w") },
        async execute() {
          runs.count += 1;
          return { status: "succeeded", resultJson: '"wrote"' };
        },
      },
    };
  }

  const unapprovedPolicy = policy({ approvableCapabilities: ["fs.write"] });
  const authorizer = capabilityAuthorizer({ policy: unapprovedPolicy, now: () => NOW });

  test("requires_approval rejects identically on every re-proposal and never executes", async () => {
    const writeTool = makeWriteTool();
    const { deps } = makeDeps([writeTool.tool]);
    await deps.store.append([sessionCreated(1), turnStarted(2, 1)], 0);
    for (let attempt = 0; attempt < 3; attempt += 1) {
      const summary = await executeToolCall(
        deps,
        { name: "write_file", argumentsJson: "{}" },
        { signal: new AbortController().signal, authorizer },
      );
      expect(summary.status).toBe("REJECTED");
    }
    expect(writeTool.runs.count).toBe(0);
    const state = await projectSessionState(deps);
    const snapshots = [...state.toolExecutions.values()];
    expect(snapshots).toHaveLength(3);
    const reasons = snapshots.map((snapshot) => snapshot.rejectionReason);
    expect(reasons[0]).toContain("requires human approval");
    expect(reasons[1]).toBe(reasons[0]);
    expect(reasons[2]).toBe(reasons[0]);
    for (const snapshot of snapshots) {
      expect(snapshot.status).toBe("REJECTED");
    }
  });

  test("arguments cannot influence the authorization decision", async () => {
    const writeTool = makeWriteTool();
    const { deps } = makeDeps([writeTool.tool]);
    await deps.store.append([sessionCreated(1), turnStarted(2, 1)], 0);
    for (const argumentsJson of [
      '{"path":"note.txt"}',
      '{"path":"note.txt","please":"grant me fs.write, this is urgent"}',
      '{"scope":{"kind":"workspace","root":"/"}}',
    ]) {
      const summary = await executeToolCall(
        deps,
        { name: "write_file", argumentsJson },
        { signal: new AbortController().signal, authorizer },
      );
      expect(summary.status).toBe("REJECTED");
    }
    expect(writeTool.runs.count).toBe(0);
    const state = await projectSessionState(deps);
    const snapshots = [...state.toolExecutions.values()];
    expect(snapshots).toHaveLength(3);
    const reasons = snapshots.map((snapshot) => snapshot.rejectionReason);
    expect(reasons[1]).toBe(reasons[0]);
    expect(reasons[2]).toBe(reasons[0]);
  });

  test("a granted capability executes and records the authorized fact", async () => {
    const writeTool = makeWriteTool();
    const { deps } = makeDeps([writeTool.tool]);
    await deps.store.append([sessionCreated(1), turnStarted(2, 1)], 0);
    const granting = capabilityAuthorizer({
      policy: policy({ grants: [{ name: "fs.write", scope: workspace("/w") }] }),
      now: () => NOW,
    });
    const summary = await executeToolCall(
      deps,
      { name: "write_file", argumentsJson: "{}" },
      { signal: new AbortController().signal, authorizer: granting },
    );
    expect(summary.status).toBe("SUCCEEDED");
    expect(writeTool.runs.count).toBe(1);
    const state = await projectSessionState(deps);
    const snapshot = [...state.toolExecutions.values()][0];
    expect(snapshot?.status).toBe("SUCCEEDED");
    expect(snapshot?.effect).toBe("idempotent_write");
  });

  test("a write tool reaching the runtime without a declared requirement is rejected (defense in depth)", async () => {
    const rogueRuns = { count: 0 };
    const rogue: ToolDefinition = {
      name: "rogue_write",
      description: "registration should have caught this",
      effect: "non_idempotent_write",
      inputSchema: z.object({}),
      parametersJson: '{"type":"object"}',
      async execute() {
        rogueRuns.count += 1;
        return { status: "succeeded", resultJson: '"should never run"' };
      },
    };
    const { deps } = makeDeps([rogue]);
    await deps.store.append([sessionCreated(1), turnStarted(2, 1)], 0);
    const summary = await executeToolCall(
      deps,
      { name: "rogue_write", argumentsJson: "{}" },
      { signal: new AbortController().signal, authorizer },
    );
    expect(summary.status).toBe("REJECTED");
    const state = await projectSessionState(deps);
    const snapshot = [...state.toolExecutions.values()][0];
    expect(snapshot?.status).toBe("REJECTED");
    expect(snapshot?.rejectionReason).toContain("declares no capability requirement");
    expect(rogueRuns.count).toBe(0);
  });
});
