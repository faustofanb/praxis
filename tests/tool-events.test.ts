import {
  SessionEventUnionSchema,
  TOOL_EFFECTS,
  TOOL_EVENT_TYPES,
  ToolEffectSchema,
  ToolProposedEventSchema,
  ToolReconciledEventSchema,
} from "@praxis/contracts";
import { describe, expect, test } from "vitest";
import {
  toolAuthorized,
  toolFailed,
  toolIndeterminate,
  toolProposed,
  toolReconciled,
  toolRejected,
  toolStarted,
  toolSucceeded,
} from "./helpers/session-events";

describe("tool lifecycle event schemas", () => {
  test("every tool event type parses through its owning schema", () => {
    const samples = [
      toolProposed(1, 1),
      toolAuthorized(2, 1),
      toolRejected(2, 1),
      toolStarted(3, 1),
      toolSucceeded(4, 1),
      toolFailed(4, 1),
      toolIndeterminate(4, 1),
      toolReconciled(5, 1, "succeeded", '{"paymentId":"pay_1"}'),
      toolReconciled(5, 1, "failed", "provably absent"),
      toolReconciled(5, 1, "indeterminate", "still unknown"),
    ];
    for (const sample of samples) {
      expect(SessionEventUnionSchema.parse(sample)).toBeTruthy();
    }
  });

  test("the vocabulary covers exactly the eight lifecycle events", () => {
    expect(TOOL_EVENT_TYPES).toEqual([
      "ToolProposed",
      "ToolAuthorized",
      "ToolRejected",
      "ToolStarted",
      "ToolSucceeded",
      "ToolFailed",
      "ToolIndeterminate",
      "ToolReconciled",
    ]);
  });

  test("records the effect class as a fact on ToolProposed", () => {
    for (const effect of TOOL_EFFECTS) {
      const parsed = ToolProposedEventSchema.parse(toolProposed(1, 1, { effect }));
      expect(parsed.payload.effect).toBe(effect);
    }
    expect(() =>
      ToolProposedEventSchema.parse(toolProposed(1, 1, { effect: "chaotic" as never })),
    ).toThrow();
    expect(() => ToolEffectSchema.parse("chaotic")).toThrow();
  });

  test("requires non-empty identifiers and reasons", () => {
    expect(() =>
      SessionEventUnionSchema.parse({
        ...toolProposed(1, 1),
        payload: {
          toolExecutionId: "",
          name: "read_file",
          argumentsJson: "{}",
          effect: "read_only",
        },
      }),
    ).toThrow();
    expect(() =>
      SessionEventUnionSchema.parse({
        ...toolRejected(1, 1),
        payload: { toolExecutionId: "tool-exec-1", reason: "" },
      }),
    ).toThrow();
    expect(() =>
      SessionEventUnionSchema.parse({
        ...toolFailed(1, 1),
        payload: { toolExecutionId: "tool-exec-1", message: "" },
      }),
    ).toThrow();
  });

  test("rejects lifecycle types outside the vocabulary", () => {
    expect(() =>
      SessionEventUnionSchema.parse({
        ...toolStarted(1, 1),
        type: "ToolCancelled",
      }),
    ).toThrow();
  });
});

describe("ToolReconciled payload boundaries", () => {
  test("each outcome variant carries exactly its proof field", () => {
    const succeeded = ToolReconciledEventSchema.parse(
      toolReconciled(1, 1, "succeeded", '{"paymentId":"pay_1"}'),
    );
    expect(succeeded.payload).toEqual({
      toolExecutionId: "tool-exec-1",
      outcome: "succeeded",
      resultJson: '{"paymentId":"pay_1"}',
    });

    const failed = ToolReconciledEventSchema.parse(toolReconciled(1, 1, "failed", "absent"));
    expect(failed.payload).toEqual({
      toolExecutionId: "tool-exec-1",
      outcome: "failed",
      message: "absent",
    });

    const indeterminate = ToolReconciledEventSchema.parse(
      toolReconciled(1, 1, "indeterminate", "still unknown"),
    );
    expect(indeterminate.payload).toEqual({
      toolExecutionId: "tool-exec-1",
      outcome: "indeterminate",
      reason: "still unknown",
    });
  });

  test("variant and payload must agree — no coerced or invented outcomes", () => {
    // succeeded without its proof
    expect(() =>
      SessionEventUnionSchema.parse({
        ...toolReconciled(1, 1),
        payload: { toolExecutionId: "tool-exec-1", outcome: "succeeded" },
      }),
    ).toThrow();
    // failed with an empty justification
    expect(() =>
      SessionEventUnionSchema.parse({
        ...toolReconciled(1, 1),
        payload: { toolExecutionId: "tool-exec-1", outcome: "failed", message: "" },
      }),
    ).toThrow();
    // an outcome outside the reconciliation vocabulary
    expect(() =>
      SessionEventUnionSchema.parse({
        ...toolReconciled(1, 1),
        payload: { toolExecutionId: "tool-exec-1", outcome: "cancelled" },
      }),
    ).toThrow();
  });
});
