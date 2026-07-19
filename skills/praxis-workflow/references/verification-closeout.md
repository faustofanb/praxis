# Verification And Closeout

Use this reference before final delivery, especially after interruptions or context compaction.

## Resume Discipline

After interruption, compaction or handoff:

1. Bind to the newest user request.
2. Run a minimal workspace status check before editing.
3. Re-read the local Praxis entry files needed for the next action.
4. Discard stale plan steps that conflict with the newest request.
5. Verify or explain why verification was not run before final delivery.

## Verification Levels

- L0: changed-file boundary plus syntax/parser or equivalent focused check; default for eligible `quick` tasks.
- L1: project-focused unit/contract tests and standard project verification; default for ordinary requirement work.
- L2: migration/database checks, broader regression, delivery readiness and explicitly authorized independent Quality review; required for high-risk boundaries.

Verification level comes from the extension manifest and task policy. Changed files can only raise the level: database, migration, permission, report, shared-contract or cross-project paths require formal mode and L2. Independent Quality review is never an automatic ritual; run it only for L2/high-risk work or explicit user authorization.

## Evidence

Final output should include the meaningful evidence for the task:

- files changed;
- commands run;
- tests or checks passed;
- checks skipped and why;
- any waiver reason and residual risk.

For delivery or closeout work, also include confirmed commits, excluded commits,
candidate audit evidence and confirmations still required.

Do not claim completion when required evidence is missing. Report the concrete blocker instead.
