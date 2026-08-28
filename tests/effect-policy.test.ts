import type { ToolDefinition } from "@praxis/contracts";
import { TOOL_EFFECTS } from "@praxis/contracts";
import { retryPolicyForEffect, validateToolDefinitions } from "@praxis/core";
import { describe, expect, test } from "vitest";
import { z } from "zod";

function makeTool(overrides: Partial<ToolDefinition> = {}): ToolDefinition {
  return {
    name: "example_tool",
    description: "example",
    effect: "read_only",
    inputSchema: z.unknown(),
    parametersJson: "{}",
    execute: async () => ({ status: "succeeded", resultJson: "{}" }),
    ...overrides,
  };
}

describe("retryPolicyForEffect", () => {
  test("maps every effect class to its runtime retry rule", () => {
    expect(retryPolicyForEffect("read_only")).toBe("safe_to_repeat");
    expect(retryPolicyForEffect("idempotent_write")).toBe("safe_to_repeat");
    expect(retryPolicyForEffect("reconcilable_write")).toBe("repeat_only_after_reconciled_absence");
    expect(retryPolicyForEffect("non_idempotent_write")).toBe("never_repeat");
  });

  test("is total: every effect in the vocabulary has a policy", () => {
    for (const effect of TOOL_EFFECTS) {
      expect(typeof retryPolicyForEffect(effect)).toBe("string");
    }
  });
});

describe("validateToolDefinitions (ADR-0006 registration enforcement)", () => {
  test("accepts definitions whose effect class keeps its promise", () => {
    expect(() =>
      validateToolDefinitions([
        makeTool({ name: "read_file", effect: "read_only" }),
        makeTool({
          name: "write_file",
          effect: "idempotent_write",
        }),
        makeTool({
          name: "send_payment",
          effect: "reconcilable_write",
          reconcile: async () => ({ status: "indeterminate", reason: "unknown" }),
        }),
        makeTool({
          name: "send_email",
          effect: "non_idempotent_write",
        }),
      ]),
    ).not.toThrow();
  });

  test("rejects reconcilable_write without reconcile — the class name would be a lie", () => {
    expect(() =>
      validateToolDefinitions([makeTool({ name: "send_payment", effect: "reconcilable_write" })]),
    ).toThrow(/send_payment declares effect reconcilable_write but defines no reconcile/u);
  });

  test("non_idempotent_write may reconcile to settle facts for escalation", () => {
    expect(() =>
      validateToolDefinitions([
        makeTool({
          name: "send_email",
          effect: "non_idempotent_write",
          reconcile: async () => ({ status: "indeterminate", reason: "unknown" }),
        }),
      ]),
    ).not.toThrow();
  });

  test("rejects duplicate names", () => {
    expect(() =>
      validateToolDefinitions([makeTool({ name: "read_file" }), makeTool({ name: "read_file" })]),
    ).toThrow(/duplicate tool definition: read_file/u);
  });
});
