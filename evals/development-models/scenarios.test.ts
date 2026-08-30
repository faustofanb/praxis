import { foldSessionEvents, validateToolDefinitions } from "@praxis/core";
import { describe, expect, test } from "vitest";
import {
  checkExternalWriteTool,
  DECIDE_ACTIONS,
  DECIDE_TOOL_NAME,
  type DecideAction,
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
  test("scenarios are unique and form the 8-row formal matrix (M7-T005)", () => {
    const ids = SCENARIOS.map((scenario) => scenario.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(ids).toEqual([
      "invalidated-plan",
      "completion-blocked",
      "pending-indeterminate",
      "inconclusive-verification",
      "healthy-plan",
      "completion-legal",
      "resolved-indeterminate",
      "plan-challenge",
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

  test("every row cites the runtime law it evaluates (owning docs/02 section)", () => {
    for (const scenario of SCENARIOS) {
      expect(scenario.law.length).toBeGreaterThan(0);
      expect(scenario.law).toContain("docs/02");
    }
  });

  test("the matrix grades every word of the decision vocabulary", () => {
    // Both directions: each graded action is in the vocabulary (asserted
    // per scenario above), and each vocabulary word is the CORRECT answer
    // somewhere — otherwise the matrix has a blind spot a cautious or
    // complacent model could exploit without ever being caught.
    const graded = SCENARIOS.flatMap((scenario) => scenario.expectedActions);
    for (const action of DECIDE_ACTIONS) {
      expect(graded, `no row grades "${action}" as correct`).toContain(action);
    }
  });

  test("each clarified action anchors to its own fact surface or runtime law (M7-T013)", () => {
    // The v1 vocabulary let every model conflate the verification family
    // (0/5 on pending-indeterminate) and miss the plan-persistence and
    // completion-refusal laws (0/5 healthy-plan, repeated completion bias).
    // The descriptions must carry the anchors that separate them — facts
    // about the vocabulary and the runtime, identical for every model.
    const decide = decideToolDefinition();
    const description = JSON.parse(decide.parametersJson) as {
      properties: { action: { description: string } };
    };
    const text = description.properties.action.description;
    const anchors: readonly [DecideAction, readonly string[]][] = [
      ["continue_previous_action", ["plan of record", "persists until falsified"]],
      [
        "verify_or_reconcile_effect",
        ["EXECUTION", "unknown outcome", "Pending indeterminate", "not a re-verification"],
      ],
      [
        "re_verify_with_stronger_evidence",
        ["VERIFICATION", "inconclusive", "Latest verification", "not executions"],
      ],
      ["declare_session_complete", ["runtime refuses completion", "completion-target challenge"]],
      ["resolve_open_challenge", ["open challenge"]],
      ["propose_new_plan", ["falsified", "missing"]],
      ["investigate_further", ["evidence"]],
    ];
    for (const [action, needles] of anchors) {
      const segment = text.slice(text.indexOf(`${action}:`));
      expect(segment, `no anchor for ${action}`).toContain(action);
      for (const needle of needles) {
        expect(segment, `${action} missing anchor "${needle}"`).toContain(needle);
      }
    }
  });

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
