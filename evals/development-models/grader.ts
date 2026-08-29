import type { SessionEventUnion } from "@praxis/contracts";
import { DECIDE_TOOL_NAME, type DecideAction, DecideInputSchema } from "./scenarios";

/**
 * Grade a scenario run from the durable stream alone (M4-T005). The grader
 * never inspects provider internals or raw model text: the decision is the
 * last decide_next_action ToolProposed fact, parsed with the same schema the
 * runtime enforced — so grading is replayable exactly like any other
 * projection over events.
 */

export type ScenarioVerdict =
  | { verdict: "pass"; action: DecideAction; rationale: string }
  | { verdict: "fail"; reason: string };

type ToolProposedEvent = Extract<SessionEventUnion, { type: "ToolProposed" }>;

function isDecideProposal(event: SessionEventUnion): event is ToolProposedEvent {
  return event.type === "ToolProposed" && event.payload.name === DECIDE_TOOL_NAME;
}

export function gradeDecision(
  events: readonly SessionEventUnion[],
  expectedActions: readonly DecideAction[],
): ScenarioVerdict {
  const proposals = events.filter(isDecideProposal);
  // Last proposal wins: a model may correct itself inside the turn; the
  // final recorded decision is the one the session would act on.
  const last = proposals.at(-1);
  if (last === undefined) {
    return { verdict: "fail", reason: "the model never called decide_next_action" };
  }
  let raw: unknown;
  try {
    raw = JSON.parse(last.payload.argumentsJson);
  } catch {
    return { verdict: "fail", reason: "decide_next_action arguments are not valid JSON" };
  }
  const decision = DecideInputSchema.safeParse(raw);
  if (!decision.success) {
    return {
      verdict: "fail",
      reason: "decide_next_action arguments do not match the decision schema",
    };
  }
  const { action, rationale } = decision.data;
  if (!expectedActions.includes(action)) {
    return {
      verdict: "fail",
      reason: `chose "${action}"; expected one of: ${expectedActions.join(", ")}`,
    };
  }
  return { verdict: "pass", action, rationale };
}
