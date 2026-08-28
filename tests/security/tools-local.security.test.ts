import { mkdir, mkdtemp, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { ToolDefinition } from "@praxis/contracts";
import { asEventId, asToolExecutionId } from "@praxis/contracts";
import type { ToolRuntimeDeps } from "@praxis/core";
import { executeToolCall, projectSessionState, readOnlyAuthorizer } from "@praxis/core";
import { localReadTools, readFileTool } from "@praxis/tools-local";
import { afterEach, beforeEach, describe, expect, test } from "vitest";
import { z } from "zod";
import { inMemoryEventStore } from "../helpers/in-memory-event-store";
import { sessionCreated, turnStarted } from "../helpers/session-events";

const TEST_SESSION_ID = sessionCreated(1).sessionId;

let root: string;
let outsideRoot: string;

beforeEach(async () => {
  root = await mkdtemp(join(tmpdir(), "praxis-sec-"));
  outsideRoot = await mkdtemp(join(tmpdir(), "praxis-out-"));
  await writeFile(join(root, "note.txt"), "inside content");
  await writeFile(join(outsideRoot, "secret.txt"), "outside secret");
  await mkdir(join(root, "sub"));
  await writeFile(join(root, "sub", "data.json"), "{}");
});

afterEach(async () => {
  await rm(root, { recursive: true, force: true });
  await rm(outsideRoot, { recursive: true, force: true });
});

describe("workspace-root confinement", () => {
  test("read_file rejects relative path traversal out of the root", async () => {
    const tool = readFileTool(root);
    const outcome = await tool.execute(
      { signal: new AbortController().signal },
      {
        path: "../../etc/passwd",
      },
    );
    expect(outcome).toMatchObject({
      status: "failed",
      error: { message: expect.stringContaining("escapes the workspace root") },
    });
  });

  test("read_file rejects absolute paths outside the root", async () => {
    const tool = readFileTool(root);
    const outcome = await tool.execute(
      { signal: new AbortController().signal },
      {
        path: join(outsideRoot, "secret.txt"),
      },
    );
    expect(outcome).toMatchObject({ status: "failed" });
  });

  test("read_file rejects symlink escapes through realpath checks", async () => {
    await symlink(join(outsideRoot, "secret.txt"), join(root, "leak.txt"));
    const tool = readFileTool(root);
    const outcome = await tool.execute(
      { signal: new AbortController().signal },
      {
        path: "leak.txt",
      },
    );
    expect(outcome).toMatchObject({
      status: "failed",
      error: { message: expect.stringContaining("symlink") },
    });
  });

  test("paths inside the root keep working, including subdirectories", async () => {
    const tool = readFileTool(root);
    const outcome = await tool.execute(
      { signal: new AbortController().signal },
      {
        path: "sub/data.json",
      },
    );
    expect(outcome).toMatchObject({ status: "succeeded" });
  });

  test("list_dir rejects traversal and reports sorted entries inside the root", async () => {
    const tools = localReadTools(root);
    const listDir = tools.find((tool) => tool.name === "list_dir");
    if (listDir === undefined) {
      throw new Error("list_dir missing from local read tools");
    }
    const denied = await listDir.execute(
      { signal: new AbortController().signal },
      {
        path: "../..",
      },
    );
    expect(denied).toMatchObject({ status: "failed" });

    const allowed = await listDir.execute(
      { signal: new AbortController().signal },
      {
        path: ".",
      },
    );
    if (allowed.status !== "succeeded") {
      throw new Error("expected list_dir success");
    }
    const result = JSON.parse(allowed.resultJson) as {
      entries: Array<{ name: string; kind: string }>;
    };
    expect(result.entries.map((entry) => entry.name)).toEqual(["note.txt", "sub"].sort());
  });
});

describe("deny-by-default authorization", () => {
  function writeToolDeps(tools: readonly ToolDefinition[]): ToolRuntimeDeps {
    let counter = 500;
    let executions = 0;
    return {
      store: inMemoryEventStore(),
      sessionId: TEST_SESSION_ID,
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

  const writeTool: ToolDefinition = {
    name: "delete_everything",
    description: "adversarial write tool",
    effect: "non_idempotent_write",
    inputSchema: z.object({}),
    parametersJson: '{"type":"object"}',
    async execute() {
      return { status: "succeeded", resultJson: '"deleted"' };
    },
  };

  test("a non-read-only tool is rejected before execution", async () => {
    const deps = writeToolDeps([writeTool]);
    await deps.store.append([sessionCreated(1), turnStarted(2, 1)], 0);

    const summary = await executeToolCall(
      deps,
      { name: "delete_everything", argumentsJson: "{}" },
      { signal: new AbortController().signal },
    );

    expect(summary.status).toBe("REJECTED");
    const state = await projectSessionState(deps);
    const snapshot = [...state.toolExecutions.values()][0];
    expect(snapshot?.status).toBe("REJECTED");
    expect(snapshot?.rejectionReason).toContain("not permitted");
  });

  test("an adversarial proposal cannot forge an effect class; the registry decides", async () => {
    const deps = writeToolDeps(localReadTools(root));
    await deps.store.append([sessionCreated(1), turnStarted(2, 1)], 0);

    const summary = await executeToolCall(
      deps,
      { name: "read_file", argumentsJson: '{"path":"note.txt"}' },
      { signal: new AbortController().signal },
    );

    expect(summary.status).toBe("SUCCEEDED");
    const state = await projectSessionState(deps);
    const snapshot = [...state.toolExecutions.values()][0];
    expect(snapshot?.effect).toBe("read_only");
  });

  test("an unregistered tool is proposed conservatively and denied", async () => {
    const deps = writeToolDeps(localReadTools(root));
    await deps.store.append([sessionCreated(1), turnStarted(2, 1)], 0);

    const summary = await executeToolCall(
      deps,
      { name: "shell_exec", argumentsJson: '{"cmd":"rm -rf /"}' },
      { signal: new AbortController().signal },
    );

    expect(summary.status).toBe("REJECTED");
    const state = await projectSessionState(deps);
    const snapshot = [...state.toolExecutions.values()][0];
    expect(snapshot?.effect).toBe("non_idempotent_write");
    expect(snapshot?.rejectionReason).toContain("unknown tool");
  });

  test("readOnlyAuthorizer denies every write-capable effect class", () => {
    for (const effect of [
      "idempotent_write",
      "reconcilable_write",
      "non_idempotent_write",
    ] as const) {
      expect(readOnlyAuthorizer({ name: "x", effect }).decision).toBe("rejected");
    }
    expect(readOnlyAuthorizer({ name: "x", effect: "read_only" })).toEqual({
      decision: "authorized",
    });
  });
});
