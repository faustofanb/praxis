# Skill: Add Durable Event

## Gate questions

1. Is this an already-observed fact rather than intent/debug telemetry?
2. Must it survive restart/replay?
3. Which DerivedState field changes because of it?
4. Can an existing Event express the same fact?
5. Is payload bounded and serializable?
6. How will old sessions be read?

## Procedure

1. Add/modify schema in `contracts`.
2. Add reducer handling with exhaustive switch.
3. Add unit/property tests.
4. Add migration/fixture handling if schema compatibility changes.
5. Add replay test.
6. Update system/subsystem docs.

Do not create durable Events only because UI/debugging wants a notification; telemetry/UI events belong elsewhere unless they change durable Agent truth.
