# ADR-0012: Epistemic Event Contracts — Goal/Observation/Hypothesis/Plan/Challenge/Verification Slice

- Status: Accepted
- Date: 2026-08-28
- Owners: Praxis core
- Supersedes: none
- Related: ADR-0009 (v1 session event contracts), ADR-0005 (deterministic core), docs/02 sections 5, 6.2, 7, 13-14, 16

## Context

docs/02 has carried the epistemic primitives on paper since the beginning: section 6.2 names nine
Goal/Epistemic events, section 5 sketches the domain types, section 7 names the derived-state
members (`goal`, `activePlan`, `hypotheses`, `openChallenges`, `lastVerification`), and sections
13-14 define what verification and challenge mean. None of it existed in code — M4-T001 closes
that gap as pure contract + state work, the same shape M3-T001 used for reconciliation. The
deferred behaviors (context projection M4-T002, falsification-driven invalidation M4-T003,
challenge-driven legal-next-action changes M4-T004) compose over these facts without changing
them, so the vocabulary has to be right first.

Three types were named but never defined anywhere: `ObservationSource`, `HardConstraint`,
`VerificationResult`. Two design holes needed a decision: docs/02 section 5.4 gives Plan a
`"completed"` status that no event in the section 6.2 vocabulary produces, and section 5.2's
`observedAt` has no home in an event-sourced payload where the envelope owns time.

## Decision

1. **Nine durable events joined to the session union** (`epistemic-events.ts`): `GoalSet`,
   `ObservationRecorded`, `HypothesisProposed`, `HypothesisStatusChanged`, `PlanSet`,
   `PlanInvalidated`, `ChallengeRaised`, `ChallengeResolved`, `VerificationRecorded`. Payloads
   parse from `unknown` at the boundary; `ChallengeRaised` is discriminated on `targetType` so
   hypothesis/plan targets carry branded ids and completion/policy targets stay free-form strings.
2. **Session-level facts, not turn actions**: every epistemic event requires an ACTIVE session and
   deliberately does NOT require an open turn. docs/02 section 16 makes Observation/Proposal the
   extension contribution channel; turn-scoping would lock the host and extensions out between
   turns. PAUSED still rejects — resume remains the only unlock, mirroring the ToolReconciled
   historical-fact law (ADR-0011).
3. **Reducer registries under the section 7 "at least includes" clause**: state grows
   `observations`, `plans`, `challenges` maps alongside the section 7 members because the laws
   need them — id uniqueness, terminal-target rejection, challenge target validation, and
   PlanSet's referenced-hypothesis check (fail-closed: a plan may not reference an unproposed
   hypothesis). `openChallenges` is maintained as the section 7 projection of the challenges map.
4. **Status laws**: `GoalSet` and `VerificationRecorded` are latest-wins; `PlanSet` supersedes the
   previous active plan; `PlanInvalidated` is legal only on the active plan; hypothesis status is
   monotonic (`proposed -> supported -> falsified | superseded`, with `proposed -> falsified |
   superseded` also legal; `falsified`/`superseded` terminal), the from-status is derived by
   replay and never trusted from the payload, and status-change evidence files under `support`
   toward `supported` and `conflicts` toward `falsified` (supersession carries a reason, not
   evidence); `ChallengeResolved` is legal only while open, outcome `accepted | rejected |
   resolved` with a required reason.
5. **Honest shapes**: `VerificationResult.outcome` includes `inconclusive` — an unverifiable
   check is recorded as such, never coerced to `failed` (same law as ToolIndeterminate).
   `Observation.observedAt` comes from the envelope's `occurredAt`, never from the payload.
   `HardConstraint` is `{ description }` — constraints have no id until a policy needs one.
6. **Plan drops `"completed"` in v1**: the vocabulary has no event that produces it; plan
   completion is a session-level fact (`SessionCompleted`). A dead discriminator value would
   break the totality discipline. docs/02 section 5.4 is updated accordingly.
7. **Evidence refs are claims, not registry entries**: `evidenceEventIds` are schema-validated
   references to stream history; the reducer does not index historical event ids, so a forged ref
   is a stream-authoring defect surfaced by replay tooling, not a transition error. The ids the
   reducer owns (observations, hypotheses, plans, challenges) are registry-enforced.

## Consequences

### Positive

- The M4 runtime behaviors have a fact-shaped API to build on, and the reducer stays the single
  state manager — the M4-T002 projection will read state instead of maintaining a second fold.
- Falsification is a fact, invalidation is a decision: the reducer never auto-invalidates a plan
  when its hypothesis is falsified (pinned by the `epistemic-v1` fixture checkpoint at seq 20);
  M4-T003 owns that policy explicitly instead of it hiding in a fold.
- Old streams stay loadable: the union only grew, pre-M4 fixtures fold unchanged.

### Negative / trade-offs

- The state shape grows five members and the vocabulary gains nine types; reducers stay total but
  consumers of `DerivedSessionState` see new required (always-present, possibly empty) fields.
- `PlanSet` with a dangling hypothesis reference is rejected outright — stricter than a
  lazy-resolution design; a runtime that wants to plan before proposing must order its facts.

### Operational / migration impact

- None at storage level (additive schema, no store change — the store validates through the
  public union). Replay of pre-M4 streams yields the new fields as empty collections.

## Alternatives considered

### Keep `"completed"` as a PlanStatus for forward compatibility

Rejected: a status no event can produce is untestable law and invites schema drift. If a
PlanCompleted fact is ever needed, the union grows then, and supersession already covers the
"stopped being the active plan" semantics.

### Turn-scoped epistemic events

Rejected: model proposals happen mid-turn, but host/user observations and extension contributions
happen between turns; scoping to the open turn would make the honest recording path illegal at
the exact moment it is needed (and would repeat the structural impossibility ADR-0011 fixed for
post-pause reconciliation).

### Reducer-validated evidence refs (event-id index in state)

Rejected: it would grow state by every event id for one cross-field check the schema already
types; forgery is detectable by replay tooling against the actual stream.

## Verification

- `tests/reducer-epistemic.test.ts`: full-slice fold, open-turn/between-turns legality,
  EMPTY/PAUSED/COMPLETED rejection, id-uniqueness and unknown-target laws, hypothesis status
  matrix incl. terminals, plan supersede/invalidate, challenge target validation and resolution,
  verification latest-wins with honest inconclusive.
- `tests/fixtures/replay/epistemic-v1.json` + `tests/replay/replay.test.ts`: fixture loads through
  the public schema, folds deterministically; the seq-20 checkpoint pins
  falsification-without-auto-invalidation.
- `tests/property/contracts-events.property.test.ts`: epistemic payloads round-trip; vocabulary
  rejection now filters against the full v1 vocabulary; `to: "proposed"`, `outcome: "open"`,
  `outcome: "maybe"` all rejected at the boundary.
- Pre-existing fixtures (session-lifecycle-v1, session-tool-lifecycle-v1,
  agent-loop-recovery-v1, tool-reconciliation-v1) still load and fold.

## Revisit triggers

- M4-T002 needs bounded observation projection (e.g. max active observations): bound the
  projection, never the event stream.
- M4-T004 needs challenge-targeted completion blocking: add the law to SessionCompleted's
  preconditions — do not widen ChallengeRaised.
- A policy needs addressable constraints (`HardConstraint` ids) for `policy`-target challenges.
- A hypothesis needs supersession linkage (`supersededBy`) rather than a free-form reason.
