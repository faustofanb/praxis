import { z } from "zod";
import { sessionEventSchema } from "../envelope";
import {
  ChallengeOutcomeSchema,
  GoalStateSchema,
  ObservationCoreSchema,
  VerificationOutcomeSchema,
} from "../epistemic/epistemic";
import { ChallengeIdSchema, EventIdSchema, HypothesisIdSchema, PlanIdSchema } from "../ids";

/**
 * v1 durable event vocabulary: the Goal/Epistemic slice (docs/02 sections
 * 5, 6.2, 13-14, ADR-0012). These are session-level facts on the host/
 * extension contribution channel (docs/02 section 16): they require a live
 * session but not an open turn — turn-scoping would lock the host out
 * between turns. Evidence refs are schema-validated claims about stream
 * history; the reducer enforces the id registries it keeps, not event
 * existence. Who appends these facts and when is runtime work (M4-T002+);
 * here they only become foldable.
 */

export const GOAL_SET = "GoalSet";
export const OBSERVATION_RECORDED = "ObservationRecorded";
export const HYPOTHESIS_PROPOSED = "HypothesisProposed";
export const HYPOTHESIS_STATUS_CHANGED = "HypothesisStatusChanged";
export const PLAN_SET = "PlanSet";
export const PLAN_INVALIDATED = "PlanInvalidated";
export const CHALLENGE_RAISED = "ChallengeRaised";
export const CHALLENGE_RESOLVED = "ChallengeResolved";
export const VERIFICATION_RECORDED = "VerificationRecorded";

export const EPISTEMIC_EVENT_TYPES = [
  GOAL_SET,
  OBSERVATION_RECORDED,
  HYPOTHESIS_PROPOSED,
  HYPOTHESIS_STATUS_CHANGED,
  PLAN_SET,
  PLAN_INVALIDATED,
  CHALLENGE_RAISED,
  CHALLENGE_RESOLVED,
  VERIFICATION_RECORDED,
] as const;
export type EpistemicEventType = (typeof EPISTEMIC_EVENT_TYPES)[number];

export const GoalSetPayloadSchema = GoalStateSchema;
export const GoalSetEventSchema = sessionEventSchema(GOAL_SET, GoalSetPayloadSchema);
export type GoalSetEvent = z.infer<typeof GoalSetEventSchema>;

export const ObservationRecordedPayloadSchema = ObservationCoreSchema;
export const ObservationRecordedEventSchema = sessionEventSchema(
  OBSERVATION_RECORDED,
  ObservationRecordedPayloadSchema,
);
export type ObservationRecordedEvent = z.infer<typeof ObservationRecordedEventSchema>;

export const HypothesisProposedPayloadSchema = z.object({
  hypothesisId: HypothesisIdSchema,
  statement: z.string().min(1),
  support: z.array(EventIdSchema).optional(),
  conflicts: z.array(EventIdSchema).optional(),
});
export const HypothesisProposedEventSchema = sessionEventSchema(
  HYPOTHESIS_PROPOSED,
  HypothesisProposedPayloadSchema,
);
export type HypothesisProposedEvent = z.infer<typeof HypothesisProposedEventSchema>;

/**
 * `to` never carries "proposed": proposals are birth facts, and the from-status
 * is derived by replay instead of trusted from the payload.
 */
export const HYPOTHESIS_STATUS_CHANGES = ["supported", "falsified", "superseded"] as const;
export const HypothesisStatusChangeSchema = z.enum(HYPOTHESIS_STATUS_CHANGES);
export type HypothesisStatusChange = (typeof HYPOTHESIS_STATUS_CHANGES)[number];

export const HypothesisStatusChangedPayloadSchema = z.object({
  hypothesisId: HypothesisIdSchema,
  to: HypothesisStatusChangeSchema,
  evidenceEventIds: z.array(EventIdSchema).optional(),
  reason: z.string().min(1).optional(),
});
export const HypothesisStatusChangedEventSchema = sessionEventSchema(
  HYPOTHESIS_STATUS_CHANGED,
  HypothesisStatusChangedPayloadSchema,
);
export type HypothesisStatusChangedEvent = z.infer<typeof HypothesisStatusChangedEventSchema>;

export const PlanSetPayloadSchema = z.object({
  planId: PlanIdSchema,
  goalRef: z.string().min(1),
  focus: z.string().min(1).optional(),
  hypothesisId: HypothesisIdSchema.optional(),
  nextAction: z.string().min(1),
  falsifiedIf: z.string().min(1).optional(),
});
export const PlanSetEventSchema = sessionEventSchema(PLAN_SET, PlanSetPayloadSchema);
export type PlanSetEvent = z.infer<typeof PlanSetEventSchema>;

export const PlanInvalidatedPayloadSchema = z.object({
  planId: PlanIdSchema,
  reason: z.string().min(1),
});
export const PlanInvalidatedEventSchema = sessionEventSchema(
  PLAN_INVALIDATED,
  PlanInvalidatedPayloadSchema,
);
export type PlanInvalidatedEvent = z.infer<typeof PlanInvalidatedEventSchema>;

export const ChallengeRaisedPayloadSchema = z.discriminatedUnion("targetType", [
  z.object({
    challengeId: ChallengeIdSchema,
    targetType: z.literal("hypothesis"),
    targetId: HypothesisIdSchema,
    claim: z.string().min(1),
    evidenceEventIds: z.array(EventIdSchema),
  }),
  z.object({
    challengeId: ChallengeIdSchema,
    targetType: z.literal("plan"),
    targetId: PlanIdSchema,
    claim: z.string().min(1),
    evidenceEventIds: z.array(EventIdSchema),
  }),
  z.object({
    challengeId: ChallengeIdSchema,
    targetType: z.literal("completion"),
    targetId: z.string().min(1),
    claim: z.string().min(1),
    evidenceEventIds: z.array(EventIdSchema),
  }),
  z.object({
    challengeId: ChallengeIdSchema,
    targetType: z.literal("policy"),
    targetId: z.string().min(1),
    claim: z.string().min(1),
    evidenceEventIds: z.array(EventIdSchema),
  }),
]);
export const ChallengeRaisedEventSchema = sessionEventSchema(
  CHALLENGE_RAISED,
  ChallengeRaisedPayloadSchema,
);
export type ChallengeRaisedEvent = z.infer<typeof ChallengeRaisedEventSchema>;

export const ChallengeResolvedPayloadSchema = z.object({
  challengeId: ChallengeIdSchema,
  outcome: ChallengeOutcomeSchema,
  reason: z.string().min(1),
});
export const ChallengeResolvedEventSchema = sessionEventSchema(
  CHALLENGE_RESOLVED,
  ChallengeResolvedPayloadSchema,
);
export type ChallengeResolvedEvent = z.infer<typeof ChallengeResolvedEventSchema>;

export const VerificationRecordedPayloadSchema = z.object({
  outcome: VerificationOutcomeSchema,
  summary: z.string().min(1),
  evidenceEventIds: z.array(EventIdSchema),
});
export const VerificationRecordedEventSchema = sessionEventSchema(
  VERIFICATION_RECORDED,
  VerificationRecordedPayloadSchema,
);
export type VerificationRecordedEvent = z.infer<typeof VerificationRecordedEventSchema>;

export const EPISTEMIC_EVENT_SCHEMAS = [
  GoalSetEventSchema,
  ObservationRecordedEventSchema,
  HypothesisProposedEventSchema,
  HypothesisStatusChangedEventSchema,
  PlanSetEventSchema,
  PlanInvalidatedEventSchema,
  ChallengeRaisedEventSchema,
  ChallengeResolvedEventSchema,
  VerificationRecordedEventSchema,
] as const;
