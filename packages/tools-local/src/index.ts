import type { ToolDefinition } from "@praxis/contracts";
import { packageName as contractsPackageName } from "@praxis/contracts";
import type { LocalReadToolOptions } from "./read-tools";
import { listDirTool, readFileTool } from "./read-tools";
import type { LocalWriteToolOptions } from "./write-tools";
import { bashTool, writeFileTool } from "./write-tools";

export const packageName = "@praxis/tools-local";
export const workspaceDependencies = [contractsPackageName] as const;

export type { LocalReadToolOptions } from "./read-tools";
export { listDirTool, readFileTool, truncateContent } from "./read-tools";
export type { LocalWriteToolOptions } from "./write-tools";
export { bashTool, writeFileTool } from "./write-tools";

/** The v1 local read-only tool set bound to a workspace root. */
export function localReadTools(
  root: string,
  options?: LocalReadToolOptions,
): readonly ToolDefinition[] {
  return [readFileTool(root, options), listDirTool(root)];
}

/** The v1 local write-capable tool set bound to a workspace root. */
export function localWriteTools(
  root: string,
  options?: LocalWriteToolOptions,
): readonly ToolDefinition[] {
  return [writeFileTool(root), bashTool(root, options)];
}
