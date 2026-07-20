import { spawnSync } from "node:child_process";

const binary = process.env.PRAXIS_BIN || "praxis";
const result = spawnSync(binary, process.argv.slice(2), { stdio: "inherit" });
process.exit(result.status ?? 1);
