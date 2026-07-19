import { mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";

const check = process.argv.includes("--check");
const GENERATED_COMMENT =
  "<!-- Generated from {source} by adapters/render.mjs; do not edit. -->";

function dumpsJson(payload) {
  return `${JSON.stringify(payload, null, 2)}\n`;
}

function parseSimpleToml(path) {
  const payload = {};
  const text = readFileSync(path, "utf8");
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const match = line.match(/^(\w+)\s*=\s*(".*")\s*$/);
    if (!match) continue;
    payload[match[1]] = JSON.parse(match[2]);
  }
  return payload;
}

function commandMarkdown(sourcePath, payload) {
  const relative = sourcePath.replaceAll("\\", "/");
  const prompt = (payload.prompt || "").replaceAll("{{args}}", "$ARGUMENTS");
  return `---\ndescription: ${payload.description}\n---\n${GENERATED_COMMENT.replace("{source}", relative)}\n\n${prompt}\n`;
}

function expectedFiles() {
  const files = new Map([
    [
      ".codex-plugin/plugin.json",
      dumpsJson({
        name: "praxis-next",
        version: "0.1.0",
        description: "Praxis Next Codex 薄适配器",
        commands: ["/praxis-help", "/praxis-check", "/praxis-quick", "/praxis-start"],
      }),
    ],
    [
      ".claude-plugin/plugin.json",
      dumpsJson({
        name: "praxis-next",
        version: "0.1.0",
        description: "Praxis Next Claude Code 薄适配器",
        commands: ["/praxis-help", "/praxis-check", "/praxis-quick", "/praxis-start"],
      }),
    ],
    [
      ".claude-plugin/marketplace.json",
      dumpsJson({
        name: "Praxis Next",
        summary: "调用已安装 Praxis CLI 的薄平台适配器",
        locale: "zh-CN",
      }),
    ],
    [
      ".orca-plugin/plugin.json",
      dumpsJson({
        id: "com.fausto.praxis-next",
        name: "praxis-next",
        version: "0.1.0",
        description: "Praxis Next Orca 薄适配器与本地命令源",
        main: "main.js",
        commandsDir: "../commands",
      }),
    ],
    [
      ".orca-plugin/main.js",
      "export default function activate() {}\n",
    ],
  ]);

  for (const entry of readdirSync("commands", { withFileTypes: true })) {
    if (!entry.isFile() || !entry.name.endsWith(".toml")) continue;
    const sourcePath = join("commands", entry.name);
    const payload = parseSimpleToml(sourcePath);
    files.set(join("commands", entry.name.replace(/\.toml$/, ".md")), commandMarkdown(sourcePath, payload));
  }
  return files;
}

function generatedCommandFiles() {
  try {
    return readdirSync("commands")
      .filter((name) => name.endsWith(".md"))
      .map((name) => join("commands", name));
  } catch {
    return [];
  }
}

const files = expectedFiles();
let drift = false;
for (const [path, body] of files) {
  if (check) {
    let current = "";
    try {
      current = readFileSync(path, "utf8");
    } catch {
      drift = true;
      console.error(`缺少生成文件：${path}`);
      continue;
    }
    if (current !== body) {
      drift = true;
      console.error(`生成文件漂移：${path}`);
    }
  } else {
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, body);
  }
}
for (const path of generatedCommandFiles()) {
  if (!files.has(path)) {
    if (check) {
      drift = true;
      console.error(`意外生成文件：${path}`);
    } else {
      rmSync(path);
    }
  }
}
process.exit(drift ? 1 : 0);
