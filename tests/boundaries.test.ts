import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test } from "vitest";

/**
 * Repo-level dependency boundary tests (ADR-0002, docs/01 §4).
 *
 * contracts        -> no workspace dependencies
 * core             -> contracts only
 * adapters         -> contracts only, never each other, never core
 * testkit          -> contracts + core, never a production dependency of others
 * apps/cli         -> composition root, may depend on any workspace package
 */

type Manifest = {
  name: string;
  dependencies?: Readonly<Record<string, string>>;
  devDependencies?: Readonly<Record<string, string>>;
};

const repoRoot = fileURLToPath(new URL("..", import.meta.url));

const workspaceDirs = [
  "apps/cli",
  "packages/contracts",
  "packages/core",
  "packages/store-sqlite",
  "packages/provider-openai",
  "packages/tools-local",
  "packages/testkit",
] as const;

const adapters = [
  "packages/store-sqlite",
  "packages/provider-openai",
  "packages/tools-local",
] as const;

const workspaceNames = new Set<string>([
  "@praxis/cli",
  "@praxis/contracts",
  "@praxis/core",
  "@praxis/store-sqlite",
  "@praxis/provider-openai",
  "@praxis/tools-local",
  "@praxis/testkit",
]);

function readManifest(dir: string): Manifest {
  const parsed: unknown = JSON.parse(readFileSync(`${repoRoot}${dir}/package.json`, "utf8"));
  if (typeof parsed !== "object" || parsed === null || !("name" in parsed)) {
    throw new Error(`invalid manifest: ${dir}/package.json`);
  }
  return parsed as Manifest;
}

function workspaceDeps(manifest: Manifest): string[] {
  return Object.keys(manifest.dependencies ?? {}).filter((dep) => workspaceNames.has(dep));
}

const manifests = new Map<string, Manifest>(workspaceDirs.map((dir) => [dir, readManifest(dir)]));

test("every workspace manifest is present and named as expected", () => {
  for (const dir of workspaceDirs) {
    const manifest = manifests.get(dir);
    expect(manifest, `${dir}/package.json is readable`).toBeDefined();
    expect(manifest?.name).toMatch(/^@praxis\//);
  }
});

test("contracts has no workspace dependencies", () => {
  expect(workspaceDeps(manifests.get("packages/contracts") ?? failManifest())).toEqual([]);
});

test("core depends only on contracts", () => {
  expect(workspaceDeps(manifests.get("packages/core") ?? failManifest())).toEqual([
    "@praxis/contracts",
  ]);
});

test("adapters depend only on contracts and never on each other or core", () => {
  for (const dir of adapters) {
    expect(workspaceDeps(manifests.get(dir) ?? failManifest()), dir).toEqual(["@praxis/contracts"]);
  }
});

test("testkit depends only on contracts and core", () => {
  expect(workspaceDeps(manifests.get("packages/testkit") ?? failManifest())).toEqual([
    "@praxis/contracts",
    "@praxis/core",
  ]);
});

test("testkit is never a production dependency of any other package", () => {
  for (const dir of workspaceDirs) {
    if (dir === "packages/testkit") {
      continue;
    }
    const deps = manifests.get(dir)?.dependencies ?? {};
    expect(deps["@praxis/testkit"], dir).toBeUndefined();
  }
});

test("apps/cli (composition root) may depend on any workspace package", () => {
  for (const dep of workspaceDeps(manifests.get("apps/cli") ?? failManifest())) {
    expect(workspaceNames.has(dep)).toBe(true);
  }
});

const exactVersion = /^\d+\.\d+\.\d+$/;

test("all dependencies across every manifest use exact pinned versions", () => {
  const targets: ReadonlyArray<readonly [string, Manifest]> = [
    ["", readManifest("")], // repository root
    ...workspaceDirs.map((dir): readonly [string, Manifest] => [dir, readManifest(dir)]),
  ];
  for (const [dir, manifest] of targets) {
    for (const [field, deps] of [
      ["dependencies", manifest.dependencies],
      ["devDependencies", manifest.devDependencies],
    ] as const) {
      for (const [name, version] of Object.entries(deps ?? {})) {
        expect(version, `${dir || "root"} ${field} ${name}`).toMatch(exactVersion);
      }
    }
  }
});

function failManifest(): Manifest {
  throw new Error("manifest missing from test fixtures");
}
