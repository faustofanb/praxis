import { mkdir, mkdtemp, readdir, readFile, realpath, rm, stat, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { validateToolDefinitions } from "@praxis/core";
import { bashTool, localWriteTools, readFileTool, writeFileTool } from "@praxis/tools-local";
import { afterEach, beforeEach, describe, expect, test } from "vitest";

let root: string;

beforeEach(async () => {
  root = await mkdtemp(join(tmpdir(), "praxis-write-"));
});
afterEach(async () => {
  await rm(root, { recursive: true, force: true });
});

const signal = () => ({ signal: new AbortController().signal });

describe("write_file (reconcilable_write, ADR-0011)", () => {
  test("writes content atomically and reports bytes", async () => {
    const tool = writeFileTool(root);
    const outcome = await tool.execute(signal(), {
      path: "notes/a.txt",
      content: "hello praxis",
    });
    // Parent must exist — implicit mkdir is deliberately not provided.
    if (outcome.status !== "failed") {
      throw new Error("expected missing-parent failure");
    }
    expect(outcome.error.message).toContain("parent directory does not exist");

    await mkdir(join(root, "notes"));
    const ok = await tool.execute(signal(), { path: "notes/a.txt", content: "hello praxis" });
    expect(ok).toEqual({
      status: "succeeded",
      resultJson: JSON.stringify({ path: "notes/a.txt", bytes: 12 }),
    });
    expect(await readFile(join(root, "notes", "a.txt"), "utf8")).toBe("hello praxis");
  });

  test("overwrites an existing file and leaves no temp artifacts behind", async () => {
    await writeFile(join(root, "a.txt"), "old");
    const tool = writeFileTool(root);
    const outcome = await tool.execute(signal(), { path: "a.txt", content: "new content" });
    expect(outcome.status).toBe("succeeded");
    expect(await readFile(join(root, "a.txt"), "utf8")).toBe("new content");
    expect(await readdir(root)).toEqual(["a.txt"]);
  });

  test("refuses to write the root itself or an existing directory", async () => {
    const tool = writeFileTool(root);
    await mkdir(join(root, "sub"));
    for (const path of [".", "sub"]) {
      const outcome = await tool.execute(signal(), { path, content: "x" });
      expect(outcome.status).toBe("failed");
    }
    expect((await readdir(root)).includes("sub")).toBe(true);
  });

  test("reconcile verifies by content comparison, mutating nothing", async () => {
    const tool = writeFileTool(root);
    if (tool.reconcile === undefined) {
      throw new Error("write_file must define reconcile (reconcilable_write)");
    }
    await tool.execute(signal(), { path: "a.txt", content: "settled" });
    const before = await stat(join(root, "a.txt"));

    const match = await tool.reconcile(signal(), { path: "a.txt", content: "settled" });
    expect(match).toEqual({
      status: "succeeded",
      resultJson: JSON.stringify({ path: "a.txt", verified: true, bytes: 7 }),
    });
    const after = await stat(join(root, "a.txt"));
    expect(after.mtimeMs).toBe(before.mtimeMs);

    const mismatch = await tool.reconcile(signal(), { path: "a.txt", content: "other" });
    expect(mismatch).toMatchObject({
      status: "failed",
      error: { message: expect.stringContaining("different content") as unknown as string },
    });
  });

  test("reconcile settles a crashed write as provably absent when the file is missing", async () => {
    const tool = writeFileTool(root);
    if (tool.reconcile === undefined) {
      throw new Error("write_file must define reconcile");
    }
    const outcome = await tool.reconcile(signal(), { path: "never.txt", content: "x" });
    expect(outcome).toMatchObject({
      status: "failed",
      error: { message: expect.stringContaining("did not take effect") as unknown as string },
    });
  });

  test("read_file observes the reconciled write — tools agree through the filesystem", async () => {
    const write = writeFileTool(root);
    await write.execute(signal(), { path: "shared.txt", content: "via write" });
    const read = readFileTool(root);
    const outcome = await read.execute(signal(), { path: "shared.txt" });
    expect(outcome).toMatchObject({ status: "succeeded" });
    if (outcome.status === "succeeded") {
      expect(JSON.parse(outcome.resultJson)).toMatchObject({ content: "via write" });
    }
  });
});

describe("bash (non_idempotent_write, honest outcomes)", () => {
  test("runs with cwd pinned to the workspace root and captures output", async () => {
    const tool = bashTool(root);
    const outcome = await tool.execute(signal(), { command: "pwd && echo done" });
    expect(outcome).toEqual({
      status: "succeeded",
      resultJson: JSON.stringify({
        exitCode: 0,
        stdout: `${await realpath(root)}\ndone\n`,
        stderr: "",
        stdoutTruncatedBytes: 0,
        stderrTruncatedBytes: 0,
      }),
    });
  });

  test("a completed non-zero exit is a failed fact carrying the stderr tail", async () => {
    const tool = bashTool(root);
    const outcome = await tool.execute(signal(), {
      command: "echo boom >&2; exit 3",
    });
    expect(outcome).toMatchObject({
      status: "failed",
      error: { message: expect.stringContaining("exited with code 3") as unknown as string },
    });
    if (outcome.status === "failed") {
      expect(outcome.error.message).toContain("boom");
    }
  });

  test("a timeout kills the command and reports INDETERMINATE, never failed", async () => {
    const tool = bashTool(root);
    const outcome = await tool.execute(signal(), {
      command: "echo partial; sleep 30",
      timeoutMs: 1_000,
    });
    expect(outcome).toEqual({
      status: "indeterminate",
      reason: expect.stringContaining("timed out after 1000ms") as unknown as string,
    });
  });

  test("output beyond the budget is truncated with a byte marker and counted", async () => {
    const tool = bashTool(root, { maxOutputBytes: 64 });
    const outcome = await tool.execute(signal(), { command: "printf 'a%.0s' {1..1000}" });
    expect(outcome.status).toBe("succeeded");
    if (outcome.status !== "succeeded") {
      throw new Error("expected success");
    }
    const result = JSON.parse(outcome.resultJson) as {
      stdout: string;
      stdoutTruncatedBytes: number;
    };
    expect(result.stdout.startsWith("aaa")).toBe(true);
    expect(result.stdout).toContain("bytes truncated]");
    expect(result.stdoutTruncatedBytes).toBe(1000 - 64);
  });

  test("declares the shell.exec capability scoped to the bound root and passes registration", () => {
    const write = writeFileTool(root);
    expect(write.effect).toBe("reconcilable_write");
    expect(write.requiredCapability).toEqual({
      name: "fs.write",
      scope: { kind: "workspace", root },
    });
    const bash = bashTool(root);
    expect(bash.effect).toBe("non_idempotent_write");
    expect(bash.requiredCapability).toEqual({
      name: "shell.exec",
      scope: { kind: "workspace", root },
    });
    expect(bash.reconcile).toBeUndefined();
    expect(() => validateToolDefinitions(localWriteTools(root))).not.toThrow();
  });
});
