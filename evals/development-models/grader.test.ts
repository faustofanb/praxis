import { sessionCreated, toolProposed } from "@praxis/testkit/session-events";
import { describe, expect, test } from "vitest";
import { gradeDecision } from "./grader";
import { DECIDE_ACTIONS, DECIDE_TOOL_NAME, type DecideAction } from "./scenarios";

/**
 * Grader units (M4-T005): grading reads only the durable ToolProposed fact.
 * Every failure mode has a distinct, greppable reason.
 */

const VALID_ARGS = (action: DecideAction): string =>
  JSON.stringify({ action, rationale: "the durable facts demand it" });

function streamWithDecision(argumentsJson: string) {
  return [sessionCreated(1), toolProposed(2, 1, { name: DECIDE_TOOL_NAME, argumentsJson })];
}

describe("epistemic eval grader", () => {
  test("an expected action in the last decide proposal passes with its rationale", () => {
    const verdict = gradeDecision(streamWithDecision(VALID_ARGS("investigate_further")), [
      "investigate_further",
      "propose_new_plan",
    ]);
    expect(verdict).toEqual({
      verdict: "pass",
      action: "investigate_further",
      rationale: "the durable facts demand it",
    });
  });

  test("the last proposal wins when the model corrects itself mid-turn", () => {
    const events = [
      sessionCreated(1),
      toolProposed(2, 1, {
        name: DECIDE_TOOL_NAME,
        argumentsJson: VALID_ARGS("declare_session_complete"),
      }),
      toolProposed(3, 2, {
        name: DECIDE_TOOL_NAME,
        argumentsJson: VALID_ARGS("resolve_open_challenge"),
      }),
    ];
    expect(gradeDecision(events, ["resolve_open_challenge"]).verdict).toBe("pass");
  });

  test("a wrong action fails naming the choice and the expected set", () => {
    const verdict = gradeDecision(streamWithDecision(VALID_ARGS("declare_session_complete")), [
      "resolve_open_challenge",
    ]);
    expect(verdict).toEqual({
      verdict: "fail",
      reason: 'chose "declare_session_complete"; expected one of: resolve_open_challenge',
    });
  });

  test("no decide proposal in the stream fails explicitly", () => {
    const verdict = gradeDecision([sessionCreated(1)], ["investigate_further"]);
    expect(verdict).toEqual({
      verdict: "fail",
      reason: "the model never called decide_next_action",
    });
  });

  test("unrelated tool proposals are ignored, not graded", () => {
    const events = [sessionCreated(1), toolProposed(2, 1, { name: "read_file" })];
    expect(gradeDecision(events, DECIDE_ACTIONS).verdict).toBe("fail");
  });

  test("arguments that are not JSON fail without throwing", () => {
    const verdict = gradeDecision(streamWithDecision("{not json"), ["investigate_further"]);
    expect(verdict).toEqual({
      verdict: "fail",
      reason: "decide_next_action arguments are not valid JSON",
    });
  });

  test("arguments outside the decision schema fail", () => {
    const verdict = gradeDecision(streamWithDecision(JSON.stringify({ action: "wing_it" })), [
      "investigate_further",
    ]);
    expect(verdict).toEqual({
      verdict: "fail",
      reason: "decide_next_action arguments do not match the decision schema",
    });
  });
});
