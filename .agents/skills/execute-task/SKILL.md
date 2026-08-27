# Skill: Execute Task

## Trigger

Use for any non-trivial development task driven by a Task Contract in
`.praxis/tasks/` (the mandatory flow is defined in
`docs/06-ai-development-control-plane.md` §5).

## Procedure

1. `mise run ai:brief` — read the bounded project context; do not rebuild it
   from memory.
2. Discover: inspect code, tests, contracts and dependencies cited by the
   task's `evidence`. Record observed/expected/difference in the Task
   Contract before coding.
3. `mise run ai:plan -- .praxis/tasks/<id>.yaml` — only a schema-valid
   contract can enter `PLAN_READY`. Fix the contract, not the validator.
4. Implement strictly within `scope.allowed_paths`. If evidence shows the
   scope must expand, update the Task Contract first, then continue
   (`ai-policy: expand_scope_on_evidence`).
5. Add the tests demanded by the change type (see AGENTS.md Tests).
6. `mise run ai:guard` — resolve every scope/architecture violation before
   proceeding.
7. `mise run ai:verify` — all derived gates must genuinely PASS. Never weaken
   a gate or test to make it pass.
8. `mise run ai:accept` — low-risk tasks are machine-accepted; risk D/E,
   ADR-requiring or dependency-introducing tasks only reach
   `ACCEPTANCE_READY` for independent/human sign-off.
9. `mise run ai:handoff` — persist the handoff artifact before ending the
   session.

## Stop conditions

Stop and re-plan if:

- the task requires touching `forbidden_paths` or v1 non-goals;
- implementation evidence contradicts the planned design (ADR territory —
  switch to `architecture-change`);
- `ai:verify` fails twice for the same root cause — the hypothesis may be
  wrong; record it in the contract's `falsified_if` terms;
- prerequisites of the task are not actually accepted.
