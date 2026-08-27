# Skill: Review Change

Review by risk, not style volume.

## P0/P1 pass

Look for:

- duplicate/non-idempotent side effects;
- incorrect success after verifier/tool/store failure;
- capability bypass or indirect delegated capability;
- secret leakage into context/telemetry/event payload;
- illegal state transitions;
- replay causing effects;
- unbounded context/queue/output;
- schema migration breakage;
- Core importing adapter/provider implementation;
- missing integration/fault test for Agent behavior.

## P2/P3 pass

Then inspect maintainability, performance and style.

Only report findings with a concrete failure path or violated documented rule. Avoid speculative redesign during normal review.
