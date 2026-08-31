import { createHash } from "node:crypto";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { relative, resolve } from "node:path";

const ROOT = resolve(import.meta.dir, "../..");
const EXP = resolve(ROOT, ".praxis/experiments/runtime-v2-rust");
const SPIKE = resolve(EXP, "spike.json");
const STATE = resolve(EXP, "state.json");
const TASKS = resolve(EXP, "tasks.json");
const LOCK = resolve(EXP, "bootstrap-lock.json");

function die(message: string, code = 1): never {
  console.error(`ERROR: ${message}`);
  process.exit(code);
}
function load(path: string): any {
  if (!existsSync(path)) die(`missing ${relative(ROOT, path)}`);
  return JSON.parse(readFileSync(path, "utf8"));
}
function save(path: string, value: any): void {
  writeFileSync(path, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}
function run(cmd: string[], allowFailure = false): { code: number; out: string; err: string } {
  const r = Bun.spawnSync({ cmd, cwd: ROOT, stdout: "pipe", stderr: "pipe" });
  const out = r.stdout.toString();
  const err = r.stderr.toString();
  if (!allowFailure && r.exitCode !== 0) {
    if (out) process.stdout.write(out);
    if (err) process.stderr.write(err);
    die(`command failed (${r.exitCode}): ${cmd.join(" ")}`);
  }
  return { code: r.exitCode, out, err };
}
function sha256(path: string): string {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}
function match(pattern: string, path: string): boolean {
  return new Bun.Glob(pattern).match(path);
}
function matchesAny(patterns: string[], path: string): boolean {
  return patterns.some((p) => match(p, path));
}
function currentTask(state: any, tasks: any): any | null {
  return tasks.tasks.find((t: any) => t.id === state.active_task) ?? null;
}
function status(): void {
  const spike = load(SPIKE);
  const state = load(STATE);
  console.log(JSON.stringify({
    experiment: spike.id,
    question: spike.question,
    reference: spike.reference,
    branch: spike.branch,
    status: state.status,
    phase: state.phase,
    active_task: state.active_task,
    decision: state.decision,
    hard_gates: state.hard_gates,
    next_legal_actions: state.next_legal_actions,
    blockers: state.blockers,
  }, null, 2));
}
function brief(): void {
  const spike = load(SPIKE);
  const state = load(STATE);
  const tasks = load(TASKS);
  const task = currentTask(state, tasks);
  console.log(JSON.stringify({
    experiment: { id: spike.id, question: spike.question, branch: spike.branch, timebox: spike.timebox },
    reference: spike.reference,
    current: { status: state.status, phase: state.phase, active_task: state.active_task, decision: state.decision },
    task,
    hard_gates: state.hard_gates,
    permanent_allowed_paths: spike.permanent_allowed_paths,
    forbidden_reference_paths: spike.forbidden_reference_paths,
    protected_after_bootstrap: spike.protected_after_bootstrap,
    next_legal_actions: state.next_legal_actions,
  }, null, 2));
}
function changedFiles(ref: string): string[] {
  const committed = run(["git", "diff", "--name-only", `${ref}...HEAD`], true).out.split(/\r?\n/).filter(Boolean);
  const statusOut = run(["git", "status", "--porcelain=v1", "--untracked-files=all"], true).out;
  const working: string[] = [];
  for (const line of statusOut.split(/\r?\n/)) {
    if (!line) continue;
    const raw = line.slice(3).trim();
    const p = raw.includes(" -> ") ? (raw.split(" -> ").at(-1) ?? raw) : raw;
    working.push(p.replace(/^"|"$/g, ""));
  }
  return [...new Set([...committed, ...working])].sort();
}
function guard(): void {
  const spike = load(SPIKE);
  const state = load(STATE);
  const tasks = load(TASKS);
  const lock = load(LOCK);
  const branch = run(["git", "branch", "--show-current"]).out.trim();
  if (branch !== spike.branch) die(`wrong branch: ${branch}; expected ${spike.branch}`);

  for (const [rel, expected] of Object.entries(lock.protected_files as Record<string, string>)) {
    const path = resolve(ROOT, rel);
    if (!existsSync(path)) die(`CONTROL_PLANE_DRIFT missing protected file: ${rel}`, 2);
    const actual = sha256(path);
    if (actual !== expected) die(`CONTROL_PLANE_DRIFT ${rel}\nexpected ${expected}\nactual   ${actual}`, 2);
  }

  const task = currentTask(state, tasks);
  const dynamicAllowed = task?.allowed_paths ?? [];
  const allowed = [...spike.permanent_allowed_paths, ...dynamicAllowed];
  const files = changedFiles(spike.reference.commit);
  const violations: string[] = [];
  for (const file of files) {
    if (matchesAny(spike.forbidden_reference_paths, file)) violations.push(`${file} (reference forbidden)`);
    else if (!matchesAny(allowed, file)) violations.push(`${file} (outside spike scope)`);
  }
  if (violations.length) die(`SCOPE_VIOLATION\n${violations.join("\n")}`, 3);
  console.log(`PASS spike:guard (${files.length} changed paths relative to reference; no violations)`);
}
function verify(): void {
  guard();
  const state = load(STATE);
  if (state.phase === "BOOTSTRAP_REVIEW") {
    for (const path of [
      SPIKE,
      STATE,
      TASKS,
      LOCK,
      resolve(ROOT, "docs/spikes/runtime-v2-rust/00-charter.md"),
      resolve(ROOT, "docs/decisions/ADR-0014-runtime-v2-core-language.md"),
    ]) {
      if (!existsSync(path)) die(`bootstrap verification missing ${relative(ROOT, path)}`);
    }
    const adr = readFileSync(resolve(ROOT, "docs/decisions/ADR-0014-runtime-v2-core-language.md"), "utf8");
    if (!adr.includes("Status: Proposed") || !adr.includes("Decision: PENDING")) die("ADR bootstrap state is not Proposed/PENDING");
    console.log("PASS spike:verify bootstrap prepared; HUMAN BOOTSTRAP REVIEW REQUIRED");
    return;
  }

  const fmt = run(["cargo", "fmt", "--manifest-path", "spikes/runtime-v2-rust/Cargo.toml", "--", "--check"], true);
  if (fmt.code !== 0) die("cargo fmt --check failed", 4);
  const cargo = run(["cargo", "test", "--manifest-path", "spikes/runtime-v2-rust/Cargo.toml", "--workspace"], true);
  if (cargo.code !== 0) die("cargo test failed", 4);
  console.log(`PASS spike:verify phase=${state.phase}; task-specific evidence still governs advancement`);
}
function requireHumanApprovedFlag(): void {
  if (!process.argv.includes("--human-approved")) die("this transition requires explicit --human-approved", 5);
}
function start(): void {
  requireHumanApprovedFlag();
  guard();
  const state = load(STATE);
  if (state.phase !== "BOOTSTRAP_REVIEW") die(`cannot start from phase ${state.phase}`);
  const dirty = run(["git", "status", "--porcelain"], true).out.trim();
  if (dirty) die("bootstrap must be committed and worktree clean before spike:start", 5);
  state.status = "RUNNING";
  state.phase = "DAY_1_CONFORMANCE";
  state.active_task = "RS-D1-CONFORMANCE";
  state.timebox.started_at = new Date().toISOString();
  state.timebox.working_day = 1;
  state.next_legal_actions = ["execute RS-D1-CONFORMANCE", "run mise run spike:guard", "run mise run spike:verify"];
  state.last_updated_at = new Date().toISOString();
  save(STATE, state);
  console.log("SPIKE_STARTED: active_task=RS-D1-CONFORMANCE");
}
function complete(): void {
  const taskId = process.argv[3];
  if (!taskId) die("usage: ... complete <task-id>");
  guard();
  verify();
  const state = load(STATE);
  const tasks = load(TASKS);
  if (state.active_task !== taskId) die(`active task is ${state.active_task}, not ${taskId}`);
  const order = tasks.tasks.map((t: any) => t.id);
  const idx = order.indexOf(taskId);
  if (idx < 0) die(`unknown task ${taskId}`);

  if (taskId === "RS-D1-CONFORMANCE") {
    const p = resolve(ROOT, "spikes/runtime-v2-rust/reports/conformance.json");
    if (!existsSync(p)) die("missing conformance.json");
    const r = load(p);
    if (r?.ts_reference?.pass_ratio !== 1) die("TS reference conformance pass_ratio must be 1.0 before Day 2");
  }
  if (taskId === "RS-D2-KERNEL") {
    const r = load(resolve(ROOT, "spikes/runtime-v2-rust/reports/conformance.json"));
    if (r?.rust?.pass_ratio !== 1) die("Rust conformance pass_ratio must be 1.0");
    state.hard_gates.G1_SEMANTIC_PARITY = "PASS";
  }
  if (taskId === "RS-D3-PERSISTENCE") {
    const c = load(resolve(ROOT, "spikes/runtime-v2-rust/reports/compatibility.json"));
    const f = load(resolve(ROOT, "spikes/runtime-v2-rust/reports/failure-parity.json"));
    if (c?.event_json !== "PASS" || c?.sqlite_fixture !== "PASS") die("G2 compatibility report not PASS");
    if (f?.all_required_cases !== "PASS") die("G3 failure parity report not PASS");
    state.hard_gates.G2_V1_DATA_COMPATIBILITY = "PASS";
    state.hard_gates.G3_FAILURE_PARITY = "PASS";
  }
  if (taskId === "RS-D4-BOUNDARY-BENCH") {
    if (!existsSync(resolve(ROOT, "spikes/runtime-v2-rust/reports/benchmark.json"))) die("missing benchmark.json");
  }
  if (taskId === "RS-D5-DECISION") die("use spike:finalize for Day 5");

  const next = order[idx + 1];
  if (!next) die("no next task; use finalize");
  state.active_task = next;
  state.phase = `DAY_${idx + 2}_${next.replace(/^RS-D\d+-/, "")}`;
  state.timebox.working_day = idx + 2;
  state.next_legal_actions = [`execute ${next}`, "run mise run spike:guard", "run mise run spike:verify"];
  state.last_updated_at = new Date().toISOString();
  save(STATE, state);
  console.log(`TASK_COMPLETED: ${taskId}; next=${next}`);
}
function humanGate(): void {
  requireHumanApprovedFlag();
  const args = process.argv.slice(3).filter((v) => v !== "--human-approved");
  const gate = args[0];
  const result = args[1];
  const approvedBy = args[2];
  if (!["G4_AUTHORITY_CLARITY", "G5_BOUNDARY_COST"].includes(gate)) die("only G4/G5 may be recorded by humanGate");
  if (!["PASS", "FAIL"].includes(result)) die("result must be PASS or FAIL");
  if (!approvedBy) die("approved-by name is required");
  const state = load(STATE);
  state.hard_gates[gate] = result;
  state.human_gate_reviews ??= [];
  state.human_gate_reviews.push({ gate, result, approved_by: approvedBy, at: new Date().toISOString() });
  state.last_updated_at = new Date().toISOString();
  save(STATE, state);
  console.log(`HUMAN_GATE_RECORDED ${gate}=${result} by ${approvedBy}`);
}
function finalize(): void {
  guard();
  const state = load(STATE);
  const required = [
    "spikes/runtime-v2-rust/reports/conformance.json",
    "spikes/runtime-v2-rust/reports/compatibility.json",
    "spikes/runtime-v2-rust/reports/failure-parity.json",
    "spikes/runtime-v2-rust/reports/benchmark.json",
    "docs/spikes/runtime-v2-rust/final-report.md",
    "docs/decisions/ADR-0014-runtime-v2-core-language.md",
  ];
  for (const p of required) if (!existsSync(resolve(ROOT, p))) die(`finalization missing ${p}`);
  const unresolved = Object.entries(state.hard_gates).filter(([, v]) => !["PASS", "FAIL"].includes(String(v)));
  if (unresolved.length) die(`hard gates still unresolved: ${unresolved.map(([k]) => k).join(", ")}`);
  const adr = readFileSync(resolve(ROOT, "docs/decisions/ADR-0014-runtime-v2-core-language.md"), "utf8");
  if (!adr.includes("Status: Proposed")) die("ADR must remain Proposed until human acceptance");
  const allowed = ["KEEP_TS_CORE", "MIGRATE_DETERMINISTIC_CORE_TO_RUST"];
  const decision = allowed.find((d) => adr.includes(`Decision: ${d}`));
  if (!decision) die("ADR Decision must be one allowed enum before finalize");
  if (adr.includes("Status: Accepted")) die("executing AI may not accept ADR");
  const anyFail = Object.values(state.hard_gates).includes("FAIL");
  if (anyFail && decision !== "KEEP_TS_CORE") die("any hard-gate failure forces KEEP_TS_CORE recommendation");
  state.status = "DECISION_READY";
  state.phase = "HUMAN_ADR_REVIEW";
  state.active_task = null;
  state.decision = decision;
  state.next_legal_actions = ["human review final report", "human accept or reject ADR-0014"];
  state.last_updated_at = new Date().toISOString();
  save(STATE, state);
  console.log(`FINALIZATION_READY recommendation=${decision}; HUMAN ADR DECISION REQUIRED`);
}

const cmd = process.argv[2] ?? "status";
if (cmd === "status") status();
else if (cmd === "brief") brief();
else if (cmd === "guard") guard();
else if (cmd === "verify") verify();
else if (cmd === "start") start();
else if (cmd === "complete") complete();
else if (cmd === "human-gate") humanGate();
else if (cmd === "finalize") finalize();
else die(`unknown command: ${cmd}`);
