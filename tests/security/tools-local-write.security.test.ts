import { mkdir, mkdtemp, readdir, readFile, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { bashTool, writeFileTool } from "@praxis/tools-local";
import { afterEach, beforeEach, describe, expect, test } from "vitest";

let root: string;
let outsideRoot: string;

beforeEach(async () => {
  root = await mkdtemp(join(tmpdir(), "praxis-wsec-"));
  outsideRoot = await mkdtemp(join(tmpdir(), "praxis-wout-"));
  await writeFile(join(outsideRoot, "secret.txt"), "outside secret");
  await mkdir(join(root, "sub"));
});
afterEach(async () => {
  await rm(root, { recursive: true, force: true });
  await rm(outsideRoot, { recursive: true, force: true });
});

const signal = () => ({ signal: new AbortController().signal });

/**
 * Adversarial matrix for the layer-2 confinement of the write tools
 * (docs/02 section 9.3; M3 failure acceptance: "path/capability bypass
 * attempts rejected"). Every case asserts both the failed outcome and that
 * nothing was written outside the root.
 */

describe("write_file escape attempts", () => {
  test("relative traversal out of the root is rejected before any write", async () => {
    const tool = writeFileTool(root);
    const outcome = await tool.execute(signal(), {
      path: "../../outside.txt",
      content: "escaped",
    });
    expect(outcome).toMatchObject({
      status: "failed",
      error: { message: expect.stringContaining("escapes the workspace root") },
    });
    expect(await readFile(join(outsideRoot, "secret.txt"), "utf8")).toBe("outside secret");
  });

  test("absolute paths outside the root are rejected", async () => {
    const tool = writeFileTool(root);
    const outcome = await tool.execute(signal(), {
      path: join(outsideRoot, "overwritten.txt"),
      content: "escaped",
    });
    expect(outcome).toMatchObject({ status: "failed" });
    expect(await readdir(outsideRoot)).toEqual(["secret.txt"]);
  });

  test("symlink escapes are caught by the realpath double-check", async () => {
    await symlink(join(outsideRoot, "secret.txt"), join(root, "leak.txt"));
    const tool = writeFileTool(root);
    const outcome = await tool.execute(signal(), { path: "leak.txt", content: "pwned" });
    expect(outcome).toMatchObject({
      status: "failed",
      error: { message: expect.stringContaining("symlink") },
    });
    expect(await readFile(join(outsideRoot, "secret.txt"), "utf8")).toBe("outside secret");
  });

  test("a symlinked directory inside the root cannot smuggle writes out", async () => {
    await symlink(outsideRoot, join(root, "door"));
    const tool = writeFileTool(root);
    const outcome = await tool.execute(signal(), { path: "door/new.txt", content: "pwned" });
    expect(outcome).toMatchObject({ status: "failed" });
    expect(await readdir(outsideRoot)).toEqual(["secret.txt"]);
  });

  test("reconcile on an escape path claims nothing and never unlocks re-execution", async () => {
    const tool = writeFileTool(root);
    if (tool.reconcile === undefined) {
      throw new Error("write_file must define reconcile");
    }
    const outcome = await tool.reconcile(signal(), {
      path: "../../outside.txt",
      content: "escaped",
    });
    // The policy refused to look, and symlink state may have changed since
    // the execution, so absence is not provable. Only an observed conclusion
    // may be failed — the one outcome that unlocks re-execution.
    expect(outcome).toMatchObject({
      status: "indeterminate",
      reason: expect.stringContaining("cannot verify") as unknown as string,
    });
  });
});

describe("bash confinement honest limits", () => {
  test("cwd is the workspace root, and relative writes land inside it", async () => {
    const tool = bashTool(root);
    const outcome = await tool.execute(signal(), {
      command: "echo created > inside.txt && pwd",
    });
    expect(outcome.status).toBe("succeeded");
    expect(await readFile(join(root, "inside.txt"), "utf8")).toBe("created\n");
  });

  test("bash cannot be smuggled a second command through the input schema", async () => {
    const tool = bashTool(root);
    const outcome = await tool.execute(signal(), {
      command: 'echo \'{"path":"x","content":"y"}\'',
    });
    expect(outcome.status).toBe("succeeded");
    // The command ran; nothing about it granted any new capability — the
    // tool stays a single shell.exec scope bound to this root.
    expect(await readdir(root)).toEqual(["sub"]);
  });

  test("bash is not path-confined by design — the control is the capability gate (docs/02 9.3)", async () => {
    // v1 claims no OS sandbox: once shell.exec is granted, a command may
    // touch paths outside the workspace root. This pins the honest boundary
    // so nobody mistakes bash for path-confined; the gate that matters is
    // layer 1 (capability), covered in the integration suite.
    const tool = bashTool(root);
    const outside = join(outsideRoot, "via-bash.txt");
    const outcome = await tool.execute(signal(), {
      command: `touch ${outside} && echo ok`,
    });
    expect(outcome.status).toBe("succeeded");
    expect(await readdir(outsideRoot)).toContain("via-bash.txt");
  });
});
