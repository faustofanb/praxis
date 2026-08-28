import type { ToolAuthorizer } from "../tools/tool-runtime";
import type { CapabilityPolicyConfig } from "./policy";
import { capabilityDecision } from "./policy";

/**
 * Adapts the capability decision table onto the tool runtime's authorizer
 * seam (docs/02 section 9.3 layer 1; layer 2 — path/cwd confinement — lives
 * in tool implementations). `requires_approval` rejects fail-closed with an
 * explicit reason (ADR-0007): approval UX is an extension, and its absence
 * must never open the gate. The clock is injected so decisions replay
 * deterministically in tests.
 */
export function capabilityAuthorizer(deps: {
  readonly policy: CapabilityPolicyConfig;
  readonly now: () => number;
}): ToolAuthorizer {
  return (request) => {
    if (request.requiredCapability === undefined) {
      // Defense in depth: registration already rejects write tools without a
      // capability; a tool that reaches here without one may only run if its
      // effect class makes it harmless.
      if (request.effect === "read_only") {
        return { decision: "authorized" };
      }
      return {
        decision: "rejected",
        reason: `tool ${request.name} has effect ${request.effect} but declares no capability requirement`,
      };
    }
    const decision = capabilityDecision(request.requiredCapability, deps.policy, deps.now());
    switch (decision.type) {
      case "allow":
        return { decision: "authorized" };
      case "deny":
        return {
          decision: "rejected",
          reason: `capability denied: ${decision.reason}`,
        };
      case "requires_approval":
        return {
          decision: "rejected",
          reason: `capability ${decision.request.capability} requires human approval; none is configured, so the call is rejected (fail closed)`,
        };
    }
  };
}
