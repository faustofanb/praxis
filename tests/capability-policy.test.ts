import type { CapabilityLease, CapabilityRequirement } from "@praxis/contracts";
import {
  asCapabilityLeaseId,
  normalizeWorkspaceRoot,
  scopeSatisfies,
  workspaceRootCovers,
} from "@praxis/contracts";
import {
  type CapabilityPolicyConfig,
  capabilityAuthorizer,
  capabilityDecision,
  capabilityPolicySummary,
} from "@praxis/core";
import { describe, expect, test } from "vitest";

const workspace = (root: string) => ({ kind: "workspace" as const, root });

function makeLease(overrides: Partial<CapabilityLease> = {}): CapabilityLease {
  return {
    id: asCapabilityLeaseId("lease-1"),
    capability: "fs.write",
    scope: workspace("/w"),
    issuedAt: 100,
    expiresAt: 1_000,
    reason: "demo write window",
    ...overrides,
  };
}

function makeConfig(overrides: Partial<CapabilityPolicyConfig> = {}): CapabilityPolicyConfig {
  return {
    workspaceRoots: ["/w"],
    grants: [],
    leases: [],
    approvableCapabilities: ["fs.write"],
    ...overrides,
  };
}

describe("workspace scope normalization", () => {
  test("canonicalizes separators, dot segments, and trailing slashes", () => {
    expect(normalizeWorkspaceRoot("/w//sub/")).toBe("/w/sub");
    expect(normalizeWorkspaceRoot("/w/./sub")).toBe("/w/sub");
    expect(normalizeWorkspaceRoot("/")).toBe("/");
  });

  test("rejects relative roots and '..' — escapes are never resolved", () => {
    expect(() => normalizeWorkspaceRoot("w/sub")).toThrow(/must be absolute/u);
    expect(() => normalizeWorkspaceRoot("/w/../etc")).toThrow(/must not contain '..'/u);
  });

  test("containment is segment-wise, never a raw string prefix", () => {
    expect(workspaceRootCovers("/", "/anything")).toBe(true);
    expect(workspaceRootCovers("/w", "/w")).toBe(true);
    expect(workspaceRootCovers("/w", "/w/sub")).toBe(true);
    expect(workspaceRootCovers("/work", "/workspace")).toBe(false);
    expect(workspaceRootCovers("/w", "/wx")).toBe(false);
  });

  test("scope satisfaction: global grants cover, scoped grants must contain", () => {
    const global = { name: "fs.read" };
    const scoped = { name: "fs.read", scope: workspace("/w") };
    const request: CapabilityRequirement = { name: "fs.read", scope: workspace("/w/sub") };
    expect(scopeSatisfies(global, request)).toBe(true);
    expect(scopeSatisfies(scoped, request)).toBe(true);
    expect(scopeSatisfies({ ...scoped, scope: workspace("/other") }, request)).toBe(false);
    expect(scopeSatisfies(scoped, { name: "fs.read" })).toBe(false);
  });
});

describe("capabilityDecision (docs/02 section 9.1 decision table)", () => {
  test("a scope outside every workspace root is a scope escape — deny", () => {
    const decision = capabilityDecision(
      { name: "fs.read", scope: workspace("/etc") },
      makeConfig(),
      0,
    );
    expect(decision).toEqual({
      type: "deny",
      reason: expect.stringContaining("escapes the configured workspace") as unknown as string,
    });
  });

  test("a standing grant covering name and scope allows", () => {
    const decision = capabilityDecision(
      { name: "fs.read", scope: workspace("/w/sub") },
      makeConfig({ grants: [{ name: "fs.read", scope: workspace("/w") }] }),
      0,
    );
    expect(decision).toEqual({ type: "allow", via: { kind: "grant" } });
  });

  test("an unexpired lease allows and names the lease that satisfied it", () => {
    const decision = capabilityDecision(
      { name: "fs.write", scope: workspace("/w") },
      makeConfig({ leases: [makeLease()] }),
      999,
    );
    expect(decision).toEqual({ type: "allow", via: { kind: "lease", leaseId: makeLease().id } });
  });

  test("an expired lease denies unconditionally — at and after expiresAt", () => {
    for (const now of [1_000, 5_000]) {
      const decision = capabilityDecision(
        { name: "fs.write", scope: workspace("/w") },
        makeConfig({ leases: [makeLease()] }),
        now,
      );
      expect(decision.type).toBe("deny");
      if (decision.type === "deny") {
        expect(decision.reason).toContain("expired");
      }
    }
  });

  test("an approvable capability without grant or lease requires approval", () => {
    const decision = capabilityDecision(
      { name: "fs.write", scope: workspace("/w") },
      makeConfig(),
      0,
    );
    expect(decision).toEqual({
      type: "requires_approval",
      request: { capability: "fs.write", scope: workspace("/w") },
    });
  });

  test("an ungranted, unapprovable capability denies (fail closed)", () => {
    const decision = capabilityDecision(
      { name: "kernel.load", scope: workspace("/w") },
      makeConfig(),
      0,
    );
    expect(decision.type).toBe("deny");
  });

  test("grants cannot be satisfied by a lease of a different capability or scope", () => {
    const config = makeConfig({
      leases: [makeLease({ capability: "shell.exec" }), makeLease({ scope: workspace("/other") })],
    });
    const decision = capabilityDecision({ name: "fs.write", scope: workspace("/w") }, config, 500);
    expect(decision.type).toBe("requires_approval");
  });
});

describe("capabilityAuthorizer (runtime seam, fail closed)", () => {
  test("allow maps to authorized", () => {
    const authorizer = capabilityAuthorizer({
      policy: makeConfig({ grants: [{ name: "fs.read", scope: workspace("/w") }] }),
      now: () => 0,
    });
    expect(
      authorizer({
        name: "read_file",
        effect: "read_only",
        argumentsJson: "{}",
        requiredCapability: { name: "fs.read", scope: workspace("/w") },
      }),
    ).toEqual({ decision: "authorized" });
  });

  test("deny maps to rejected with the reason", () => {
    const authorizer = capabilityAuthorizer({ policy: makeConfig(), now: () => 0 });
    const decision = authorizer({
      name: "read_file",
      effect: "read_only",
      argumentsJson: "{}",
      requiredCapability: { name: "kernel.load", scope: workspace("/w") },
    });
    expect(decision).toEqual({
      decision: "rejected",
      reason: expect.stringContaining("capability denied") as unknown as string,
    });
  });

  test("requires_approval rejects — approval UX is absent, so the gate stays closed", () => {
    const authorizer = capabilityAuthorizer({ policy: makeConfig(), now: () => 0 });
    const decision = authorizer({
      name: "write_file",
      effect: "idempotent_write",
      argumentsJson: "{}",
      requiredCapability: { name: "fs.write", scope: workspace("/w") },
    });
    expect(decision).toEqual({
      decision: "rejected",
      reason: expect.stringContaining("requires human approval") as unknown as string,
    });
  });

  test("a write tool with no declared requirement is rejected, read-only tools pass", () => {
    const authorizer = capabilityAuthorizer({ policy: makeConfig(), now: () => 0 });
    expect(authorizer({ name: "rogue", effect: "idempotent_write", argumentsJson: "{}" })).toEqual({
      decision: "rejected",
      reason: expect.stringContaining("declares no capability requirement") as unknown as string,
    });
    expect(authorizer({ name: "read_file", effect: "read_only", argumentsJson: "{}" })).toEqual({
      decision: "authorized",
    });
  });
});

describe("capabilityPolicySummary (model-visible projection)", () => {
  test("lists grants, lease states, and approvables deterministically", () => {
    const config = makeConfig({
      grants: [{ name: "fs.read", scope: workspace("/w") }],
      leases: [makeLease(), makeLease({ id: asCapabilityLeaseId("lease-2"), expiresAt: 50 })],
    });
    const summary = capabilityPolicySummary(config, 100);
    expect(summary).toContain("Granted: fs.read (workspace /w)");
    expect(summary).toContain(
      "Lease lease-1 (demo write window): fs.write (workspace /w) — expires 1000",
    );
    expect(summary).toContain(
      "Lease lease-2 (demo write window): fs.write (workspace /w) — EXPIRED",
    );
    expect(summary).toContain("Requires human approval before use: fs.write");
    expect(capabilityPolicySummary(config, 100)).toBe(summary);
  });

  test("an empty policy is stated honestly", () => {
    expect(
      capabilityPolicySummary(
        { workspaceRoots: ["/w"], grants: [], leases: [], approvableCapabilities: [] },
        0,
      ),
    ).toBe("No capabilities granted.");
  });
});
