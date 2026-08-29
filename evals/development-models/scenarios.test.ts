import { foldSessionEvents, validateToolDefinitions } from "@praxis/core";
import { describe, expect, test } from "vitest";
import {
  checkExternalWriteTool,
  DECIDE_ACTIONS,
  DECIDE_TOOL_NAME,
  decideToolDefinition,
  PROBE_TOOL_NAME,
  SCENARIOS,
} from "./scenarios";

/**
 * Scenario integrity (M4-T005): every scenario must be buildable from legal
 * durable facts, advertise tools that pass registration, and grade against a
 * reachable action set. If a seed stops folding or a brief marker drifts,
 * these tests fail before any real-model evidence is trusted.
 */

describe("epistemic eval scenario integrity", () => {
  test("scenarios are unique and cover the four M4 laws", () => {
    const ids = SCENARIOS.map((scenario) => scenario.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(ids).toEqual([
      "invalidated-plan",
      "completion-blocked",
      "pending-indeterminate",
      "inconclusive-verification",
    ]);
  });

  for (const scenario of SCENARIOS) {
    test(`scenario ${scenario.id}: seed folds legally and expected actions are reachable`, () => {
      expect(() => foldSessionEvents([...scenario.seed])).not.toThrow();
      expect(scenario.expectedActions.length).toBeGreaterThan(0);
      for (const action of scenario.expectedActions) {
        expect(DECIDE_ACTIONS).toContain(action);
      }
      expect(scenario.briefMustContain.length).toBeGreaterThan(0);
      expect(scenario.prompt).toContain("decide_next_action");
    });
  }

  test("tool definitions pass registration validation", () => {
    // The probe's two behaviors share one name — a real deps registers
    // exactly one instance; validate each registration separately.
    expect(() =>
      validateToolDefinitions([decideToolDefinition(), checkExternalWriteTool("clear")]),
    ).not.toThrow();
    expect(() =>
      validateToolDefinitions([decideToolDefinition(), checkExternalWriteTool("indeterminate")]),
    ).not.toThrow();
  });

  test("advertised parameters match the decision vocabulary", () => {
    const decide = decideToolDefinition();
    expect(decide.name).toBe(DECIDE_TOOL_NAME);
    const parameters = JSON.parse(decide.parametersJson) as {
      properties: { action: { enum: string[] } };
    };
    expect(parameters.properties.action.enum).toEqual([...DECIDE_ACTIONS]);

    const probe = checkExternalWriteTool("clear");
    expect(probe.name).toBe(PROBE_TOOL_NAME);
    expect(() => JSON.parse(probe.parametersJson)).not.toThrow();
  });
});
