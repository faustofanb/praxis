import { spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, expect, test } from "vitest";

/**
 * Integration tests for the AI development controller (scripts/ai/praxis-dev.ts).
 *
 * Each test drives the real script as a subprocess against an isolated fixture
 * repository (git repo + .praxis/ control-plane files), via the PRAXIS_ROOT
 * override. Gates are stubbed with trivial bun -e commands so verify behavior
 * is observable without running the repository quality chain.
 */

const repoRoot = fileURLToPath(new URL("..", import.meta.url));
const controllerScript = join(repoRoot, "scripts", "ai", "praxis-dev.ts");
const taskSchema = readFileSync(join(repoRoot, ".praxis", "schemas", "task.schema.json"), "utf8");

let root: string;

function write(relativePath: string, content: string): void {
  const absolute = join(root, relativePath);
  mkdirSync(dirname(absolute), { recursive: true });
  writeFileSync(absolute, content, "utf8");
}

function git(args: readonly string[]): void {
  const result = spawnSync("git", args, { cwd: root, encoding: "utf8" });
  expect(result.status, `git ${args.join(" ")} failed: ${result.stderr}`).toBe(0);
}

function praxisDev(args: readonly string[]): {
  status: number | null;
  stdout: string;
  stderr: string;
} {
  const result = spawnSync("bun", [controllerScript, ...args], {
    env: { ...process.env, PRAXIS_ROOT: root },
    encoding: "utf8",
  });
  return { status: result.status, stdout: result.stdout, stderr: result.stderr };
}

function stateContent(): string {
  return readFileSync(join(root, ".praxis", "state.yaml"), "utf8");
}

function taskContent(id: string): string {
  return readFileSync(join(root, ".praxis", "tasks", `${id}.yaml`), "utf8");
}

function contract(fields: {
  id?: string;
  riskClass?: string;
  objective?: string;
  requiredGates?: string;
  withScope?: boolean;
}): string {
  const id = fields.id ?? "M0-T001";
  const scope =
    fields.withScope === false
      ? ""
      : `scope:
  allowed_paths:
  - .praxis/tasks/${id}.yaml
  - .praxis/state.yaml
  - allowed/**
  forbidden_paths:
  - forbidden/**
`;
  return `schema_version: 1
id: ${id}
title: fixture task
milestone: M0
status: planned
risk_class: ${fields.riskClass ?? "B"}
objective: ${fields.objective ?? "a sufficiently long fixture objective for schema validation"}
evidence:
  observed: []
  expected: []
  references: []
hypothesis: fixture hypothesis
${scope}architecture_refs: []
required_gates:
- ${fields.requiredGates ?? "pass"}
acceptance:
  scenarios: []
  failure_cases: []
  artifacts: []
falsified_if: a sufficiently long falsification statement for the fixture task
requires_adr: false
requires_human_acceptance: false
`;
}

beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "praxis-dev-test-"));
  git(["init", "-q"]);
  write(
    ".praxis/state.yaml",
    `schema_version: 1
current_milestone: M0
last_accepted_milestone: null
active_task: null
development_state: IDLE
blockers: []
open_adrs: []
known_risks: []
next_legal_actions: []
`,
  );
  write(
    ".praxis/project.yaml",
    `schema_version: 1
project: praxis-fixture
release_line: v1
`,
  );
  write(
    ".praxis/architecture.yaml",
    `schema_version: 1
packages: {}
`,
  );
  write(
    ".praxis/quality-gates.yaml",
    `schema_version: 1
gates:
  pass:
  - bun
  - -e
  - "0"
  fail:
  - bun
  - -e
  - "process.exit(1)"
rules:
- id: baseline
  match:
  - '**/*'
  require:
  - pass
`,
  );
  write(".praxis/schemas/task.schema.json", taskSchema);
  // Commit the fixture control plane so git status only reports per-test
  // changes, mirroring a real repository where .praxis files are tracked.
  git(["config", "user.email", "fixture@example.com"]);
  git(["config", "user.name", "praxis-fixture"]);
  git(["add", ".praxis"]);
  git(["commit", "-q", "-m", "fixture control plane baseline"]);
});

test("plan activates a valid Task Contract", () => {
  write(".praxis/tasks/M0-T001.yaml", contract({}));
  const result = praxisDev(["plan", ".praxis/tasks/M0-T001.yaml"]);
  expect(result.stderr).toBe("");
  expect(result.status).toBe(0);
  expect(result.stdout).toContain("PLAN_READY M0-T001");
  expect(stateContent()).toContain("active_task: M0-T001");
  expect(stateContent()).toContain("development_state: PLAN_READY");
  expect(taskContent("M0-T001")).toContain("status: plan_ready");
});

test("plan rejects Task Contracts that violate the task schema", () => {
  const invalid: ReadonlyArray<{ name: string; contractYaml: string; message: string }> = [
    {
      name: "bad id pattern",
      contractYaml: contract({ id: "M0-T1" }),
      message: "must match",
    },
    {
      name: "bad risk class",
      contractYaml: contract({ id: "M0-T002", riskClass: "F" }),
      message: "must be one of",
    },
    {
      name: "objective below minLength",
      contractYaml: contract({ id: "M0-T003", objective: "short" }),
      message: "non-whitespace characters",
    },
    {
      name: "missing scope",
      contractYaml: contract({ id: "M0-T004", withScope: false }),
      message: "required by task schema",
    },
  ];
  for (const entry of invalid) {
    write(`.praxis/tasks/${entry.name.replace(/\s+/g, "-")}.yaml`, entry.contractYaml);
    const result = praxisDev(["plan", `.praxis/tasks/${entry.name.replace(/\s+/g, "-")}.yaml`]);
    expect(result.status, entry.name).toBe(1);
    expect(result.stderr, entry.name).toContain(entry.message);
    expect(stateContent(), entry.name).toContain("development_state: IDLE");
  }
});

test("plan refuses to start while another task is active", () => {
  write(".praxis/tasks/M0-T001.yaml", contract({}));
  write(".praxis/tasks/M0-T002.yaml", contract({ id: "M0-T002" }));
  expect(praxisDev(["plan", ".praxis/tasks/M0-T001.yaml"]).status).toBe(0);
  const second = praxisDev(["plan", ".praxis/tasks/M0-T002.yaml"]);
  expect(second.status).toBe(1);
  expect(second.stderr).toContain("active task already exists");
});

test("guard fails when a change falls outside allowed_paths", () => {
  write(".praxis/tasks/M0-T001.yaml", contract({}));
  praxisDev(["plan", ".praxis/tasks/M0-T001.yaml"]);
  write("stray.txt", "outside the task contract scope");
  const result = praxisDev(["guard"]);
  expect(result.status).toBe(1);
  expect(result.stderr).toContain("stray.txt: outside allowed_paths");
});

test("guard fails when a change matches forbidden_paths", () => {
  write(".praxis/tasks/M0-T001.yaml", contract({}));
  praxisDev(["plan", ".praxis/tasks/M0-T001.yaml"]);
  mkdirSync(join(root, "forbidden"), { recursive: true });
  write("forbidden/secret.txt", "explicitly forbidden");
  const result = praxisDev(["guard"]);
  expect(result.status).toBe(1);
  expect(result.stderr).toContain("forbidden/secret.txt: matches forbidden_paths");
});

test("guard passes when all changes are in scope", () => {
  write(".praxis/tasks/M0-T001.yaml", contract({}));
  praxisDev(["plan", ".praxis/tasks/M0-T001.yaml"]);
  write("allowed/note.txt", "inside the task contract scope");
  const result = praxisDev(["guard"]);
  expect(result.status).toBe(0);
  expect(result.stdout).toContain("GUARD_PASS");
});

test("verify records FAIL and moves state to REWORK when a gate fails", () => {
  write(".praxis/tasks/M0-T001.yaml", contract({ requiredGates: "fail" }));
  praxisDev(["plan", ".praxis/tasks/M0-T001.yaml"]);
  const result = praxisDev(["verify"]);
  expect(result.status).toBe(1);
  const state = stateContent();
  expect(state).toContain("development_state: REWORK");
  expect(state).toContain("result: FAIL");
});

test("verify passes and reaches ACCEPTANCE_READY", () => {
  write(".praxis/tasks/M0-T001.yaml", contract({}));
  praxisDev(["plan", ".praxis/tasks/M0-T001.yaml"]);
  const result = praxisDev(["verify"]);
  expect(result.stderr).toBe("");
  expect(result.status).toBe(0);
  expect(result.stdout).toContain("VERIFY_PASS M0-T001");
  expect(stateContent()).toContain("development_state: ACCEPTANCE_READY");
});

test("accept requires a passing verification record", () => {
  write(".praxis/tasks/M0-T001.yaml", contract({}));
  praxisDev(["plan", ".praxis/tasks/M0-T001.yaml"]);
  const result = praxisDev(["accept"]);
  expect(result.status).toBe(1);
  expect(result.stderr).toContain("no passing verification record");
});

test("accept routes class D tasks to independent or human acceptance", () => {
  write(".praxis/tasks/M0-T005.yaml", contract({ id: "M0-T005", riskClass: "D" }));
  praxisDev(["plan", ".praxis/tasks/M0-T005.yaml"]);
  praxisDev(["verify"]);
  const result = praxisDev(["accept"]);
  expect(result.status).toBe(0);
  expect(result.stdout).toContain("independent/human acceptance required");
  expect(taskContent("M0-T005")).toContain("status: acceptance_ready");
  expect(stateContent()).toContain("active_task: M0-T005");
});

test("accept auto-accepts low-risk tasks after verification", () => {
  write(".praxis/tasks/M0-T001.yaml", contract({}));
  praxisDev(["plan", ".praxis/tasks/M0-T001.yaml"]);
  praxisDev(["verify"]);
  const result = praxisDev(["accept"]);
  expect(result.status).toBe(0);
  expect(result.stdout).toContain("ACCEPTED M0-T001");
  const state = stateContent();
  expect(state).toContain("development_state: ACCEPTED");
  expect(state).not.toContain("active_task: M0-T001");
  expect(taskContent("M0-T001")).toContain("status: accepted");
});

test("handoff writes a handoff file for the finished task", () => {
  write(".praxis/tasks/M0-T001.yaml", contract({}));
  praxisDev(["plan", ".praxis/tasks/M0-T001.yaml"]);
  praxisDev(["verify"]);
  praxisDev(["accept"]);
  const result = praxisDev(["handoff"]);
  expect(result.status).toBe(0);
  const handoffs = readdirSync(join(root, ".praxis", "handoffs"));
  expect(handoffs).toHaveLength(1);
  expect(handoffs[0]).toMatch(/^M0-T001-\d+\.md$/);
  expect(readFileSync(join(root, ".praxis", "handoffs", handoffs[0] ?? ""), "utf8")).toContain(
    "M0-T001",
  );
});

test("handoff falls back to the last verified task when none is active", () => {
  write(".praxis/tasks/M0-T001.yaml", contract({}));
  praxisDev(["plan", ".praxis/tasks/M0-T001.yaml"]);
  praxisDev(["verify"]);
  const result = praxisDev(["handoff"]);
  expect(result.status).toBe(0);
  const handoffs = readdirSync(join(root, ".praxis", "handoffs"));
  expect(handoffs).toHaveLength(1);
});

afterEach(() => {
  rmSync(root, { recursive: true, force: true });
});
