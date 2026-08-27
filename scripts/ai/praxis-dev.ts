import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, relative, resolve } from "node:path";
import { YAML } from "bun";

const ROOT = resolve(import.meta.dir, "../..");
const PRAXIS = resolve(ROOT, ".praxis");

type PlainObject = Record<string, unknown>;

type DevState =
  | "IDLE"
  | "DISCOVERING"
  | "PLAN_READY"
  | "IMPLEMENTING"
  | "VERIFYING"
  | "ACCEPTANCE_READY"
  | "REWORK"
  | "ACCEPTED";

function die(message: string, code = 1): never {
  console.error(`ERROR: ${message}`);
  process.exit(code);
}

function isObject(value: unknown): value is PlainObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function loadYaml(path: string): PlainObject {
  if (!existsSync(path)) die(`missing file: ${relative(ROOT, path)}`);
  const parsed = YAML.parse(readFileSync(path, "utf8"));
  if (!isObject(parsed)) die(`expected object YAML: ${relative(ROOT, path)}`);
  return parsed;
}

function saveYaml(path: string, value: PlainObject): void {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, YAML.stringify(value, null, 2), "utf8");
}

function loadProject(): PlainObject {
  return loadYaml(resolve(PRAXIS, "project.yaml"));
}

function loadState(): PlainObject {
  return loadYaml(resolve(PRAXIS, "state.yaml"));
}

function saveState(state: PlainObject): void {
  saveYaml(resolve(PRAXIS, "state.yaml"), state);
}

function currentMilestone(state: PlainObject): string {
  const value = state.current_milestone;
  if (typeof value !== "string") die("state.current_milestone must be a string");
  return value;
}

function activeTaskId(state: PlainObject): string | null {
  const value = state.active_task;
  if (value === null || value === undefined) return null;
  if (typeof value !== "string") die("state.active_task must be string|null");
  return value;
}

function taskFiles(): string[] {
  const glob = new Bun.Glob("*.yaml");
  return [...glob.scanSync({ cwd: resolve(PRAXIS, "tasks"), absolute: true })].filter(
    (path) => !path.endsWith("TEMPLATE.yaml"),
  );
}

function loadTaskById(id: string): { path: string; value: PlainObject } {
  for (const path of taskFiles()) {
    const task = loadYaml(path);
    if (task.id === id) return { path, value: task };
  }
  die(`active task '${id}' has no Task Contract in .praxis/tasks`);
}

function loadTaskPath(pathArg: string): { path: string; value: PlainObject } {
  const path = resolve(ROOT, pathArg);
  return { path, value: loadYaml(path) };
}

function run(command: readonly string[], allowFailure = false): string {
  const result = Bun.spawnSync({
    cmd: [...command],
    cwd: ROOT,
    stdout: "pipe",
    stderr: "pipe",
  });
  const stdout = result.stdout.toString();
  const stderr = result.stderr.toString();
  if (!allowFailure && result.exitCode !== 0) {
    if (stdout) process.stdout.write(stdout);
    if (stderr) process.stderr.write(stderr);
    die(`command failed (${result.exitCode}): ${command.join(" ")}`);
  }
  return stdout;
}

function gitChangedFiles(): string[] {
  const output = run(["git", "status", "--porcelain=v1", "--untracked-files=all"], true);
  if (!output.trim()) return [];
  const files: string[] = [];
  for (const line of output.split("\n")) {
    if (!line.trim()) continue;
    const raw = line.slice(3).trim();
    const finalName = raw.includes(" -> ") ? raw.split(" -> ").at(-1)! : raw;
    files.push(finalName.replace(/^"|"$/g, ""));
  }
  return [...new Set(files)].sort();
}

function globMatches(pattern: string, path: string): boolean {
  return new Bun.Glob(pattern).match(path);
}

function matchesAny(patterns: readonly string[], path: string): boolean {
  return patterns.some((pattern) => globMatches(pattern, path));
}

function stringArray(value: unknown, label: string): string[] {
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string")) {
    die(`${label} must be string[]`);
  }
  return value as string[];
}

function scopeFromTask(task: PlainObject): { allowed: string[]; forbidden: string[] } {
  if (!isObject(task.scope)) die("task.scope must be an object");
  return {
    allowed: stringArray(task.scope.allowed_paths, "task.scope.allowed_paths"),
    forbidden: stringArray(task.scope.forbidden_paths, "task.scope.forbidden_paths"),
  };
}

function validateTask(task: PlainObject, state: PlainObject): void {
  for (const key of ["id", "title", "milestone", "status", "objective", "falsified_if"]) {
    if (typeof task[key] !== "string" || !(task[key] as string).trim()) {
      die(`task.${key} must be a non-empty string`);
    }
  }
  if (task.milestone !== currentMilestone(state)) {
    die(`task milestone ${String(task.milestone)} != current milestone ${currentMilestone(state)}`);
  }
  const scope = scopeFromTask(task);
  if (scope.allowed.length === 0) die("Task Contract must declare allowed_paths");
  stringArray(task.required_gates ?? [], "task.required_gates");
}

function printStatus(): void {
  const state = loadState();
  const project = loadProject();
  const payload = {
    project: project.project,
    release_line: project.release_line,
    current_milestone: state.current_milestone,
    last_accepted_milestone: state.last_accepted_milestone,
    active_task: state.active_task,
    development_state: state.development_state,
    blockers: state.blockers ?? [],
    next_legal_actions: state.next_legal_actions ?? [],
  };
  console.log(YAML.stringify(payload, null, 2));
}

function printBrief(): void {
  const state = loadState();
  const project = loadProject();
  const architecture = loadYaml(resolve(PRAXIS, "architecture.yaml"));
  const taskId = activeTaskId(state);
  const task = taskId ? loadTaskById(taskId).value : null;
  const payload = {
    project: project.project,
    goal: project.goal,
    v1_outcomes: project.v1_outcomes,
    non_goals: project.non_goals,
    core_invariants: project.core_invariants,
    current_milestone: state.current_milestone,
    development_state: state.development_state,
    blockers: state.blockers ?? [],
    active_task: task,
    architecture: {
      packages: architecture.packages,
      adr_required_for: architecture.adr_required_for,
    },
    git_changed_files: gitChangedFiles(),
  };
  console.log(YAML.stringify(payload, null, 2));
}

function planTask(pathArg: string | undefined): void {
  if (!pathArg) die("plan requires a Task Contract path");
  const state = loadState();
  if (activeTaskId(state)) die("an active task already exists; accept/rework/handoff it first");
  const { path, value: task } = loadTaskPath(pathArg);
  validateTask(task, state);
  task.status = "plan_ready";
  saveYaml(path, task);
  state.active_task = task.id;
  state.development_state = "PLAN_READY" satisfies DevState;
  state.next_legal_actions = [
    "implement only within Task Contract scope",
    "run ai:guard",
    "run ai:verify",
  ];
  saveState(state);
  console.log(`PLAN_READY ${String(task.id)}`);
}

function guard(): void {
  const state = loadState();
  const id = activeTaskId(state);
  if (!id) die("ai:guard requires an active task");
  const task = loadTaskById(id).value;
  validateTask(task, state);
  const scope = scopeFromTask(task);
  const changed = gitChangedFiles();
  const violations: string[] = [];
  for (const file of changed) {
    if (matchesAny(scope.forbidden, file)) violations.push(`${file}: matches forbidden_paths`);
    if (!matchesAny(scope.allowed, file)) violations.push(`${file}: outside allowed_paths`);
  }
  if (violations.length) {
    console.error(violations.map((item) => `- ${item}`).join("\n"));
    die("scope guard failed");
  }
  architectureGuard(changed);
  console.log(`GUARD_PASS ${changed.length} changed file(s)`);
}

function packageNameMap(): Map<string, string> {
  const result = new Map<string, string>();
  for (const top of ["packages", "apps"]) {
    const glob = new Bun.Glob(`${top}/*/package.json`);
    for (const manifest of glob.scanSync({ cwd: ROOT, absolute: true })) {
      const json = JSON.parse(readFileSync(manifest, "utf8")) as PlainObject;
      if (typeof json.name !== "string") continue;
      const id = manifest.split("/").at(-2)!;
      result.set(json.name, id);
    }
  }
  return result;
}

function architectureGuard(changed: readonly string[]): void {
  const architecture = loadYaml(resolve(PRAXIS, "architecture.yaml"));
  if (!isObject(architecture.packages)) die("architecture.packages must be object");
  const packageNames = packageNameMap();
  const violations: string[] = [];
  for (const file of changed.filter((item) =>
    /^(packages|apps)\/[^/]+\/package\.json$/.test(item),
  )) {
    const manifest = JSON.parse(readFileSync(resolve(ROOT, file), "utf8")) as PlainObject;
    const pkgId = file.split("/")[1]!;
    const rules = architecture.packages[pkgId];
    if (!isObject(rules)) continue;
    const allowed = new Set(
      stringArray(rules.may_depend_on ?? [], `architecture.packages.${pkgId}.may_depend_on`),
    );
    const deps = {
      ...(isObject(manifest.dependencies) ? manifest.dependencies : {}),
      ...(isObject(manifest.devDependencies) ? manifest.devDependencies : {}),
    };
    for (const depName of Object.keys(deps)) {
      const depId = packageNames.get(depName);
      if (depId && !allowed.has(depId)) {
        violations.push(
          `${file}: ${pkgId} may not depend on workspace package ${depId} (${depName})`,
        );
      }
    }
  }
  if (violations.length) {
    console.error(violations.map((item) => `- ${item}`).join("\n"));
    die("architecture guard failed");
  }
}

function requiredGates(task: PlainObject, changed: readonly string[]): string[] {
  const config = loadYaml(resolve(PRAXIS, "quality-gates.yaml"));
  const gates = isObject(config.gates) ? config.gates : die("quality-gates.gates must be object");
  const selected = new Set(stringArray(task.required_gates ?? [], "task.required_gates"));
  if (!Array.isArray(config.rules)) die("quality-gates.rules must be array");
  for (const rawRule of config.rules) {
    if (!isObject(rawRule)) die("quality gate rule must be object");
    const patterns = stringArray(rawRule.match, "quality gate rule.match");
    if (changed.some((file) => matchesAny(patterns, file))) {
      for (const gate of stringArray(rawRule.require ?? [], "quality gate rule.require"))
        selected.add(gate);
    }
  }
  for (const gate of selected) {
    stringArray(gates[gate], `quality-gates.gates.${gate}`);
  }
  return [...selected].sort();
}

function verify(): void {
  const state = loadState();
  const id = activeTaskId(state);
  if (!id) die("ai:verify requires an active task");
  guard();
  const taskFile = loadTaskById(id);
  const task = taskFile.value;
  const changed = gitChangedFiles();
  const config = loadYaml(resolve(PRAXIS, "quality-gates.yaml"));
  if (!isObject(config.gates)) die("quality-gates.gates must be object");
  const gates = requiredGates(task, changed);
  state.development_state = "VERIFYING" satisfies DevState;
  saveState(state);
  const results: Array<{ gate: string; result: "PASS" | "FAIL" }> = [];
  for (const gate of gates) {
    const command = stringArray(config.gates[gate], `quality-gates.gates.${gate}`);
    process.stdout.write(`\n==> ${gate}: ${command.join(" ")}\n`);
    const result = Bun.spawnSync({ cmd: command, cwd: ROOT, stdout: "inherit", stderr: "inherit" });
    const status = result.exitCode === 0 ? "PASS" : "FAIL";
    results.push({ gate, result });
    if (status === "FAIL") break;
  }
  const pass = results.length === gates.length && results.every((item) => item.result === "PASS");
  state.last_verification = {
    task: id,
    at: new Date().toISOString(),
    result: pass ? "PASS" : "FAIL",
    gates: results,
  };
  state.development_state = pass
    ? ("ACCEPTANCE_READY" satisfies DevState)
    : ("REWORK" satisfies DevState);
  saveState(state);
  if (!pass) die("verification failed");
  console.log(`VERIFY_PASS ${id}`);
}

function accept(): void {
  const state = loadState();
  const id = activeTaskId(state);
  if (!id) die("ai:accept requires an active task");
  const taskFile = loadTaskById(id);
  const task = taskFile.value;
  if (
    !isObject(state.last_verification) ||
    state.last_verification.task !== id ||
    state.last_verification.result !== "PASS"
  ) {
    die("current task has no passing verification record");
  }
  const requiresHuman =
    task.requires_human_acceptance === true ||
    task.requires_adr === true ||
    task.risk_class === "D" ||
    task.risk_class === "E";
  if (requiresHuman) {
    task.status = "acceptance_ready";
    state.development_state = "ACCEPTANCE_READY" satisfies DevState;
    saveYaml(taskFile.path, task);
    saveState(state);
    console.log(`ACCEPTANCE_READY ${id} (independent/human acceptance required)`);
    return;
  }
  task.status = "accepted";
  saveYaml(taskFile.path, task);
  state.development_state = "ACCEPTED" satisfies DevState;
  state.active_task = null;
  state.next_legal_actions = ["generate handoff", "select next eligible task in current milestone"];
  saveState(state);
  console.log(`ACCEPTED ${id}`);
}

function handoff(): void {
  const state = loadState();
  const taskId =
    activeTaskId(state) ??
    (isObject(state.last_verification) && typeof state.last_verification.task === "string"
      ? state.last_verification.task
      : "session");
  const path = resolve(PRAXIS, "handoffs", `${taskId}-${Date.now()}.md`);
  const changed = gitChangedFiles();
  const body = `# Praxis Development Handoff\n\n- Task: ${taskId}\n- Milestone: ${currentMilestone(state)}\n- Development state: ${String(state.development_state)}\n- Generated: ${new Date().toISOString()}\n\n## Changed files\n\n${changed.length ? changed.map((file) => `- \`${file}\``).join("\n") : "- none"}\n\n## Last verification\n\n\`\`\`yaml\n${YAML.stringify(state.last_verification ?? null, null, 2)}\`\`\`\n\n## Blockers / risks\n\n\`\`\`yaml\n${YAML.stringify({ blockers: state.blockers ?? [], known_risks: state.known_risks ?? [] }, null, 2)}\`\`\`\n\n## Next legal actions\n\n${Array.isArray(state.next_legal_actions) ? state.next_legal_actions.map((item) => `- ${String(item)}`).join("\n") : "- inspect project state"}\n`;
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, body, "utf8");
  console.log(relative(ROOT, path));
}

const command = process.argv[2];
switch (command) {
  case "status":
    printStatus();
    break;
  case "brief":
    printBrief();
    break;
  case "plan":
    planTask(process.argv[3]);
    break;
  case "guard":
    guard();
    break;
  case "verify":
    verify();
    break;
  case "accept":
    accept();
    break;
  case "handoff":
    handoff();
    break;
  default:
    die("usage: praxis-dev <status|brief|plan <task.yaml>|guard|verify|accept|handoff>", 2);
}
