import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { ToolDefinition } from "@praxis/contracts";
import { asEventId, asSessionId, asToolExecutionId } from "@praxis/contracts";
import type { ToolRuntimeDeps } from "@praxis/core";
import { capabilityAuthorizer, executeToolCall, projectSessionState } from "@praxis/core";
import { bashTool, writeFileTool } from "@praxis/tools-local";
import { afterEach, beforeEach, describe, expect, test } from "vitest";
import { inMemoryEventStore } from "../helpers/in-memory-event-store";
import {
  sessionCreated,
  toolAuthorized,
  toolIndeterminate,
  toolProposed,
  toolReconciled,
  toolStarted,
  turnStarted,
} from "../helpers/session-events";

const SESSION_ID = asSessionId("session-write-tools");
const NOW = 10_000;

let root: string;

beforeEach(async () => {
  root = await mkdtemp(join(tmpdir(), "praxis-wint-"));
});
afterEach(async () => {
  await rm(root, { recursive: true, force: true });
});

function makeDeps(tools: readonly ToolDefinition[]): ToolRuntimeDeps {
  const store = inMemoryEventStore();
  let counter = 100;
  let executions = 0;
  return {
    store,
    sessionId: SESSION_ID,
    tools,
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

const granting = (names: readonly string[]) =>
  capabilityAuthorizer({
    policy: {
      workspaceRoots: [root],
      grants: names.map((name) => ({ name, scope: { kind: "workspace" as const, root } })),
      leases: [],
      approvableCapabilities: [],
    },
    now: () => NOW,
  });

/**
 * M3 milestone scenarios through the real runtime: authorized writes land
 * as durable facts, unauthorized ones never start, and the crash-after-
 * side-effect path flows indeterminate -> reconcile -> settled fact
 * (M3.yaml failure acceptance) against a real filesystem.
 */
describe("write tools through the capability-gated runtime", () => {
  test("an authorized write_file executes and lands SUCCEEDED", async () => {
    const deps = makeDeps([writeFileTool(root)]);
    await deps.store.append(
      [sessionCreated(1), turnStarted(2, 1)].map((event) => ({
        ...event,
        sessionId: SESSION_ID,
      })),
      0,
    );
    const summary = await executeToolCall(
      deps,
      { name: "write_file", argumentsJson: JSON.stringify({ path: "a.txt", content: "data" }) },
      { signal: new AbortController().signal, authorizer: granting(["fs.write"]) },
    );
    expect(summary.status).toBe("SUCCEEDED");
    expect(await readFile(join(root, "a.txt"), "utf8")).toBe("data");
    const state = await projectSessionState(deps);
    const snapshot = [...state.toolExecutions.values()][0];
    expect(snapshot?.status).toBe("SUCCEEDED");
    expect(snapshot?.effect).toBe("reconcilable_write");
  });

  test("an authorized bash command executes and captures its output", async () => {
    const deps = makeDeps([bashTool(root)]);
    await deps.store.append(
      [sessionCreated(1), turnStarted(2, 1)].map((event) => ({
        ...event,
        sessionId: SESSION_ID,
      })),
      0,
    );
    const summary = await executeToolCall(
      deps,
      { name: "bash", argumentsJson: JSON.stringify({ command: "echo runtime" }) },
      { signal: new AbortController().signal, authorizer: granting(["shell.exec"]) },
    );
    expect(summary.status).toBe("SUCCEEDED");
    const state = await projectSessionState(deps);
    const snapshot = [...state.toolExecutions.values()][0];
    expect(snapshot?.status).toBe("SUCCEEDED");
    if (snapshot?.resultJson !== undefined) {
      expect(JSON.parse(snapshot.resultJson)).toMatchObject({ exitCode: 0, stdout: "runtime\n" });
    }
  });

  test("a write without its capability granted is rejected before execution", async () => {
    const deps = makeDeps([writeFileTool(root), bashTool(root)]);
    await deps.store.append(
      [sessionCreated(1), turnStarted(2, 1)].map((event) => ({
        ...event,
        sessionId: SESSION_ID,
      })),
      0,
    );
    const denied = capabilityAuthorizer({
      policy: {
        workspaceRoots: [root],
        grants: [],
        leases: [],
        approvableCapabilities: ["fs.write", "shell.exec"],
      },
      now: () => NOW,
    });
    for (const proposal of [
      { name: "write_file", argumentsJson: JSON.stringify({ path: "b.txt", content: "x" }) },
      { name: "bash", argumentsJson: JSON.stringify({ command: "echo nope" }) },
    ]) {
      const summary = await executeToolCall(deps, proposal, {
        signal: new AbortController().signal,
        authorizer: denied,
      });
      expect(summary.status).toBe("REJECTED");
    }
    const state = await projectSessionState(deps);
    expect([...state.toolExecutions.values()].every((s) => s.status === "REJECTED")).toBe(true);
    const events = await deps.store.readStream(SESSION_ID, 0);
    expect(events.map((event) => event.type)).not.toContain("ToolStarted");
  });

  test("crash after the rename, before the result event: INDETERMINATE -> reconcile -> SUCCEEDED", async () => {
    const input = { path: "crashed.txt", content: "did the rename happen?" };
    const tool = writeFileTool(root);
    // The real side effect happened (the rename completed) — then the
    // process died before any terminal event could be appended.
    const outcome = await tool.execute({ signal: new AbortController().signal }, input);
    if (outcome.status !== "succeeded") {
      throw new Error(`expected the real write to succeed: ${JSON.stringify(outcome)}`);
    }

    const store = inMemoryEventStore();
    const crashStream = [
      sessionCreated(1),
      turnStarted(2, 1),
      toolProposed(3, 1, {
        name: "write_file",
        argumentsJson: JSON.stringify(input),
        effect: "reconcilable_write",
      }),
      toolAuthorized(4, 1),
      toolStarted(5, 1),
      toolIndeterminate(6, 1, "process crashed after rename, before the result event"),
    ].map((event) => ({ ...event, sessionId: SESSION_ID }));
    await store.append(crashStream, 0);

    const deps: ToolRuntimeDeps = {
      store,
      sessionId: SESSION_ID,
      tools: [tool],
      now: () => 1,
      newEventId: () => asEventId("event-reconcile"),
      newToolExecutionId: () => asToolExecutionId("tool-exec-1"),
    };
    const crashed = await projectSessionState(deps);
    const snapshot = [...crashed.toolExecutions.values()][0];
    expect(snapshot?.status).toBe("INDETERMINATE");

    // Recovery (M3-T004 will orchestrate this): reconcile verifies the
    // filesystem fact and the conclusion lands as a durable ToolReconciled.
    if (tool.reconcile === undefined) {
      throw new Error("write_file must define reconcile");
    }
    const reconciliation = await tool.reconcile({ signal: new AbortController().signal }, input);
    expect(reconciliation.status).toBe("succeeded");
    if (reconciliation.status !== "succeeded") {
      throw new Error("expected verified reconciliation");
    }
    await store.append(
      [toolReconciled(7, 1, "succeeded", reconciliation.resultJson)].map((event) => ({
        ...event,
        sessionId: SESSION_ID,
      })),
      6,
    );

    const settled = await projectSessionState(deps);
    const finalSnapshot = [...settled.toolExecutions.values()][0];
    expect(finalSnapshot?.status).toBe("SUCCEEDED");
    expect(finalSnapshot?.reconciliationCount).toBe(1);
    expect(await readFile(join(root, "crashed.txt"), "utf8")).toBe(input.content);
  });
});
