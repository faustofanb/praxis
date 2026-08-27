# Skill: Architecture Change

## Trigger

Use when normal implementation hits one of the stop conditions in
`docs/07-architecture-conformance.md` §4: a package boundary cannot satisfy
the requirement, a Port lacks necessary semantics, the durable event
vocabulary must change, adapter-specific capability must enter Core, or a v1
non-goal must be crossed.

## Procedure

1. Stop implementation immediately. Record the observed contradiction with
   file/line evidence in the Task Contract.
2. Draft alternatives — at minimum: (a) stay inside current boundaries,
   (b) extend an existing seam, (c) change the boundary. Say why (a) and (b)
   fail before proposing (c).
3. Write the ADR from `docs/decisions/ADR_TEMPLATE.md`: context, decision,
   consequences, rejected alternatives.
4. Get approval (human or independent reviewer per `docs/08`) before any
   code changes.
5. Update, in this order: ADR → `.praxis/architecture.yaml` →
   `docs/02-system-design.md` → affected subsystem docs → code/tests.
6. Extend the conformance net: any architecture-related P0/P1 bug or newly
   allowed dependency becomes a `check-architecture` rule or test, not just
   documentation.
7. Resume the originating task via `execute-task`.

## Forbidden

- Changing code first and editing architecture docs to match afterwards;
- silently adding a dependency to `core` (requires
  `adr_required_for: add_dependency_to_core`);
- resolving a boundary conflict by weakening an invariant in `AGENTS.md` or
  `.praxis/project.yaml`.
