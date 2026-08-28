# ADR-0011: Tool Reconciliation Contract — ToolReconciled Event, ReconciliationOutcome, and Per-Effect Retry Policy

- Status: Accepted
- Date: 2026-08-28
- Owners: Praxis core
- Supersedes: none
- Related: ADR-0006 (tool effect classes), ADR-0003 (event store), docs/02 sections 8 and 17

## Context

ADR-0006 made indeterminate tool outcomes first-class, and docs/02 section 8.2 always drew the
reconciliation edge (`INDETERMINATE -> reconcile -> SUCCEEDED | FAILED | INDETERMINATE`), but until
M3-T001 the code had no carrier for it: `ToolIndeterminate` was terminal in the reducer, the event
vocabulary listed `ToolReconciled` without a schema, and `ToolDefinition` had no `reconcile`. Two
runtime rules from docs/02 section 17 ("never assume an unexecuted tool from a missing result
event"; "never blind-retry an INDETERMINATE non-idempotent write") existed only as prose — nothing
in code decided, per effect class, what recovery may do.

## Decision

1. **`ToolReconciled` durable event** with a payload discriminated on `outcome`
   (`succeeded`+`resultJson` | `failed`+`message` | `indeterminate`+`reason`). Legal only from
   `INDETERMINATE`; legal repeatedly while still indeterminate (escalate now, settle later);
   `SUCCEEDED`/`FAILED` reached by reconciliation are terminal exactly like those reached by
   execution. The derived snapshot records `reconciliationCount` (attempts, not outcomes).
2. **`ReconciliationOutcome` + optional `reconcile` on the tool port**, mirroring
   `ToolExecutionOutcome`'s epistemics: `succeeded`/`failed` assert the external effect did/did
   not happen; anything short of proof stays `indeterminate`. Reconciliation verifies — it must
   not perform new external effects. It receives the same parsed input as `execute`.
3. **A deterministic per-effect retry policy table in core** (`retryPolicyForEffect`):
   `read_only`/`idempotent_write` → `safe_to_repeat`; `reconcilable_write` →
   `repeat_only_after_reconciled_absence`; `non_idempotent_write` → `never_repeat`. Total over the
   effect vocabulary by construction (a new class breaks compilation).
4. **Registration enforcement of ADR-0006**: `validateToolDefinitions` (run fail-closed in
   `runTurn` before any execution) rejects a `reconcilable_write` without `reconcile` and
   duplicate names. `non_idempotent_write` may define `reconcile` — it settles facts for
   escalation and never unlocks repetition.

## Consequences

### Positive

- INDETERMINATE stops being a dead end: recovery (M3-T004) has a fact-shaped API to settle it,
  and the model sees the settled outcome as an appended tool fact (ContextBuilder), never a
  rewritten one.
- "Never blind-retry" is now a total, typed function rather than prose; enforcement cannot depend
  on model or tool-author self-discipline.
- Old streams stay loadable: the union only grew, and `reconciliationCount` defaults to 0 through
  the ToolProposed fold — no migration.

### Negative / trade-offs

- The vocabulary gains one event type and the state machine gains a repeatable edge; reducers must
  treat reconciliation-settled terminals as final.
- `reconcile` on `non_idempotent_write` is legal but cannot unlock re-execution — tool authors may
  find that stricter than intuition.

### Operational / migration impact

- None at storage level (additive schema). Derived-state consumers see a new optional field and a
  new event type.

## Alternatives considered

### Reuse ToolSucceeded/ToolFailed with a `reconciled` flag

Hides whether the fact came from execution or verification, and pollutes two stable payloads for
one feature. Rejected: facts should name how they became known.

### Let reconcile live only in tool adapters (no durable event)

Then settled outcomes would be invisible to replay and the conversation projection — recovery
would diverge between live and replayed sessions, breaking ADR-0005 determinism. Rejected.

### A separate RECONCILED status

docs/02 section 8.2 settles into the existing terminals on purpose: what matters downstream is
the outcome, not how it was learned. A fifth status would touch every status consumer for no new
information. Rejected.

## Verification

- `tests/reducer-tools.test.ts`: all three settle variants, repeat-while-indeterminate,
  every illegal source status, closed-turn/PAUSED rejection, terminals never resurrect.
- `tests/fixtures/replay/tool-reconciliation-v1.json` + `tests/replay/replay.test.ts`: fixture
  loads through the public schema, folds deterministically, checkpoints stay honestly INDETERMINATE.
- `tests/property/tool-events.property.test.ts`: every payload variant round-trips.
- `tests/effect-policy.test.ts`: table totality and ADR-0006 registration enforcement.
- Pre-existing fixtures (session-lifecycle-v1, agent-loop-recovery-v1) still load and fold.

## Revisit triggers

- M3-T004 recovery orchestration needs richer reconciliation facts (e.g. which strategy produced
  the outcome, evidence payloads) — extend the payload, do not fork the event.
- A real tool cannot express its verification in the `reconcile(context, input)` shape.
- Reconciliation needs to run while the session is PAUSED (today it requires ACTIVE + the
  execution's turn open).
