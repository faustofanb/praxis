import type {
  ApprovalRequest,
  CapabilityDecision,
  CapabilityGrant,
  CapabilityLease,
  CapabilityRequirement,
} from "@praxis/contracts";
import { normalizeWorkspaceRoot, scopeSatisfies, workspaceRootCovers } from "@praxis/contracts";

/**
 * Runtime capability policy (docs/02 section 9, ADR-0007). Pure decision
 * table — no I/O, no clock (callers inject `now`), no model input. The model
 * may learn what is granted (see capabilityPolicySummary) but can never
 * grant: every decision derives from host-provided grants and leases only.
 *
 * Fail-closed order of judgment:
 * 1. a requested scope outside every workspace root is a scope escape — deny;
 * 2. a standing grant covering name+scope — allow;
 * 3. an unexpired lease covering name+scope — allow;
 * 4. a matching-but-expired lease — deny (expiry is unconditional, never
 *    "probably still fine");
 * 5. an approvable capability — requires_approval (approval UX is an
 *    extension; until it exists the runtime rejects fail-closed);
 * 6. anything else — deny.
 */

export type CapabilityPolicyConfig = {
  /** Workspace boundaries the host configured; scope escapes deny outright. */
  readonly workspaceRoots: readonly string[];
  readonly grants: readonly CapabilityGrant[];
  readonly leases: readonly CapabilityLease[];
  /** Capability names that may be granted later via an approval->lease flow. */
  readonly approvableCapabilities: readonly string[];
};

export function capabilityDecision(
  requirement: CapabilityRequirement,
  config: CapabilityPolicyConfig,
  now: number,
): CapabilityDecision {
  if (requirement.scope?.kind === "workspace") {
    const requested = normalizeWorkspaceRoot(requirement.scope.root);
    const insideWorkspace = config.workspaceRoots.some((root) =>
      workspaceRootCovers(normalizeWorkspaceRoot(root), requested),
    );
    if (!insideWorkspace) {
      return deny(`scope ${requirement.scope.root} escapes the configured workspace`);
    }
  }

  const grant = config.grants.find(
    (candidate) => candidate.name === requirement.name && scopeSatisfies(candidate, requirement),
  );
  if (grant !== undefined) {
    return { type: "allow", via: { kind: "grant" } };
  }

  const lease = config.leases.find(
    (candidate) =>
      candidate.capability === requirement.name && scopeSatisfies(candidate, requirement),
  );
  if (lease !== undefined) {
    if (now < lease.expiresAt) {
      return { type: "allow", via: { kind: "lease", leaseId: lease.id } };
    }
    return deny(
      `lease ${lease.id.valueOf()} for ${requirement.name} expired at ${lease.expiresAt} (now ${now})`,
    );
  }

  if (config.approvableCapabilities.includes(requirement.name)) {
    const request: ApprovalRequest = {
      capability: requirement.name,
      ...(requirement.scope === undefined ? {} : { scope: requirement.scope }),
    };
    return { type: "requires_approval", request };
  }

  return deny(`capability ${requirement.name} is not granted`);
}

function deny(reason: string): CapabilityDecision {
  return { type: "deny", reason };
}

/**
 * Deterministic, model-visible projection of the current policy (docs/02
 * section 9.1: the model may know its capabilities, never grant them).
 * Expired leases are listed as expired — honest state, not wishful access.
 */
export function capabilityPolicySummary(config: CapabilityPolicyConfig, now: number): string {
  const lines: string[] = [];
  const grants = [...config.grants].sort((a, b) => a.name.localeCompare(b.name));
  if (grants.length > 0) {
    lines.push(
      `Granted: ${grants.map((grant) => formatEntry(grant.name, grant.scope?.root)).join(", ")}`,
    );
  }
  const leases = [...config.leases].sort((a, b) => a.capability.localeCompare(b.capability));
  for (const lease of leases) {
    const state = now < lease.expiresAt ? `expires ${lease.expiresAt}` : "EXPIRED";
    lines.push(
      `Lease ${lease.id.valueOf()} (${lease.reason}): ${formatEntry(lease.capability, lease.scope?.root)} — ${state}`,
    );
  }
  const approvable = [...config.approvableCapabilities].sort((a, b) => a.localeCompare(b));
  if (approvable.length > 0) {
    lines.push(
      `Requires human approval before use: ${approvable.join(", ")} — re-proposing does not grant them.`,
    );
  }
  if (lines.length === 0) {
    return "No capabilities granted.";
  }
  return lines.join("\n");
}

function formatEntry(name: string, root: string | undefined): string {
  return root === undefined ? name : `${name} (workspace ${normalizeWorkspaceRoot(root)})`;
}
