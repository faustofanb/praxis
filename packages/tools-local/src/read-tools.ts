import { readdir, readFile, stat } from "node:fs/promises";
import type { ToolDefinition, ToolExecutionContext, ToolExecutionOutcome } from "@praxis/contracts";
import { z } from "zod";
import { resolveWithinRoot } from "./path-policy";

/**
 * Local read-only tools (docs/03 M2.3). Every path is confined to the
 * injected workspace root, lexically and through realpath (symlinks cannot
 * escape), and file contents are head-truncated to a byte budget before
 * becoming durable facts. Deterministic ordering everywhere.
 */

export type LocalReadToolOptions = {
  /** Max UTF-8 bytes of file content per result. Default 64 KiB. */
  readonly maxResultBytes?: number;
};

const DEFAULT_MAX_RESULT_BYTES = 64 * 1024;
const TRUNCATION_RESERVE_BYTES = 40;

const encoder = new TextEncoder();

function utf8Bytes(text: string): number {
  return encoder.encode(text).length;
}

function cutToBytes(text: string, limitBytes: number): string {
  let kept = "";
  let bytes = 0;
  for (const char of text) {
    const charBytes = utf8Bytes(char);
    if (bytes + charBytes > limitBytes) {
      break;
    }
    kept += char;
    bytes += charBytes;
  }
  return kept;
}

export function truncateContent(
  content: string,
  maxBytes: number,
): { content: string; truncatedBytes: number } {
  const bytes = utf8Bytes(content);
  if (bytes <= maxBytes) {
    return { content, truncatedBytes: 0 };
  }
  const kept = cutToBytes(content, maxBytes - TRUNCATION_RESERVE_BYTES);
  const truncatedBytes = bytes - utf8Bytes(kept);
  return {
    content: `${kept}…[+${truncatedBytes} bytes truncated]`,
    truncatedBytes,
  };
}

function failed(message: string): ToolExecutionOutcome {
  return { status: "failed", error: { message } };
}

const ReadPathInputSchema = z.object({ path: z.string().min(1) });
const READ_PATH_PARAMETERS_JSON =
  '{"type":"object","properties":{"path":{"type":"string","minLength":1}},"required":["path"],"additionalProperties":false}';

export function readFileTool(root: string, options: LocalReadToolOptions = {}): ToolDefinition {
  const maxResultBytes = options.maxResultBytes ?? DEFAULT_MAX_RESULT_BYTES;
  return {
    name: "read_file",
    description:
      "Read a UTF-8 text file inside the workspace root; large contents are head-truncated with a byte marker",
    effect: "read_only",
    inputSchema: ReadPathInputSchema,
    parametersJson: READ_PATH_PARAMETERS_JSON,
    async execute(_context: ToolExecutionContext, input: unknown): Promise<ToolExecutionOutcome> {
      const { path } = ReadPathInputSchema.parse(input);
      try {
        const target = await resolveWithinRoot(root, path);
        const info = await stat(target);
        if (!info.isFile()) {
          return failed(`not a file: ${path}`);
        }
        const raw = await readFile(target, "utf8");
        const { content, truncatedBytes } = truncateContent(raw, maxResultBytes);
        return {
          status: "succeeded",
          resultJson: JSON.stringify({
            path,
            content,
            ...(truncatedBytes > 0 ? { truncatedBytes } : {}),
          }),
        };
      } catch (error) {
        return failed(error instanceof Error ? error.message : String(error));
      }
    },
  };
}

const DIRENT_KINDS = ["file", "dir", "symlink", "other"] as const;
type DirentKind = (typeof DIRENT_KINDS)[number];

function direntKind(type: string): DirentKind {
  return (DIRENT_KINDS as readonly string[]).includes(type) ? (type as DirentKind) : "other";
}

export function listDirTool(root: string): ToolDefinition {
  return {
    name: "list_dir",
    description: "List directory entries inside the workspace root, sorted by name",
    effect: "read_only",
    inputSchema: ReadPathInputSchema,
    parametersJson: READ_PATH_PARAMETERS_JSON,
    async execute(_context: ToolExecutionContext, input: unknown): Promise<ToolExecutionOutcome> {
      const { path } = ReadPathInputSchema.parse(input);
      try {
        const target = await resolveWithinRoot(root, path);
        const info = await stat(target);
        if (!info.isDirectory()) {
          return failed(`not a directory: ${path}`);
        }
        const entries = await readdir(target, { withFileTypes: true });
        entries.sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
        return {
          status: "succeeded",
          resultJson: JSON.stringify({
            path,
            entries: entries.map((entry) => ({
              name: entry.name,
              kind: direntKind(
                entry.isFile()
                  ? "file"
                  : entry.isDirectory()
                    ? "dir"
                    : entry.isSymbolicLink()
                      ? "symlink"
                      : "other",
              ),
            })),
          }),
        };
      } catch (error) {
        return failed(error instanceof Error ? error.message : String(error));
      }
    },
  };
}
