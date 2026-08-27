# Skill: Fix Bug

## Procedure

1. Reproduce or establish concrete evidence of the bug.
2. Classify failure layer: contract, reducer/state, loop, provider, tool, persistence, capability, context, UI.
3. Write/identify the smallest regression test that fails for the real reason.
4. Form a root-cause hypothesis; separate it from observed facts.
5. Apply the smallest fix at the owning layer.
6. Run the regression test.
7. Run related integration/replay/fault tests depending on layer.
8. Review whether the bug exposed a missing invariant; if yes, add the invariant test rather than only patching the instance.
9. Do not clean unrelated code.

## Special questions

- Could the external side effect already have happened?
- Did `UNKNOWN` get collapsed into `FAILED`?
- Could replay/resume repeat the bug?
- Did a capability or context boundary contribute?
