import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import { readFile, realpath, rename, stat, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import type {
  ReconciliationOutcome,
  ToolDefinition,
  ToolExecutionContext,
  ToolExecutionOutcome,
} from "@praxis/contracts";
import { z } from "zod";
import { resolveWithinRoot } from "./path-policy";

/**
 * Local write-capable tools (docs/02 section 4.5, layer 2 of section 9.3).
 * Capability enforcement is layer 1 and already lives in Core (M3-T002):
 * both tools declare requiredCapability scoped to the bound root, so the
 * runtime gates them before execute is ever reached. What the tools own is
 * honest outcomes (section 8.2): a returned `failed` always means the effect
 * provably did not happen; anything unknowable is `indeterminate`.
 *
 * No OS-level sandbox is claimed (docs/02 section 9.3): bash can still cd
 * elsewhere — the v1 control is the shell.exec capability gate plus cwd,
 * timeout, and output truncation implemented here.
 */

export type LocalWriteToolOptions = {
  /** Default wall-clock budget per bash command. Default 30s. */
  readonly defaultTimeoutMs?: number;
  /** Hard cap for a caller-supplied timeoutMs. Default 120s. */
  readonly maxTimeoutMs?: number;
  /** Max UTF-8 bytes kept of each of stdout/stderr. Default 64 KiB. */
  readonly maxOutputBytes?: number;
};

const DEFAULT_TIMEOUT_MS = 30_000;
const MAX_TIMEOUT_MS = 120_000;
const DEFAULT_MAX_OUTPUT_BYTES = 64 * 1024;
const FAILED_MESSAGE_TAIL_BYTES = 512;

const encoder = new TextEncoder();

function utf8Bytes(text: string): number {
  return encoder.encode(text).length;
}

function failed(message: string): ToolExecutionOutcome {
  return { status: "failed", error: { message } };
}

function reconcileFailed(message: string): ReconciliationOutcome {
  return { status: "failed", error: { message } };
}

function errnoCode(error: unknown): string | undefined {
  if (error instanceof Error && "code" in error && typeof error.code === "string") {
    return error.code;
  }
  return undefined;
}

const WriteFileInputSchema = z.object({
  path: z.string().min(1),
  content: z.string(),
});
const WRITE_FILE_PARAMETERS_JSON =
  '{"type":"object","properties":{"path":{"type":"string","minLength":1},"content":{"type":"string"}},"required":["path","content"],"additionalProperties":false}';

export function writeFileTool(root: string): ToolDefinition {
  return {
    name: "write_file",
    description:
      "Atomically write UTF-8 text to a path inside the workspace root (temp file + rename); the parent directory must exist",
    effect: "reconcilable_write",
    requiredCapability: { name: "fs.write", scope: { kind: "workspace", root } },
    inputSchema: WriteFileInputSchema,
    parametersJson: WRITE_FILE_PARAMETERS_JSON,
    async execute(_context: ToolExecutionContext, input: unknown): Promise<ToolExecutionOutcome> {
      const { path, content } = WriteFileInputSchema.parse(input);
      try {
        const target = await resolveWithinRoot(root, path);
        const existing = await stat(target).then(
          (info) => info,
          () => undefined,
        );
        if (existing !== undefined && !existing.isFile()) {
          return failed(`not a file: ${path}`);
        }
        const parent = await stat(dirname(target)).then(
          (info) => info,
          () => undefined,
        );
        if (parent === undefined) {
          return failed(`parent directory does not exist: ${path}`);
        }
        if (!parent.isDirectory()) {
          return failed(`parent is not a directory: ${path}`);
        }
        // Same directory => same filesystem => rename is atomic: readers see
        // either the old content or the new one, never a partial write.
        const temp = join(dirname(target), `.praxis-tmp-${randomUUID()}`);
        await writeFile(temp, content, "utf8");
        await rename(temp, target);
        return {
          status: "succeeded",
          resultJson: JSON.stringify({ path, bytes: utf8Bytes(content) }),
        };
      } catch (error) {
        // writeFile/rename threw => the target was never touched (rename is
        // the last, atomic step), so this is a provable non-effect.
        return failed(error instanceof Error ? error.message : String(error));
      }
    },
    async reconcile(
      _context: ToolExecutionContext,
      input: unknown,
    ): Promise<ReconciliationOutcome> {
      const { path, content } = WriteFileInputSchema.parse(input);
      let target: string;
      try {
        target = await resolveWithinRoot(root, path);
      } catch (error) {
        // The path policy refused to resolve the recorded path (escape,
        // symlink violation, or the root is gone). Symlink state may have
        // changed since the execution, so the refusal proves nothing about
        // the effect: reporting failed would claim provable absence — the
        // only outcome that unlocks re-execution (contracts tool port).
        const detail = error instanceof Error ? error.message : String(error);
        return {
          status: "indeterminate",
          reason: `cannot verify: the recorded path is not reachable inside the root (${detail})`,
        };
      }
      try {
        const actual = await readFile(target, "utf8");
        if (actual === content) {
          return {
            status: "succeeded",
            resultJson: JSON.stringify({
              path,
              verified: true,
              bytes: utf8Bytes(content),
            }),
          };
        }
        return reconcileFailed(
          `the write did not take effect: ${path} exists with different content`,
        );
      } catch (error) {
        const code = errnoCode(error);
        if (code === "ENOENT") {
          // Resolved inside the root but absent: provable non-effect.
          return reconcileFailed(`the write did not take effect: no file at ${path}`);
        }
        if (code === "EISDIR") {
          // A directory occupies the target: the content write is not there.
          return reconcileFailed(`the write did not take effect: a directory occupies ${path}`);
        }
        const detail = error instanceof Error ? error.message : String(error);
        return {
          status: "indeterminate",
          reason: `cannot verify: ${path} is not readable (${detail})`,
        };
      }
    },
  };
}

const BashInputSchema = z.object({
  command: z.string().min(1),
  timeoutMs: z.number().int().positive().max(MAX_TIMEOUT_MS).optional(),
});
const BASH_PARAMETERS_JSON =
  '{"type":"object","properties":{"command":{"type":"string","minLength":1},"timeoutMs":{"type":"integer","minimum":1,"maximum":120000}},"required":["command"],"additionalProperties":false}';

export function bashTool(root: string, options: LocalWriteToolOptions = {}): ToolDefinition {
  const defaultTimeoutMs = options.defaultTimeoutMs ?? DEFAULT_TIMEOUT_MS;
  const maxOutputBytes = options.maxOutputBytes ?? DEFAULT_MAX_OUTPUT_BYTES;
  return {
    name: "bash",
    description:
      "Run a bash command with cwd pinned to the workspace root under a hard timeout; stdout/stderr are captured and byte-truncated",
    effect: "non_idempotent_write",
    requiredCapability: { name: "shell.exec", scope: { kind: "workspace", root } },
    inputSchema: BashInputSchema,
    parametersJson: BASH_PARAMETERS_JSON,
    async execute(context: ToolExecutionContext, input: unknown): Promise<ToolExecutionOutcome> {
      const { command, timeoutMs } = BashInputSchema.parse(input);
      const budgetMs = timeoutMs ?? defaultTimeoutMs;
      const cwd = await realpath(root);
      return new Promise<ToolExecutionOutcome>((resolveOutcome) => {
        const stdout = cappedCollector(maxOutputBytes);
        const stderr = cappedCollector(maxOutputBytes);
        let timedOut = false;
        const child = spawn("bash", ["-c", command], { cwd, stdio: ["ignore", "pipe", "pipe"] });

        const timer = setTimeout(() => {
          timedOut = true;
          child.kill("SIGKILL");
        }, budgetMs);
        const onAbort = () => {
          child.kill("SIGKILL");
        };
        context.signal.addEventListener("abort", onAbort, { once: true });

        child.stdout?.on("data", (chunk: Buffer) => {
          stdout.push(chunk);
        });
        child.stderr?.on("data", (chunk: Buffer) => {
          stderr.push(chunk);
        });
        child.once("error", (error) => {
          clearTimeout(timer);
          context.signal.removeEventListener("abort", onAbort);
          resolveOutcome(failed(`failed to start bash: ${error.message}`));
        });
        // "exit", not "close": a killed command's orphaned grandchildren can
        // hold the stdio pipes open long after bash itself died, and the
        // outcome must not wait for them.
        child.once("exit", (exitCode, signal) => {
          clearTimeout(timer);
          context.signal.removeEventListener("abort", onAbort);
          if (timedOut) {
            resolveOutcome({
              status: "indeterminate",
              reason: `command timed out after ${budgetMs}ms and was killed — effects unknown`,
            });
            return;
          }
          if (context.signal.aborted) {
            resolveOutcome({
              status: "indeterminate",
              reason: "turn aborted while the command was running — effects unknown",
            });
            return;
          }
          if (signal !== null) {
            resolveOutcome({
              status: "indeterminate",
              reason: `command terminated by signal ${signal} — effects unknown`,
            });
            return;
          }
          if (exitCode === 0) {
            resolveOutcome({
              status: "succeeded",
              resultJson: JSON.stringify({
                exitCode: 0,
                stdout: stdout.text(),
                stderr: stderr.text(),
                stdoutTruncatedBytes: stdout.truncatedBytes(),
                stderrTruncatedBytes: stderr.truncatedBytes(),
              }),
            });
            return;
          }
          const tail = stderr.text();
          resolveOutcome(
            failed(
              tail.length > 0
                ? `command exited with code ${exitCode}: ${tail.slice(-FAILED_MESSAGE_TAIL_BYTES)}`
                : `command exited with code ${exitCode}`,
            ),
          );
        });
      });
    },
  };
}

/**
 * Accumulates output chunks but keeps at most `maxBytes` in memory, so a
 * command flooding stdout cannot exhaust memory before its timeout fires.
 * The kept text ends with the same truncation marker the read tools use.
 */
function cappedCollector(maxBytes: number) {
  const chunks: Buffer[] = [];
  let kept = 0;
  let total = 0;
  return {
    push(chunk: Buffer): void {
      total += chunk.length;
      if (kept < maxBytes) {
        const take = Math.min(chunk.length, maxBytes - kept);
        chunks.push(chunk.subarray(0, take));
        kept += take;
      }
    },
    text(): string {
      const keptText = Buffer.concat(chunks).toString("utf8");
      return total > kept ? `${keptText}…[+${total - kept} bytes truncated]` : keptText;
    },
    truncatedBytes(): number {
      return total - kept;
    },
  };
}
