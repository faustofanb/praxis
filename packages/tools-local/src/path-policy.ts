import { realpath } from "node:fs/promises";
import { basename, dirname, join, resolve, sep } from "node:path";

/**
 * Layer-2 path confinement shared by all local tools (docs/02 section 9.3):
 * lexical check first (resolve must stay under the root), then a realpath
 * double-check so symlinks cannot escape. Any escape throws — callers turn
 * that into a `failed` outcome before touching the filesystem.
 *
 * The realpath check resolves the deepest *existing* ancestor and reattaches
 * the missing tail lexically: writes to not-yet-existing files must pass
 * confinement too, and a missing file can never be a symlink.
 */

export async function resolveWithinRoot(root: string, relative: string): Promise<string> {
  const resolved = resolve(root, relative);
  if (resolved !== root && !resolved.startsWith(`${root}${sep}`)) {
    throw new Error(`path escapes the workspace root: ${relative}`);
  }
  const realRoot = await realpath(root);
  const physical = await realpathOfExistingAncestor(resolved);
  if (physical !== realRoot && !physical.startsWith(`${realRoot}${sep}`)) {
    throw new Error(`path escapes the workspace root via symlink: ${relative}`);
  }
  return physical;
}

async function realpathOfExistingAncestor(absolute: string): Promise<string> {
  let current = absolute;
  const tail: string[] = [];
  for (;;) {
    try {
      const real = await realpath(current);
      return tail.length === 0 ? real : join(real, ...tail);
    } catch (error) {
      if (!isNotFound(error)) {
        throw error;
      }
      tail.unshift(basename(current));
      current = dirname(current);
    }
  }
}

function isNotFound(error: unknown): boolean {
  return error instanceof Error && (error as NodeJS.ErrnoException).code === "ENOENT";
}
