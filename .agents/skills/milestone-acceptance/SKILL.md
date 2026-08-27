# Skill: Milestone Acceptance

## Trigger

Use when all tasks of the current milestone are accepted (or explicitly
dropped with recorded reasons) and the milestone is ready for exit evaluation.
Norms: `docs/05-acceptance-strategy.md`, machine contract
`.praxis/milestones/<Mn>.yaml`, record `docs/acceptance/<Mn>.md`.

## Procedure

1. Collect evidence at the exact commit under acceptance:
   - machine gate summary (`ai:verify` output or CI run on that commit);
   - scenario reports (commands, environment, output, commit SHA);
   - failure-acceptance reports (injected error → gate actually FAILed).
2. Verify gate names against `.praxis/quality-gates.yaml`; a milestone
   contract referencing a nonexistent gate is a defect in the contract.
3. Answer the design–implementation consistency questions from
   `docs/07-architecture-conformance.md` §6.
4. Fill `docs/acceptance/<Mn>.md`: check Machine Gates / Scenario / Failure
   items, reference evidence artifacts, keep Exit Decision `PENDING`.
5. Report state as acceptance-ready. The implementing AI MUST NOT:
   - fill `Accepted by` with itself;
   - flip `.praxis/milestones/<Mn>.yaml` `status` to `accepted`;
   - promote `current_milestone` in `.praxis/state.yaml`.
6. Milestone promotion (status flip + `state.yaml` advance) is performed only
   by a human or the independent reviewer role defined in
   `docs/08-ai-model-development-strategy.md`, after reviewing the evidence.

## Stop conditions

Stop and return the milestone to rework if:

- any layer lacks reproducible evidence;
- a gate passes only after test/config weakening;
- failure-acceptance shows a gate that cannot fail.
