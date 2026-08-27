import { existsSync, readFileSync } from "node:fs";
import { basename, dirname, relative, resolve } from "node:path";
import { YAML } from "bun";

/**
 * Architecture conformance checker (docs/07-architecture-conformance.md §3).
 *
 * Authority: .praxis/architecture.yaml. Checks:
 * - every workspace package is declared in architecture.yaml;
 * - package manifest dependencies respect may_depend_on / forbidden_dependencies;
 * - TypeScript imports respect package direction and the public API rule
 *   (deep imports into another package are forbidden);
 * - the workspace import graph has no cycles;
 * - core has no undeclared third-party dependencies
 *   (adr_required_for: add_dependency_to_core).
 *
 * Deterministic, model-free. Exits non-zero on any MUST violation.
 * Honors PRAXIS_ROOT to operate on an alternate repository root (tests).
 */

const ROOT = resolve(process.env.PRAXIS_ROOT ?? resolve(import.meta.dir, "../.."));
const PRAXIS = resolve(ROOT, ".praxis");

type PlainObject = Record<string, unknown>;

interface PackageRule {
  mayDependOn: Set<string>;
  forbidden: Set<string>;
  allowedThirdParty: Set<string>;
}

function die(message: string, code = 1): never {
  console.error(`ERROR: ${message}`);
  process.exit(code);
}

function isObject(value: unknown): value is PlainObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringSet(value: unknown, label: string): Set<string> {
  if (value === undefined || value === null) return new Set();
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string")) {
    die(`${label} must be string[]`);
  }
  return new Set(value as string[]);
}

function loadArchitecture(): { rules: Map<string, PackageRule>; declared: Set<string> } {
  const path = resolve(PRAXIS, "architecture.yaml");
  if (!existsSync(path)) die(`missing file: ${relative(ROOT, path)}`);
  const parsed: unknown = YAML.parse(readFileSync(path, "utf8"));
  if (!isObject(parsed)) die("architecture.yaml must be an object");
  if (!isObject(parsed.packages)) die("architecture.packages must be object");
  const rules = new Map<string, PackageRule>();
  for (const [id, rawRule] of Object.entries(parsed.packages)) {
    if (!isObject(rawRule)) die(`architecture.packages.${id} must be object`);
    rules.set(id, {
      mayDependOn: stringSet(rawRule.may_depend_on, `architecture.packages.${id}.may_depend_on`),
      forbidden: stringSet(
        rawRule.forbidden_dependencies,
        `architecture.packages.${id}.forbidden_dependencies`,
      ),
      allowedThirdParty: stringSet(
        rawRule.allowed_third_party,
        `architecture.packages.${id}.allowed_third_party`,
      ),
    });
  }
  return { rules, declared: new Set(rules.keys()) };
}

interface WorkspacePackage {
  id: string;
  name: string;
  manifestPath: string;
}

function discoverPackages(): Map<string, WorkspacePackage> {
  const packages = new Map<string, WorkspacePackage>();
  for (const top of ["packages", "apps"]) {
    const glob = new Bun.Glob(`${top}/*/package.json`);
    for (const manifestPath of glob.scanSync({ cwd: ROOT })) {
      const dir = basename(dirname(manifestPath));
      const id = top === "packages" ? dir : `apps-${dir}`;
      const manifest: unknown = JSON.parse(readFileSync(resolve(ROOT, manifestPath), "utf8"));
      if (!isObject(manifest) || typeof manifest.name !== "string") {
        die(`${manifestPath}: manifest must declare a string name`);
      }
      packages.set(id, { id, name: manifest.name, manifestPath });
    }
  }
  return packages;
}

function manifestDependencies(manifest: PlainObject): string[] {
  const deps: string[] = [];
  for (const field of ["dependencies", "devDependencies"] as const) {
    const value = manifest[field];
    if (isObject(value)) deps.push(...Object.keys(value));
  }
  return deps;
}

const IMPORT_PATTERNS: readonly RegExp[] = [
  /\bfrom\s*["']([^"']+)["']/g,
  /\bimport\s*["']([^"']+)["']/g,
  /\bimport\s*\(\s*["']([^"']+)["']\s*\)/g,
  /\brequire\s*\(\s*["']([^"']+)["']\s*\)/g,
];

function extractImports(source: string): string[] {
  const specs = new Set<string>();
  for (const pattern of IMPORT_PATTERNS) {
    pattern.lastIndex = 0;
    for (const match of source.matchAll(pattern)) {
      const spec = match[1];
      if (spec) specs.add(spec);
    }
  }
  return [...specs];
}

function ownerOf(filePath: string): string | null {
  const parts = filePath.split("/");
  if (parts[0] === "packages" && parts.length > 2) return parts[1] ?? null;
  if (parts[0] === "apps" && parts.length > 2) return `apps-${parts[1]}`;
  return null;
}

function checkManifests(
  packages: Map<string, WorkspacePackage>,
  rules: Map<string, PackageRule>,
  nameToId: Map<string, string>,
  violations: string[],
): Map<string, Set<string>> {
  const edges = new Map<string, Set<string>>();
  for (const pkg of packages.values()) {
    const rule = rules.get(pkg.id);
    const manifest: unknown = JSON.parse(readFileSync(resolve(ROOT, pkg.manifestPath), "utf8"));
    if (!isObject(manifest)) die(`${pkg.manifestPath}: manifest must be an object`);
    for (const dep of manifestDependencies(manifest)) {
      const depId = nameToId.get(dep);
      if (depId) {
        if (!edges.has(pkg.id)) edges.set(pkg.id, new Set());
        edges.get(pkg.id)?.add(depId);
        if (!rule?.mayDependOn.has(depId)) {
          violations.push(
            `manifest-direction: ${pkg.manifestPath}: ${pkg.id} -> ${depId} is not allowed by architecture.yaml`,
          );
        }
        if (rule?.forbidden.has(depId)) {
          violations.push(
            `manifest-forbidden: ${pkg.manifestPath}: ${pkg.id} -> ${depId} is explicitly forbidden`,
          );
        }
      } else if (pkg.id === "core" && rule && !rule.allowedThirdParty.has(dep)) {
        violations.push(
          `core-third-party: ${pkg.manifestPath}: dependency '${dep}' requires an ADR and an architecture.yaml update (adr_required_for: add_dependency_to_core)`,
        );
      }
    }
  }
  return edges;
}

function checkImports(
  rules: Map<string, PackageRule>,
  nameToId: Map<string, string>,
  violations: string[],
): Map<string, Set<string>> {
  const edges = new Map<string, Set<string>>();
  const files = [
    ...new Bun.Glob("packages/*/src/**/*.ts").scanSync({ cwd: ROOT }),
    ...new Bun.Glob("apps/*/src/**/*.ts").scanSync({ cwd: ROOT }),
  ];
  for (const file of files) {
    const ownerId = ownerOf(file);
    if (!ownerId) continue;
    const ownerRule = rules.get(ownerId);
    for (const spec of extractImports(readFileSync(resolve(ROOT, file), "utf8"))) {
      if (!spec.startsWith("@praxis/")) continue;
      const bare = spec.split("/").slice(0, 2).join("/");
      const rest = spec.slice(bare.length);
      const depId = nameToId.get(bare);
      if (!depId) {
        violations.push(`import-unknown-package: ${file}: '${spec}' is not a workspace package`);
        continue;
      }
      if (!edges.has(ownerId)) edges.set(ownerId, new Set());
      edges.get(ownerId)?.add(depId);
      if (rest.length > 0) {
        violations.push(`deep-import: ${file}: '${spec}' bypasses the ${bare} public API`);
      }
      if (!ownerRule?.mayDependOn.has(depId)) {
        violations.push(
          `import-direction: ${file}: ${ownerId} -> ${depId} is not allowed by architecture.yaml`,
        );
      }
    }
  }
  return edges;
}

function findCycles(edges: Map<string, Set<string>>): string[] {
  const cycles: string[] = [];
  const state = new Map<string, "visiting" | "done">();
  const stack: string[] = [];

  function visit(node: string): void {
    const nodeState = state.get(node);
    if (nodeState === "done") return;
    if (nodeState === "visiting") {
      const start = stack.indexOf(node);
      const cycle = [...stack.slice(start), node].join(" -> ");
      cycles.push(`cycle: ${cycle}`);
      return;
    }
    state.set(node, "visiting");
    stack.push(node);
    for (const next of edges.get(node) ?? []) visit(next);
    stack.pop();
    state.set(node, "done");
  }

  for (const node of edges.keys()) visit(node);
  return [...new Set(cycles)];
}

function main(): void {
  const { rules, declared } = loadArchitecture();
  const packages = discoverPackages();
  const nameToId = new Map([...packages.values()].map((pkg) => [pkg.name, pkg.id]));
  const violations: string[] = [];

  for (const id of packages.keys()) {
    if (!declared.has(id)) {
      violations.push(
        `undeclared-package: ${id} exists in the workspace but not in architecture.yaml`,
      );
    }
  }
  for (const id of declared) {
    if (!packages.has(id)) {
      console.log(
        `warning: architecture.yaml declares '${id}' but no such workspace package exists`,
      );
    }
  }

  const manifestEdges = checkManifests(packages, rules, nameToId, violations);
  const importEdges = checkImports(rules, nameToId, violations);
  const edges = new Map<string, Set<string>>();
  for (const [from, tos] of [...manifestEdges, ...importEdges]) {
    if (!edges.has(from)) edges.set(from, new Set());
    for (const to of tos) edges.get(from)?.add(to);
  }
  violations.push(...findCycles(edges));

  if (violations.length > 0) {
    for (const violation of violations) console.error(`- ${violation}`);
    die(`architecture conformance failed (${violations.length} violation(s))`);
  }
  console.log(
    `ARCHITECTURE_PASS ${packages.size} package(s), rules for ${rules.size}, no violations`,
  );
}

main();
