import { spawnSync } from "node:child_process";
const bin = process.env.PRAXIS_BIN || "praxis";
const result = spawnSync(bin, process.argv.slice(2), { stdio: "inherit" });
process.exit(result.status ?? 1);
