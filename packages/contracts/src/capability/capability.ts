import { z } from "zod";
import { CapabilityLeaseIdSchema } from "../ids";

/**
 * Capability vocabulary (docs/02 section 9). Contracts own the shapes and
 * the lexical scope rules; the allow/deny decision table lives in Core.
 *
 * Scope handling is deliberately lexical and strict: roots must be absolute
 * POSIX-ish paths, "." segments are dropped, ".." segments are REJECTED
 * (never resolved — resolving would silently widen scope), duplicate slashes
 * collapse, and a trailing slash is removed. Containment is prefix-based on
 * the normalized form, so "/work" never covers "/workspace".
 */

export const CapabilityScopeSchema = z.discriminatedUnion("kind", [
  z.object({ kind: z.literal("workspace"), root: z.string().min(1) }),
]);
export type CapabilityScope = z.infer<typeof CapabilityScopeSchema>;

export const CapabilityRequirementSchema = z.object({
  /** Capability name, e.g. "fs.read" | "fs.write" | "shell.exec" or an extension name. */
  name: z.string().min(1),
  scope: CapabilityScopeSchema.optional(),
});
export type CapabilityRequirement = z.infer<typeof CapabilityRequirementSchema>;

export const CapabilityGrantSchema = z.object({
  name: z.string().min(1),
  scope: CapabilityScopeSchema.optional(),
});
export type CapabilityGrant = z.infer<typeof CapabilityGrantSchema>;

export const CapabilityLeaseSchema = z.object({
  id: z.string().min(1).brand<"CapabilityLeaseId">(),
  capability: z.string().min(1),
  scope: CapabilityScopeSchema.optional(),
  issuedAt: z.number().int().nonnegative(),
  expiresAt: z.number().int().positive(),
  reason: z.string().min(1),
});
export type CapabilityLease = z.infer<typeof CapabilityLeaseSchema>;

export const ApprovalRequestSchema = z.object({
  capability: z.string().min(1),
  scope: CapabilityScopeSchema.optional(),
});
export type ApprovalRequest = z.infer<typeof ApprovalRequestSchema>;

export const CapabilityViaSchema = z.discriminatedUnion("kind", [
  z.object({ kind: z.literal("grant") }),
  z.object({ kind: z.literal("lease"), leaseId: CapabilityLeaseIdSchema }),
]);
export type CapabilityVia = z.infer<typeof CapabilityViaSchema>;

/**
 * Policy decision (docs/02 section 9.1). `allow` names what satisfied it
 * (standing grant or a specific lease) so denials and approvals can cite
 * evidence; `requires_approval` carries the request an approval extension
 * would turn into a lease — until then the runtime rejects fail-closed
 * (ADR-0007).
 */
export const CapabilityDecisionSchema = z.discriminatedUnion("type", [
  z.object({ type: z.literal("allow"), via: CapabilityViaSchema }),
  z.object({ type: z.literal("deny"), reason: z.string().min(1) }),
  z.object({ type: z.literal("requires_approval"), request: ApprovalRequestSchema }),
]);
export type CapabilityDecision = z.infer<typeof CapabilityDecisionSchema>;

/**
 * Normalize a workspace root to its canonical form. Throws on non-absolute
 * roots and on ".." segments — a scope that needs ".." to make sense is a
 * scope escape attempt, not a path to resolve.
 */
export function normalizeWorkspaceRoot(root: string): string {
  if (!root.startsWith("/")) {
    throw new Error(`workspace root must be absolute: ${root}`);
  }
  const segments: string[] = [];
  for (const segment of root.split("/")) {
    if (segment === "" || segment === ".") {
      continue;
    }
    if (segment === "..") {
      throw new Error(`workspace root must not contain '..': ${root}`);
    }
    segments.push(segment);
  }
  return segments.length === 0 ? "/" : `/${segments.join("/")}`;
}

/**
 * True when `covering` (a grant/lease/workspace root) contains `covered`
 * (the requested scope). Both must already be normalized; "/" covers
 * everything; otherwise containment is exact or child-by-segment prefix —
 * never a raw string prefix, so "/work" does not cover "/workspace".
 */
export function workspaceRootCovers(covering: string, covered: string): boolean {
  if (covering === "/") {
    return true;
  }
  if (covering === covered) {
    return true;
  }
  return covered.startsWith(`${covering}/`);
}

/**
 * Does `grant`'s scope satisfy `request`'s scope? An undefined grant scope
 * is global; otherwise the grant's workspace root must cover the request's.
 */
export function scopeSatisfies(
  grant: CapabilityGrant | CapabilityLease,
  request: CapabilityRequirement,
): boolean {
  if (grant.scope === undefined) {
    return true;
  }
  if (request.scope === undefined) {
    // A scoped grant cannot satisfy a requirement that asks for the
    // capability everywhere.
    return false;
  }
  if (grant.scope.kind !== request.scope.kind) {
    return false;
  }
  if (grant.scope.kind === "workspace" && request.scope.kind === "workspace") {
    return workspaceRootCovers(
      normalizeWorkspaceRoot(grant.scope.root),
      normalizeWorkspaceRoot(request.scope.root),
    );
  }
  return false;
}
