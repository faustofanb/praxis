import {
  SessionEventUnionSchema,
  TOOL_EFFECTS,
  TOOL_EVENT_TYPES,
  ToolEffectSchema,
  ToolProposedEventSchema,
} from "@praxis/contracts";
import { describe, expect, test } from "vitest";
import {
  toolAuthorized,
  toolFailed,
  toolIndeterminate,
  toolProposed,
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
    ];
    for (const sample of samples) {
      expect(SessionEventUnionSchema.parse(sample)).toBeTruthy();
    }
  });

  test("the vocabulary covers exactly the seven lifecycle events", () => {
    expect(TOOL_EVENT_TYPES).toEqual([
      "ToolProposed",
      "ToolAuthorized",
      "ToolRejected",
      "ToolStarted",
      "ToolSucceeded",
      "ToolFailed",
      "ToolIndeterminate",
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
