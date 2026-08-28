import { z } from "zod";
import {
  ChallengeIdSchema,
  EventIdSchema,
  HypothesisIdSchema,
  ObservationIdSchema,
  PlanIdSchema,
  ToolExecutionIdSchema,
} from "../ids";

/**
 * Epistemic domain vocabulary (docs/02 sections 5 and 13, ADR-0012).
 * Observations are recorded material, not verified claims; hypotheses carry
 * evidence refs instead of model-invented confidence; a plan is the current
 * action assumption with its own falsification condition; a challenge is a
 * first-class fact that does not require a critic agent. Status transition
 * legality is enforced by the Core reducer, not here. The reducer never reads
 * model-generated floats as truth: no confidence field exists to depend on.
 */

/** Constraint that no local metric may override (docs/02 section 5.1). */
export const HardConstraintSchema = z.object({
  description: z.string().min(1),
});
export type HardConstraint = z.infer<typeof HardConstraintSchema>;

export const GoalStateSchema = z.object({
  need: z.string().min(1).optional(),
  goal: z.string().min(1),
  constraints: z.array(HardConstraintSchema),
  strategy: z.string().min(1).optional(),
  mission: z.string().min(1).optional(),
});
export type GoalState = z.infer<typeof GoalStateSchema>;

/** Where an observation's material came from (docs/02 section 5.2). */
export const ObservationSourceSchema = z.discriminatedUnion("kind", [
  z.object({ kind: z.literal("tool"), toolExecutionId: ToolExecutionIdSchema }),
  z.object({ kind: z.literal("user") }),
  z.object({ kind: z.literal("system"), detail: z.string().min(1) }),
]);
export type ObservationSource = z.infer<typeof ObservationSourceSchema>;

/** Payload shape of an observation; state adds observedAt from the envelope. */
export const ObservationCoreSchema = z.object({
  observationId: ObservationIdSchema,
  source: ObservationSourceSchema,
  claim: z.string().min(1),
  evidenceEventIds: z.array(EventIdSchema),
});
/**
 * State entity the reducer projects: the recorded fact plus the envelope time
 * of the ObservationRecorded event that produced it. Envelope owns time, so
 * the payload never carries it.
 */
export type Observation = z.infer<typeof ObservationCoreSchema> & { observedAt: number };

export const HYPOTHESIS_STATUSES = ["proposed", "supported", "falsified", "superseded"] as const;
export type HypothesisStatus = (typeof HYPOTHESIS_STATUSES)[number];
export const HypothesisStatusSchema = z.enum(HYPOTHESIS_STATUSES);

export const HypothesisSchema = z.object({
  hypothesisId: HypothesisIdSchema,
  statement: z.string().min(1),
  status: HypothesisStatusSchema,
  support: z.array(EventIdSchema),
  conflicts: z.array(EventIdSchema),
});
export type Hypothesis = z.infer<typeof HypothesisSchema>;

/**
 * v1 drops docs/02 section 5.4's "completed": the section 6.2 vocabulary has
 * no event that produces it — plan completion is a session-level fact
 * (SessionCompleted). A discriminator value with no producing event would
 * break totality of the transition table.
 */
export const PLAN_STATUSES = ["active", "invalidated", "superseded"] as const;
export type PlanStatus = (typeof PLAN_STATUSES)[number];
export const PlanStatusSchema = z.enum(PLAN_STATUSES);

export const PlanSchema = z.object({
  planId: PlanIdSchema,
  goalRef: z.string().min(1),
  focus: z.string().min(1).optional(),
  hypothesisId: HypothesisIdSchema.optional(),
  nextAction: z.string().min(1),
  falsifiedIf: z.string().min(1).optional(),
  status: PlanStatusSchema,
});
export type Plan = z.infer<typeof PlanSchema>;

export const CHALLENGE_TARGET_TYPES = ["hypothesis", "plan", "completion", "policy"] as const;
export type ChallengeTargetType = (typeof CHALLENGE_TARGET_TYPES)[number];
export const ChallengeTargetTypeSchema = z.enum(CHALLENGE_TARGET_TYPES);

export const CHALLENGE_STATUSES = ["open", "accepted", "rejected", "resolved"] as const;
export type ChallengeStatus = (typeof CHALLENGE_STATUSES)[number];
export const ChallengeStatusSchema = z.enum(CHALLENGE_STATUSES);

/** Terminal outcomes a resolution may record; "open" only exists at birth. */
export const CHALLENGE_OUTCOMES = ["accepted", "rejected", "resolved"] as const;
export type ChallengeOutcome = (typeof CHALLENGE_OUTCOMES)[number];
export const ChallengeOutcomeSchema = z.enum(CHALLENGE_OUTCOMES);

export const ChallengeSchema = z.object({
  challengeId: ChallengeIdSchema,
  targetType: ChallengeTargetTypeSchema,
  targetId: z.string().min(1),
  claim: z.string().min(1),
  evidenceEventIds: z.array(EventIdSchema),
  status: ChallengeStatusSchema,
});
export type Challenge = z.infer<typeof ChallengeSchema>;

/**
 * Verification facts (docs/02 section 13). "inconclusive" is first-class:
 * an unverifiable check is recorded as such, never coerced to "failed".
 */
export const VERIFICATION_OUTCOMES = ["passed", "failed", "inconclusive"] as const;
export type VerificationOutcome = (typeof VERIFICATION_OUTCOMES)[number];
export const VerificationOutcomeSchema = z.enum(VERIFICATION_OUTCOMES);

export const VerificationResultSchema = z.object({
  outcome: VerificationOutcomeSchema,
  summary: z.string().min(1),
  evidenceEventIds: z.array(EventIdSchema),
});
export type VerificationResult = z.infer<typeof VerificationResultSchema>;
