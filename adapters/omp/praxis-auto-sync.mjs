import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const PLUGIN_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const AUTO_SYNC_SCRIPT = resolve(PLUGIN_ROOT, "scripts/praxis_auto_sync.py");

export function runPraxisAutoSync(workspace = process.cwd(), run = spawnSync) {
  const candidates = process.platform === "win32"
    ? [["py", ["-3"]], ["python", []]]
    : [["python3", []], ["python", []]];

  for (const [executable, prefix] of candidates) {
    const result = run(
      executable,
      [...prefix, AUTO_SYNC_SCRIPT, "--plugin-root", PLUGIN_ROOT, "--workspace", workspace, "--json"],
      { encoding: "utf8", timeout: 15_000 },
    );
    if (result.error?.code === "ENOENT") continue;
    if (result.error) return { status: "error", message: result.error.message };
    try {
      return JSON.parse(String(result.stdout || "{}"));
    } catch {
      return {
        status: "error",
        message: String(result.stderr || result.stdout || `auto-sync exited ${result.status}`).trim(),
      };
    }
  }
  return { status: "unavailable", message: "python runtime not found" };
}

export default function praxisAutoSyncExtension(pi) {
  pi.on("session_start", async (_event, ctx) => {
    const result = runPraxisAutoSync(ctx?.cwd || process.cwd());
    if (["not-praxis", "no-profile"].includes(result.status)) return;
    const profile = result.profile ? ` · ${result.profile}` : "";
    const level = ["error", "unavailable"].includes(result.status) ? "warning" : "info";
    ctx?.ui?.notify?.(`Praxis active${profile} · ${result.status}`, level);
  });
}
