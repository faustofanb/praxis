# ADR-0010: ModelProvider Port and ScriptedModel Contract v1

- Status: Accepted
- Date: 2026-08-28
- Owners: 樊彪
- Supersedes: none
- Related: docs/02-system-design.md §10/§22, ADR-0009, .praxis/milestones/M2.yaml

## Context

M2 needs the first agent loop against a model boundary without a real LLM in
correctness gates (M2 forbidden work). docs/02 §10 fixes the port shape
(`complete(request, signal): AsyncIterable<ModelEvent>`), the minimal
`ModelRequest`/`ModelEvent` sets, and the principles: Core never parses
provider-raw responses, adapters own retry, and provider API errors are not
automatically session failures. M2 failure acceptance additionally requires
explicit provider cancellation/timeout handling, so cancellation semantics
must be part of the contract, not an implementation accident. testkit must
offer a deterministic `ScriptedModelProvider` (docs/02 §4.6) for all
correctness tests.

## Decision

**contracts owns the port and its schemas** (zod, exact-pinned, no I/O):

- `ModelRequest`: `model`, normalized `messages` (system/user/assistant/tool
  discriminated by role; tool calls carried as `ToolCallRequest` with
  `argumentsJson` string — parsing owns to the tool runtime), optional
  `tools` (name + description + parameters-schema-as-JSON), optional
  `maxOutputTokens`, a bounded `providerOptions` escape hatch
  (`Record<string, unknown>`), optional `correlationId`.
- `ModelEvent`: discriminated union on `type` (camelCase stream events,
  distinct from the PascalCase durable vocabulary): `textDelta`,
  `toolCallStart`, `toolCallDelta`, `toolCallEnd`, `usage`, `completed`
  (finishReason: `stop` | `toolCalls` | `length`), `providerError`
  (normalized `{kind, retryable, message}`; kinds: `network`, `rateLimit`,
  `invalidRequest`, `auth`, `overloaded`, `timeout`, `unknown`).
- `ModelProvider` port: one method `complete(request, signal)` returning an
  async iterable of validated `ModelEvent`s.

**Cancellation is a stream-ending condition, not an exception.** Once the
`AbortSignal` aborts, the provider's iterator ends without emitting further
events and without emitting `completed`, and must not throw for clean
cancellation; adapters normalize underlying `AbortError`s accordingly. Core
detects cancellation deterministically: `signal.aborted && no completed
event`. Abnormal provider failures surface as a `providerError` event —
retry decisions belong to the adapter, session-fatal classification to Core.

**testkit owns `ScriptedModelProvider`**: constructed from a script (a list
of script items); replays model events in order with no clock, randomness,
or I/O; records every `ModelRequest` for assertions; fails loudly
(invariant-style throw) if the loop asks beyond the script; and supports
deterministic cancellation/error injection via special script items
(`waitForAbort`, which yields nothing until the signal aborts). No ID or
event generation lives in contracts (ADR-0009 rule).

## Consequences

### Positive

- Correctness gates run against a fully deterministic model boundary.
- Cancellation behavior is testable without timeouts/flaky clocks.
- Provider differences (stream chunking, error shapes) stop at the adapter;
  Core consumes one normalized event vocabulary.
- `providerOptions` escape hatch is typed as unvalidated `unknown` at the
  boundary, keeping contracts free of provider-specific schemas.

### Negative / trade-offs

- Two vocabularies to keep distinct (durable events vs stream events); the
  casing convention carries that distinction and must be taught.
- Async-iterable + AbortSignal is a harder testing surface than plain
  request/response; the testkit script items exist to compensate.
- `argumentsJson` defers tool-argument validation to the tool runtime, so
  malformed arguments are only caught there.

### Operational / migration impact

- Streaming is the only shape v1 offers; non-streaming adapters must
  synthesize a single-delta stream.
- The OpenAI adapter (M2) maps SSE chunks onto `ModelEvent` and owns retry
  for retryable `providerError` kinds.

## Alternatives considered

### Promise-based complete(request, signal): Promise<ModelResponse>

Simpler, but loses streaming (text deltas, incremental tool arguments) that
the ContextBuilder and tool proposal UX depend on, and makes cancellation
semantics mushier.

### Throwing CancellationError from the iterator on abort

Idiomatic JS, but forces every consumer into try/catch, races with
in-flight event delivery, and makes "did the model finish before the abort?"
ambiguous. A silently-terminating stream plus `signal.aborted` is
deterministic and total.

### Provider error as thrown ModelProviderError

Errors-as-events keeps the async iterable the single communication channel,
lets Core record the failure as a fact and decide (pause/retry/escalate), and
matches "provider API error ≠ automatic session failure".

## Verification

`tests/model-provider.test.ts` (contract schemas + cancellation laws) and
`tests/testkit-scripted-model.test.ts` (script order, request recording,
exhaustion failure, abort-before/abort-mid behavior, error injection) must
pass; M2-T004's integration loop will consume ScriptedModelProvider under
`mise run test:integration`.

## Revisit triggers

A second real provider whose stream cannot be mapped onto the v1
`ModelEvent` set without loss; measured need for server-side tool
execution; usage-based billing fields beyond input/output tokens.
