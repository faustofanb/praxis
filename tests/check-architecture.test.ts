import { spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, expect, test } from "vitest";

/**
 * Failure-path tests for the architecture conformance checker
 * (scripts/ai/check-architecture.ts, docs/07 §3).
 *
 * Each test builds a minimal fixture workspace and drives the real script via
 * PRAXIS_ROOT. The real repository passing the checker is covered by the
 * test:architecture gate itself.
 */

const repoRoot = fileURLToPath(new URL("..", import.meta.url));
const checkerScript = join(repoRoot, "scripts", "ai", "check-architecture.ts");

const ARCHITECTURE_YAML = `schema_version: 1
packages:
  contracts:
    responsibility: fixture contracts
    may_depend_on: []
  core:
    responsibility: fixture core
    may_depend_on: [contracts]
  store-sqlite:
    responsibility: fixture store adapter
    may_depend_on: [contracts]
tiers: {}
adr_required_for: []
`;

let root: string;

function write(relativePath: string, content: string): void {
  const absolute = join(root, relativePath);
  mkdirSync(dirname(absolute), { recursive: true });
  writeFileSync(absolute, content, "utf8");
}

function writePackage(id: string, manifestFields: Record<string, unknown> = {}): void {
  const name = id.startsWith("apps-") ? `@praxis/${id.slice(5)}` : `@praxis/${id}`;
  const dir = id.startsWith("apps-") ? `apps/${id.slice(5)}` : `packages/${id}`;
  write(
    join(dir, "package.json"),
    JSON.stringify({ name, version: "0.0.0", ...manifestFields }, null, 2),
  );
}

function checkArchitecture(): { status: number | null; stdout: string; stderr: string } {
  const result = spawnSync("bun", [checkerScript], {
    env: { ...process.env, PRAXIS_ROOT: root },
    encoding: "utf8",
  });
  return { status: result.status, stdout: result.stdout, stderr: result.stderr };
}

function baselineWorkspace(): void {
  write(".praxis/architecture.yaml", ARCHITECTURE_YAML);
  writePackage("contracts");
  write("packages/contracts/src/index.ts", 'export const contractsEntry = "contracts";\n');
  writePackage("core", { dependencies: { "@praxis/contracts": "0.0.0" } });
  write(
    "packages/core/src/index.ts",
    'import { contractsEntry } from "@praxis/contracts";\nexport const coreEntry = contractsEntry;\n',
  );
  writePackage("store-sqlite", { dependencies: { "@praxis/contracts": "0.0.0" } });
  write("packages/store-sqlite/src/index.ts", 'export const storeEntry = "store";\n');
}

beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "praxis-arch-test-"));
});

test("conforming workspace passes", () => {
  baselineWorkspace();
  const result = checkArchitecture();
  expect(result.stderr).toBe("");
  expect(result.status).toBe(0);
  expect(result.stdout).toContain("ARCHITECTURE_PASS");
});

test("core importing an adapter violates import direction", () => {
  baselineWorkspace();
  write(
    "packages/core/src/store-import.ts",
    'import { storeEntry } from "@praxis/store-sqlite";\nexport const uses = storeEntry;\n',
  );
  const result = checkArchitecture();
  expect(result.status).toBe(1);
  expect(result.stderr).toContain("import-direction: packages/core/src/store-import.ts");
  expect(result.stderr).toContain("core -> store-sqlite");
});

test("deep import into another package violates the public API rule", () => {
  baselineWorkspace();
  write(
    "packages/core/src/deep.ts",
    'import { contractsEntry } from "@praxis/contracts/src/internal";\nexport const uses = contractsEntry;\n',
  );
  const result = checkArchitecture();
  expect(result.status).toBe(1);
  expect(result.stderr).toContain("deep-import: packages/core/src/deep.ts");
});

test("manifest dependency against architecture direction fails", () => {
  baselineWorkspace();
  writePackage("contracts", { dependencies: { "@praxis/core": "0.0.0" } });
  const result = checkArchitecture();
  expect(result.status).toBe(1);
  expect(result.stderr).toContain("manifest-direction");
  expect(result.stderr).toContain("contracts -> core");
});

test("workspace package missing from architecture.yaml fails", () => {
  baselineWorkspace();
  writePackage("tools-local");
  write("packages/tools-local/src/index.ts", 'export const toolEntry = "tool";\n');
  const result = checkArchitecture();
  expect(result.status).toBe(1);
  expect(result.stderr).toContain("undeclared-package: tools-local");
});

test("undeclared third-party dependency in core fails", () => {
  baselineWorkspace();
  writePackage("core", {
    dependencies: { "@praxis/contracts": "0.0.0", lodash: "4.17.21" },
  });
  const result = checkArchitecture();
  expect(result.status).toBe(1);
  expect(result.stderr).toContain("core-third-party");
  expect(result.stderr).toContain("add_dependency_to_core");
});

test("mutually allowed imports are reported as a cycle", () => {
  write(
    ".praxis/architecture.yaml",
    `schema_version: 1
packages:
  contracts:
    responsibility: fixture contracts
    may_depend_on: [core]
  core:
    responsibility: fixture core
    may_depend_on: [contracts]
tiers: {}
adr_required_for: []
`,
  );
  writePackage("contracts");
  write(
    "packages/contracts/src/index.ts",
    'import { coreEntry } from "@praxis/core";\nexport const contractsEntry = coreEntry;\n',
  );
  writePackage("core");
  write(
    "packages/core/src/index.ts",
    'import { contractsEntry } from "@praxis/contracts";\nexport const coreEntry = contractsEntry;\n',
  );
  const result = checkArchitecture();
  expect(result.status).toBe(1);
  expect(result.stderr).toContain("cycle:");
});

afterEach(() => {
  rmSync(root, { recursive: true, force: true });
});
