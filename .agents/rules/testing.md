# Testing Rules

## Required by change type

| Change | Minimum test |
|---|---|
| pure contract/reducer | unit + property where applicable |
| Agent Loop | integration with ScriptedModel |
| Event schema | migration + replay fixture |
| Tool execution | integration + failure/UNKNOWN path |
| Capability | adversarial bypass test |
| Context builder | hard-bound + invariant retention test |
| Crash/recovery | fault injection + replay |

## Principles

- Reproduce before fixing when feasible.
- Test the user/system behavior, not only implementation details.
- Real LLM calls are eval/e2e, not Core correctness tests.
- No sleeps for synchronization in deterministic tests; use controllable fakes/signals.
- Every regression gets a permanent test at the lowest layer that reproduces it faithfully.
- Do not weaken assertions because an implementation changed unless the contract intentionally changed.
