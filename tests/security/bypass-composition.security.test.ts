import { mkdir, mkdtemp, readdir, rm, stat, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import type { ToolDefinition } from "@praxis/contracts";
import { asEventId, asSessionId, asToolExecutionId } from "@praxis/contracts";
import type { RecoveryDeps, ToolRuntimeDeps } from "@praxis/core";
import {
  capabilityAuthorizer,
  capabilityDecision,
  executeToolCall,
  projectSessionState,
  reconcileIndeterminateExecutions,
} from "@praxis/core";
import { bashTool, writeFileTool } from "@praxis/tools-local";
import { afterEach, beforeEach, describe, expect, test } from "vitest";
import { inMemoryEventStore } from "../helpers/in-memory-event-store";
import {
  sessionCreated,
  TEST_SESSION_ID,
  toolAuthorized,
  toolIndeterminate,
  toolProposed,
  toolStarted,
  turnStarted,
} from "../helpers/session-events";

/**
 * Composition-layer bypass attempts (M3 failure acceptance: "path/capability
 * bypass attempts rejected"; docs/02 section 9.3). The per-layer matrices live
 * in capability-policy and tools-local-write security suites; these tests
 * attack the seams between the capability gate, the tool path policy, and
 * the section 17 recovery orchestration in one stroke.
 */

const NOW = 10_000;
const workspace = (root: string) => ({ kind: "workspace" as const, root });
const signal = () => ({ signal: new AbortController().signal });

let root: string;
let outsideRoot: string;

beforeEach(async () => {
  root = await mkdtemp(join(tmpdir(), "praxis-bsec-"));
  outsideRoot = await mkdtemp(join(tmpdir(), "praxis-bout-"));
  await writeFile(join(outsideRoot, "secret.txt"), "outside secret");
  await mkdir(join(root, "sub"));
});
afterEach(async () => {
  await rm(root, { recursive: true, force: true });
  await rm(outsideRoot, { recursive: true, force: true });
});

function runtimeDeps(
  store: ReturnType<typeof inMemoryEventStore>,
  tools: readonly ToolDefinition[],
): ToolRuntimeDeps {
  let counter = 100;
  let executions = 0;
  return {
    store,
    sessionId: TEST_SESSION_ID,
    tools,
    now: () => {
      counter += 1;
      return counter;
    },
    newEventId: () => asEventId(`bypass-event-${counter}`),
    newToolExecutionId: () => {
      executions += 1;
      return asToolExecutionId(`tool-exec-${executions}`);
    },
  };
}

function recoveryDeps(
  store: ReturnType<typeof inMemoryEventStore>,
  tools: readonly ToolDefinition[],
): RecoveryDeps {
  let counter = 500;
  return {
    store,
    sessionId: TEST_SESSION_ID,
    now: () => {
      counter += 1;
      return counter;
    },
    newEventId: () => asEventId(`bypass-recovery-${counter}`),
    tools,
  };
}

async function openSession(store: ReturnType<typeof inMemoryEventStore>) {
  await store.append(
    [sessionCreated(1), turnStarted(2, 1)].map((event) => ({
      ...event,
      sessionId: TEST_SESSION_ID,
    })),
    0,
  );
}

async function seedIndeterminateWrite(
  store: ReturnType<typeof inMemoryEventStore>,
  argumentsJson: string,
): Promise<void> {
  await store.append(
    [
      sessionCreated(1),
      turnStarted(2, 1, "write then crash"),
      toolProposed(3, 1, {
        name: "write_file",
        argumentsJson,
        effect: "reconcilable_write",
      }),
      toolAuthorized(4, 1),
      toolStarted(5, 1),
      toolIndeterminate(6, 1, "crashed after the write was sent"),
    ].map((event) => ({ ...event, sessionId: TEST_SESSION_ID })),
    0,
  );
}

const grantingAuthorizer = () =>
  capabilityAuthorizer({
    policy: {
      workspaceRoots: [root],
      grants: [{ name: "fs.write", scope: workspace(root) }],
      leases: [],
      approvableCapabilities: [],
    },
    now: () => NOW,
  });

describe("capability + path policy composition under attack", () => {
  test("an escape path with the capability fully granted is still a provable non-effect", async () => {
    const store = inMemoryEventStore();
    await openSession(store);
    const deps = runtimeDeps(store, [writeFileTool(root)]);

    const summary = await executeToolCall(
      deps,
      {
        name: "write_file",
        argumentsJson: JSON.stringify({ path: "../../pwned.txt", content: "escaped" }),
      },
      { ...signal(), authorizer: grantingAuthorizer() },
    );

    // Layer 1 (capability) passed — the grant is genuine; layer 2 (path
    // policy) refused before any filesystem action, which is a provable
    // non-effect, not an unknown.
    expect(summary.status).toBe("FAILED");
    const state = await projectSessionState(deps);
    const snapshot = [...state.toolExecutions.values()][0];
    expect(snapshot?.status).toBe("FAILED");
    expect(snapshot?.failureMessage ?? "").toContain("escapes the workspace root");

    const events = await store.readStream(TEST_SESSION_ID);
    const types = events.map((event) => event.type);
    expect(types).toContain("ToolAuthorized");
    expect(types.indexOf("ToolFailed")).toBeGreaterThan(types.indexOf("ToolStarted"));

    await expect(stat(resolve(root, "../../pwned.txt"))).rejects.toMatchObject({
      code: "ENOENT",
    });
  });

  test("a symlink retargeted after the crash cannot turn reconciliation into a re-execution unlock", async () => {
    // The write landed inside the root through an in-root symlink; the
    // process crashed before the fact; the attacker retargets the symlink
    // outside. The old reconcile claimed provable absence (failed — the only
    // outcome that unlocks re-execution); it must instead admit it cannot
    // verify, which escalates to a human decision.
    await mkdir(join(root, "real"));
    await writeFile(join(root, "real", "b.txt"), "landed");
    await symlink(join(root, "real"), join(root, "link"));

    const store = inMemoryEventStore();
    await seedIndeterminateWrite(store, JSON.stringify({ path: "link/b.txt", content: "landed" }));
    await rm(join(root, "link"));
    await symlink(outsideRoot, join(root, "link"));

    const report = await reconcileIndeterminateExecutions(
      recoveryDeps(store, [writeFileTool(root)]),
      signal(),
    );

    expect(report.settled).toEqual([]);
    expect(report.unresolved).toHaveLength(1);
    const events = await store.readStream(TEST_SESSION_ID);
    const reconciled = events.find((event) => event.type === "ToolReconciled");
    expect(reconciled?.payload).toMatchObject({ outcome: "indeterminate" });
    // Nothing was read or written outside through the retargeted link.
    expect(await readdir(outsideRoot)).toEqual(["secret.txt"]);
  });

  test("a forged INDETERMINATE execution with an escaping recorded input settles nothing", async () => {
    const store = inMemoryEventStore();
    await seedIndeterminateWrite(
      store,
      JSON.stringify({ path: "../../../etc/cron.d/praxis-pwn", content: "0 * * * * curl evil" }),
    );

    const report = await reconcileIndeterminateExecutions(
      recoveryDeps(store, [writeFileTool(root)]),
      signal(),
    );

    expect(report.settled).toEqual([]);
    expect(report.unresolved).toHaveLength(1);
    const events = await store.readStream(TEST_SESSION_ID);
    const reconciled = events.find((event) => event.type === "ToolReconciled");
    expect(reconciled?.payload).toMatchObject({ outcome: "indeterminate" });
    expect(
      events.some(
        (event) => event.type === "ToolReconciled" && event.payload.outcome !== "indeterminate",
      ),
    ).toBe(false);
  });

  test("symlink-aliased roots never satisfy the lexical capability scope", async () => {
    // Two names for one physical directory are still two scopes: the policy
    // is lexical by design (never resolves), so an aliased grant cannot
    // cover a differently-named root, and mismatches fail closed.
    const realDir = await mkdtemp(join(tmpdir(), "praxis-scope-real-"));
    const aliasDir = await mkdtemp(join(tmpdir(), "praxis-scope-alias-"));
    await rm(aliasDir, { recursive: true });
    await symlink(realDir, aliasDir);

    const decision = capabilityDecision(
      { name: "fs.write", scope: workspace(aliasDir) },
      {
        workspaceRoots: [realDir, aliasDir],
        grants: [{ name: "fs.write", scope: workspace(realDir) }],
        leases: [],
        approvableCapabilities: [],
      },
      NOW,
    );

    expect(decision.type).toBe("deny");
    await rm(realDir, { recursive: true, force: true });
  });

  test("bash without its capability is rejected before ToolStarted despite other write grants", async () => {
    const store = inMemoryEventStore();
    await openSession(store);
    const deps = runtimeDeps(store, [bashTool(root), writeFileTool(root)]);

    const summary = await executeToolCall(
      deps,
      { name: "bash", argumentsJson: JSON.stringify({ command: "touch pwned.txt && echo ok" }) },
      { ...signal(), authorizer: grantingAuthorizer() },
    );

    expect(summary.status).toBe("REJECTED");
    const events = await store.readStream(TEST_SESSION_ID);
    expect(events.map((event) => event.type)).not.toContain("ToolStarted");
    await expect(stat(join(root, "pwned.txt"))).rejects.toMatchObject({ code: "ENOENT" });
  });
});
