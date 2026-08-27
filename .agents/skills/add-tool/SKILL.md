# Skill: Add or Change Tool

## Required design card

Before implementation answer:

```text
Name:
Purpose:
Input schema:
Output schema:
Effect class:
Required capability:
Scope:
Timeout semantics:
Cancellation semantics:
Idempotency:
Reconciliation:
Output bound/truncation:
Secrets/redaction:
Postcondition/verification:
```

## Procedure

1. Confirm a new Tool is necessary; prefer existing Tool composition when simpler.
2. Define schema/contract without provider-specific leakage.
3. Classify effect accurately.
4. Define authorization and path/network scope.
5. Implement execute with cancellation and bounded output.
6. Implement reconcile for reconcilable writes.
7. Add integration tests for success, normal failure, timeout and cancellation.
8. Add indeterminate/retry test for writes.
9. Add capability bypass tests.
10. Update tool subsystem docs.

A write Tool without an answer for "request may have succeeded but response was lost" is not ready to merge.
