import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";

const check = process.argv.includes("--check");
const files = new Map([
  [".codex-plugin/plugin.json", {
    name: "praxis-next",
    version: "0.1.0",
    description: "Praxis Next Codex 薄适配器",
    commands: ["/praxis-help", "/praxis-check", "/praxis-quick", "/praxis-start"]
  }],
  [".claude-plugin/plugin.json", {
    name: "praxis-next",
    version: "0.1.0",
    description: "Praxis Next Claude Code 薄适配器",
    commands: ["/praxis-help", "/praxis-check", "/praxis-quick", "/praxis-start"]
  }],
  [".claude-plugin/marketplace.json", {
    name: "Praxis Next",
    summary: "调用已安装 Praxis CLI 的薄平台适配器",
    locale: "zh-CN"
  }]
]);

let drift = false;
for (const [path, payload] of files) {
  const body = `${JSON.stringify(payload, null, 2)}\n`;
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
process.exit(drift ? 1 : 0);
