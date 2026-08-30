import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "vitest";

/**
 * Dependency inventory drift guard (docs/09-dependency-inventory.md, M7-T004):
 * the inventory's machine-readable block must stay in lockstep with the
 * workspace manifests — nothing undeclared, nothing stale — and its license
 * facts must match the PINNED install (node_modules), so an upgrade that
 * changes a package's license field surfaces here. The admission law lives
 * in AGENTS.md; exact pins and dependency directions live in
 * tests/boundaries.test.ts. This file owns only inventory sync + allowlist.
 */

type Manifest = {
  dependencies?: Readonly<Record<string, string>>;
  devDependencies?: Readonly<Record<string, string>>;
};

type InventoryEntry = {
  readonly name: string;
  readonly version: string;
  readonly license: string;
  readonly kind: "runtime" | "dev";
};

type Inventory = {
  readonly allowlist: readonly string[];
  readonly entries: readonly InventoryEntry[];
};

const repoRoot = fileURLToPath(new URL("..", import.meta.url));

/** Mirrors the workspace layout enforced by tests/boundaries.test.ts. */
const manifestDirs = [
  "",
  "apps/cli",
  "packages/contracts",
  "packages/core",
  "packages/store-sqlite",
  "packages/provider-openai",
  "packages/tools-local",
  "packages/testkit",
  "packages/extension-telemetry",
  "packages/extension-standing-orders",
];

function readJson(relative: string): unknown {
  return JSON.parse(readFileSync(join(repoRoot, relative), "utf8")) as unknown;
}

type Collected = {
  readonly versions: ReadonlyMap<string, string>;
  readonly runtime: ReadonlySet<string>;
};

function collectManifestExternals(): Collected {
  const versions = new Map<string, string>();
  const runtime = new Set<string>();
  for (const dir of manifestDirs) {
    const manifest = readJson(join(dir, "package.json")) as Manifest;
    const deps = manifest.dependencies ?? {};
    const devDeps = manifest.devDependencies ?? {};
    for (const [name, version] of [...Object.entries(deps), ...Object.entries(devDeps)]) {
      if (name.startsWith("@praxis/")) {
        continue;
      }
      const known = versions.get(name);
      if (known !== undefined && known !== version) {
        throw new Error(`${name} pinned to two versions: ${known} and ${version}`);
      }
      versions.set(name, version);
      // Runtime = declared as a real dependency of a published workspace
      // package (root-only or dev-only entries stay "dev").
      if (dir !== "" && name in deps) {
        runtime.add(name);
      }
    }
  }
  return { versions, runtime };
}

function loadInventory(): Inventory {
  const doc = readFileSync(join(repoRoot, "docs/09-dependency-inventory.md"), "utf8");
  const blocks = [...doc.matchAll(/```json\n([\s\S]*?)```/g)];
  const raw = blocks[0]?.[1];
  if (raw === undefined) {
    throw new Error("docs/09-dependency-inventory.md has no fenced json block");
  }
  return JSON.parse(raw) as Inventory;
}

test("the inventory covers exactly the workspace's external direct dependencies", () => {
  const { versions } = collectManifestExternals();
  const inventory = loadInventory();
  const names = [...versions.keys()].sort();
  const documented = inventory.entries.map((entry) => entry.name).sort();
  expect(documented).toEqual(names);
});

test("every entry matches the pinned manifest version, kind, and installed license", () => {
  const { versions, runtime } = collectManifestExternals();
  const inventory = loadInventory();
  for (const entry of inventory.entries) {
    const manifestVersion = versions.get(entry.name);
    if (manifestVersion === undefined) {
      throw new Error(`${entry.name} is documented but absent from every manifest`);
    }
    expect(entry.version, `${entry.name} version`).toBe(manifestVersion);
    expect(entry.kind, `${entry.name} kind`).toBe(runtime.has(entry.name) ? "runtime" : "dev");
    const installed = readJson(join("node_modules", entry.name, "package.json")) as {
      version?: string;
      license?: string;
    };
    expect(installed.version, `${entry.name} installed version`).toBe(entry.version);
    expect(installed.license, `${entry.name} installed license`).toBe(entry.license);
  }
});

test("every documented license is inside the permissive allowlist", () => {
  const inventory = loadInventory();
  const allowlist = new Set(inventory.allowlist);
  for (const entry of inventory.entries) {
    expect(allowlist.has(entry.license), `${entry.name}: ${entry.license}`).toBe(true);
  }
});
