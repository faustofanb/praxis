# ADR-0013: Extension Seams v1 — Deny-Only Tool Hooks, Instance Host, Failure Policy Riding Crash Recovery

- Status: Accepted
- Date: 2026-08-29
- Owners: Praxis core
- Supersedes: none
- Related: ADR-0005 (deterministic core), ADR-0007 (capability enforcement is Core), ADR-0006 (effect classes), docs/02 sections 17, 19; docs/03 M6

## Context

docs/02 section 19 has specified the extension surface on paper since the design doc was written:
eight hooks (`onTurnStart`, `contributeContext`, `beforeModel`, `afterModel`, `beforeTool`,
`afterTool`, `onEvent`, `onTurnEnd`) plus four constraints — the hook count stays bounded, an
extension cannot bypass CapabilityPolicy, extension-owned durable state lives outside Core's
store, and failure blocking must be explicit per hook contract. None of it existed in code.

M6 needs the seams before it needs any extension: M6-T002 (telemetry observer) and M6-T003
(context/tool sample) must land without touching `packages/core` again, and M6-T004 audits unload
and failure isolation. That means the Core-side invocation points all land once, in this decision.
The design question was not "which hooks" (section 19 fixed that) but how to make every M6
acceptance property structural — true by construction, not by extension-author discipline:
`extension cannot bypass core capability checks`, `unload leaves no residue`, `a failing
extension never invents a second recovery path`, and `extension context stays inside the bounded
context law`.

## Decision

1. **Exactly the eight section-19 hooks, all optional** (`packages/contracts/src/extensions.ts`).
   Hooks may be sync or async; every hook context is a read-only view carrying ids and frozen
   request/result data — never the store, never the folded state, never anything mutable.
   `EXTENSION_HOOKS` pins the count; growing it is an ADR, not a feature PR.

2. **`ToolHookDecision` is deny-only by type**: `{ decision: "deny"; reason: string }` or nothing.
   "Allow" is unrepresentable in the type, and a forged non-deny return from `beforeTool` is a
   contract violation that throws regardless of the extension's failure policy. The
   M6 failure-acceptance property (`extension cannot bypass core capability checks`) is therefore
   a type invariant, not a runtime check that depends on extension goodwill.

3. **`beforeTool` composes AFTER the authorizer, before `ToolAuthorized`** (ADR-0007 order
   preserved): the authorizer/capability decision stays the sole grant path; extensions only ever
   add vetoes. A deny appends an explicit `ToolRejected` whose reason cites the extension
   (`extension <name> denied: <reason>`); the call never executes. When the authorizer rejects,
   extensions are not even consulted. First deny in registration order wins.

4. **Per-extension failure policy, declared at registration**: `'isolate'` (default — the error
   is swallowed and the hook contributes nothing; telemetry-grade observers cannot break a turn)
   and `'fail_closed'` (the error is wrapped in `ExtensionHookError` with extension and hook
   names, then rethrown). A fail_closed crash is an ordinary mid-turn crash: the persisted prefix
   folds legally and the EXISTING section-17 recovery machinery resumes the session. There is no
   extension-specific failure path. Return-shape violations (non-array `contributeContext`,
   non-deny `beforeTool`) are contract violations and throw under both policies.

5. **Instance-scoped host, no module state** (`packages/core/src/extensions/host.ts`):
   `createExtensionHost()` keeps all state in its closure; `register` validates
   (`validatePraxisExtension`: name rules, function-shaped hooks, policy domain) and rejects
   duplicate names; `unload(name)` removes immediately — later invocations skip the extension,
   and dropping the host object drops all residue. AGENTS.md's no-mutable-module-globals law
   makes the unload guarantee hold by construction.

6. **Invocation points, wired once into Core** (run-turn.ts, tool-runtime.ts, builder.ts):

   | Hook | Fires | Notes |
   |---|---|---|
   | `onTurnStart` | after the `TurnStarted` append, only in the invocation that opened the turn | a resumed open turn does not refire |
   | `contributeContext` | every model step, before context assembly | host stamps each fragment's `source` with the extension's own name — one extension cannot render sections under another's name |
   | `beforeModel` / `afterModel` | immediately around `model.complete`, after the `ModelRequestStarted` append / after the stream settles | request is a frozen view; result is the normalized `completed \| providerError \| endedSilently` |
   | `onEvent` | after every durable append succeeds, once per event, via an observing EventStore decorator | open-turn tracking derived purely from `TurnStarted`/`TurnCompleted` facts; observe-only — extensions append nothing |
   | `beforeTool` / `afterTool` | after authorizer approval, before `ToolAuthorized` / on every terminal settle including `REJECTED` | see decisions 2-3 |
   | `onTurnEnd` | on every `TurnOutcome` path (completed/paused/cancelled) | NOT on crashes — a crashed turn has no outcome and stays dangling for recovery |

7. **Context fragments enter through the M5-T001 composition law, not around it**: fragments
   render as deterministic `## Extension: <source>` sections appended after the epistemic brief
   in the single system fragment. Each section is individually fitted (truncation marker) to
   `maxFragmentBytes` — extension text is compactable content — and a composed system fragment
   that still exceeds the cap fails closed with `ContextBudgetExceededError`, exactly like an
   oversize brief. Fragments can never displace the brief's non-compactable sections.

8. **Zero-extension identity**: with no host (or an empty one) registered, `runTurn` and
   `executeToolCall` produce byte-identical event streams and model requests. The pre-task suite
   passing unedited is part of this task's evidence.

## What v1 deliberately refuses (per section 19, "not an Event Bus framework")

- **No extension-owned tool registration hook.** Tools are application-owned `deps` in v1;
  extensions observe and veto the tool lifecycle (`beforeTool`/`afterTool`) but cannot inject new
  `ToolDefinition`s. docs/03 M6's "tool registration" bullet is satisfied by the tool-lifecycle
  seam plus an application wiring its own tools — if a future task wants hook-driven tool
  injection, that is a new ADR amending this one.
- **No extension durable state inside Core's store.** `onEvent` is read-only; an extension that
  needs durable memory writes Events or its own explicit storage, outside these seams.
- **No request mutation.** `beforeModel` sees a frozen view; v1 has no rewriting seam. Context
  contribution is additive and capped; it is the only way an extension touches the prompt.
- **No cross-extension coordination, priorities, or conditional ordering.** Registration order is
   the only order.

## Consequences

- M6-T002 (telemetry) registers an `isolate` observer with `onEvent`/`afterTool` only; M6-T003
  (sample) registers a context contributor and a tool veto — both without touching Core.
- A fail_closed extension crash mid-turn leaves the same dangling shapes a real crash leaves
  (pinned in `tests/fault/extension-failure.fault.test.ts`: prefix folds, resume appends the
  honest `ModelRequestFailed`, the turn completes).
- The security surface shrinks to one question — "can anything make an unauthorized tool run?"
  — answered by the deny-only type plus the authorizer-first order
  (`tests/security/extension-bypass.security.test.ts`).
- Adding a ninth hook, request mutation, or tool injection now requires amending this ADR; that
  is the point.
