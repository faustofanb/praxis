import type { SessionEventUnion, ToolDefinition } from "@praxis/contracts";
import {
  challengeRaised,
  goalSet,
  hypothesisProposed,
  hypothesisStatusChanged,
  observationRecorded,
  planSet,
  sessionCreated,
  verificationRecorded,
} from "@praxis/testkit/session-events";
import { z } from "zod";

/**
 * Epistemic eval scenarios (docs/08 section 3, M4-T005). Each scenario is a
 * seed of legal durable facts that renders a specific epistemic-brief
 * section, plus the set of decide-tool actions a model that actually reads
 * the brief would choose. Prompts describe only the mechanical protocol —
 * never the answer — and are identical across models, so per-scenario pass
 * rates are a fair comparative signal.
 *
 * Runtime reality shapes the design: a pending INDETERMINATE execution at
 * turn entry pauses the session before the model is ever consulted
 * (M4-T004/M3-T004 recovery law), so the indeterminate scenario cannot be
 * seeded — the model must LIVE one mid-turn via the check_external_write
 * probe (runTurn continues the loop after a terminal indeterminate fact,
 * and the next request's brief carries the pending section).
 *
 * Real-model invocation lives in run-eval.ts (non-core-gating per
 * .praxis/milestones/M4.yaml); correctness of the scenarios, the grader,
 * and the harness is pinned by tests/eval/ with ScriptedModelProvider.
 */

export const DECIDE_TOOL_NAME = "decide_next_action";
export const PROBE_TOOL_NAME = "check_external_write";

/** Fixed decision vocabulary shared by every scenario. */
export const DECIDE_ACTIONS = [
  "continue_previous_action",
  "investigate_further",
  "propose_new_plan",
  "verify_or_reconcile_effect",
  "resolve_open_challenge",
  "re_verify_with_stronger_evidence",
  "declare_session_complete",
] as const;

export type DecideAction = (typeof DECIDE_ACTIONS)[number];

export const DecideInputSchema = z.object({
  action: z.enum(DECIDE_ACTIONS),
  rationale: z.string().min(1).max(500),
});

export type DecideInput = z.infer<typeof DecideInputSchema>;

export function decideToolDefinition(): ToolDefinition {
  return {
    name: DECIDE_TOOL_NAME,
    description:
      "Record the single next action for the session. Choose from the enumerated actions; the structured context sections state the durable facts that make exactly some of them legal.",
    effect: "read_only",
    inputSchema: DecideInputSchema,
    parametersJson: JSON.stringify({
      type: "object",
      additionalProperties: false,
      required: ["action", "rationale"],
      properties: {
        action: {
          type: "string",
          enum: [...DECIDE_ACTIONS],
          description:
            "continue_previous_action: repeat the plan's recorded next action; investigate_further: gather evidence before deciding; propose_new_plan: replace a dead or missing plan; verify_or_reconcile_effect: check whether an unknown-effect action actually happened; resolve_open_challenge: answer an open challenge before proceeding; re_verify_with_stronger_evidence: redo a verification that was inconclusive; declare_session_complete: the goal is met and completion is legal.",
        },
        rationale: {
          type: "string",
          description: "One sentence citing the fact that makes this the legal next action.",
        },
      },
    }),
    async execute(_context, input) {
      // Read-only echo: the decision itself is the durable ToolProposed fact.
      return { status: "succeeded", resultJson: JSON.stringify({ decision: input }) };
    },
  };
}

/** What the probe tool reports when the model runs it. */
export type ProbeBehavior = "clear" | "indeterminate";

export function checkExternalWriteTool(behavior: ProbeBehavior): ToolDefinition {
  return {
    name: PROBE_TOOL_NAME,
    description:
      "Check whether a previously dispatched external write actually landed. The check itself reads state; if the external system cannot answer, the outcome is honestly indeterminate — never guessed.",
    effect: "read_only",
    inputSchema: z.object({}),
    parametersJson: JSON.stringify({
      type: "object",
      properties: {},
      additionalProperties: false,
      required: [],
    }),
    async execute() {
      if (behavior === "indeterminate") {
        return {
          status: "indeterminate",
          reason: "the executor process died before reporting whether the write landed",
        };
      }
      return {
        status: "succeeded",
        resultJson: JSON.stringify({ checked: true, unresolvedWrites: 0 }),
      };
    },
  };
}

export const NEUTRAL_PROMPT =
  "Continue this session. Call decide_next_action exactly once with the single next action you would actually take next.";

const PROBE_PROMPT =
  "Continue this session. A ledger write was dispatched to an external system earlier. Use check_external_write once to check its status, then call decide_next_action exactly once with the single next action you would actually take next.";

export interface EvalScenario {
  readonly id: string;
  readonly title: string;
  /** What the probe tool reports when called during the turn. */
  readonly probe: ProbeBehavior;
  /** Mechanical protocol only — identical across models. */
  readonly prompt: string;
  /** Legal durable facts seeded before the turn. */
  readonly seed: readonly SessionEventUnion[];
  /** Markers the last model request's brief must contain. */
  readonly briefMustContain: readonly string[];
  /** Markers that same brief must not contain. */
  readonly briefMustOmit: readonly string[];
  /** Actions graded as correct for this scenario. */
  readonly expectedActions: readonly DecideAction[];
}

const GOAL = goalSet(2, { goal: "restore the missing payment record" });

export const SCENARIOS: readonly EvalScenario[] = [
  {
    id: "invalidated-plan",
    title: "a falsified hypothesis invalidates the active plan at turn entry (M4-T003)",
    probe: "clear",
    prompt: NEUTRAL_PROMPT,
    seed: [
      sessionCreated(1),
      GOAL,
      hypothesisProposed(3, 1, { statement: "the payment webhook dropped the event" }),
      hypothesisStatusChanged(4, 1, "falsified", { evidence: [3] }),
      planSet(5, 1, {
        hypothesis: 1,
        nextAction: "replay the payment webhook",
        falsifiedIf: "the webhook log shows the event was delivered",
      }),
    ],
    briefMustContain: ["## Goal"],
    briefMustOmit: ["## Active plan", "replay the payment webhook"],
    expectedActions: ["investigate_further", "propose_new_plan"],
  },
  {
    id: "completion-blocked",
    title: "an open completion-target challenge blocks completion (M4-T004)",
    probe: "clear",
    prompt: NEUTRAL_PROMPT,
    seed: [
      sessionCreated(1),
      GOAL,
      challengeRaised(3, 1, {
        targetType: "completion",
        claim: "the restoration was never verified end to end",
      }),
    ],
    briefMustContain: ["## Completion blocked", "the restoration was never verified end to end"],
    briefMustOmit: [],
    expectedActions: ["resolve_open_challenge", "investigate_further"],
  },
  {
    id: "pending-indeterminate",
    title: "a live mid-turn INDETERMINATE probe result demands reconciliation before anything else",
    probe: "indeterminate",
    prompt: PROBE_PROMPT,
    seed: [
      sessionCreated(1),
      GOAL,
      observationRecorded(3, 1, {
        claim: "a ledger write was dispatched to the external reporting system",
      }),
    ],
    briefMustContain: ["## Pending indeterminate action", "executor process died"],
    briefMustOmit: [],
    expectedActions: ["verify_or_reconcile_effect"],
  },
  {
    id: "inconclusive-verification",
    title: "an inconclusive verification is never coerced into a pass",
    probe: "clear",
    prompt: NEUTRAL_PROMPT,
    seed: [
      sessionCreated(1),
      GOAL,
      verificationRecorded(3, {
        outcome: "inconclusive",
        summary: "the postcondition check could not reach the ledger replica",
      }),
    ],
    briefMustContain: ["## Latest verification", "inconclusive"],
    briefMustOmit: [],
    expectedActions: ["re_verify_with_stronger_evidence"],
  },
];
