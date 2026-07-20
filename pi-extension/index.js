import { spawn } from "node:child_process";

export function splitArguments(value) {
  const arguments_ = [];
  let current = "";
  let quote = null;

  for (const character of String(value || "")) {
    if (quote) {
      if (character === quote) quote = null;
      else current += character;
    } else if (character === "\"" || character === "'") {
      quote = character;
    } else if (/\s/.test(character)) {
      if (current) arguments_.push(current);
      current = "";
    } else {
      current += character;
    }
  }

  if (quote) throw new Error("Unclosed quote in Praxis arguments");
  if (current) arguments_.push(current);
  return arguments_;
}

export function runPraxis(arguments_, options = {}) {
  const binary = options.binary || process.env.PRAXIS_BIN || "praxis";
  const cwd = options.cwd || process.cwd();

  return new Promise((resolve, reject) => {
    const child = spawn(binary, [...arguments_, "--json"], {
      cwd,
      env: process.env,
      shell: false,
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.on("error", reject);
    child.on("close", (status) => resolve({ status, stdout, stderr }));
  });
}

export default function praxisExtension(pi) {
  pi.registerCommand("praxis", {
    description: "Run the Praxis V2 CLI (usage: /praxis <command> [arguments])",
    handler: async (value, context) => {
      let arguments_;
      try {
        arguments_ = splitArguments(value);
      } catch (error) {
        context.ui.notify(error.message, "error");
        return;
      }

      if (arguments_.length === 0) {
        context.ui.notify("Usage: /praxis <command> [arguments]", "info");
        return;
      }

      try {
        const result = await runPraxis(arguments_, { cwd: context.cwd });
        const output = result.stdout.trim() || result.stderr.trim();
        context.ui.notify(
          output || `Praxis exited with status ${result.status}`,
          result.status === 0 ? "info" : "error",
        );
      } catch (error) {
        context.ui.notify(`Praxis could not start: ${error.message}`, "error");
      }
    },
  });
}
