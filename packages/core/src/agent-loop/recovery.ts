import type {
  ReconciliationOutcome,
  ToolDefinition,
  ToolExecutionContext,
  ToolExecutionId,
} from "@praxis/contracts";
import type { DerivedSessionState } from "../state/reducer";
import { foldSessionEvents } from "../state/reducer";
import { appendEvent, type EventAppenderDeps, eventEnvelope } from "./append-event";

/**
 * Crash-after-side-effect recovery (docs/02 sections 17 and 8.3; ADR-0011).
 * Dangling EXECUTING has already been closed as ToolIndeterminate by the
 * agent loop; this pass runs reconciliation for every INDETERMINATE
 * execution: parse the recorded input with the registered tool's schema,
 * call the tool's verification-only reconcile, and append the conclusion as
 * a durable ToolReconciled fact. Nothing is guessed and nothing is retried:
 * a reconcile that cannot decide leaves an honest indeterminate fact, and
 * the caller decides whether unresolved indeterminates escalate.
 */

export type RecoveryDeps = EventAppenderDeps & {
  readonly tools: readonly ToolDefinition[];
};

export type ReconciliationReport = {
  readonly settled: ReadonlyArray<{
    readonly toolExecutionId: ToolExecutionId;
    readonly outcome: "succeeded" | "failed";
  }>;
  readonly unresolved: ReadonlyArray<{
    readonly toolExecutionId: ToolExecutionId;
    readonly reason: string;
  }>;
};

export async function reconcileIndeterminateExecutions(
  deps: RecoveryDeps,
  options: { readonly signal: AbortSignal },
): Promise<ReconciliationReport> {
  const state = foldSessionEvents(await deps.store.readStream(deps.sessionId));
  const settled: Array<{ toolExecutionId: ToolExecutionId; outcome: "succeeded" | "failed" }> = [];
  const unresolved: Array<{ toolExecutionId: ToolExecutionId; reason: string }> = [];

  const indeterminate = [...state.toolExecutions.values()].filter(
    (snapshot) => snapshot.status === "INDETERMINATE",
  );
  for (const snapshot of indeterminate) {
    const tool = deps.tools.find((candidate) => candidate.name === snapshot.name);
    if (tool === undefined) {
      unresolved.push({
        toolExecutionId: snapshot.toolExecutionId,
        reason: `tool ${snapshot.name} is not registered; cannot verify`,
      });
      continue;
    }
    const reconcile = tool.reconcile;
    if (reconcile === undefined) {
      unresolved.push({
        toolExecutionId: snapshot.toolExecutionId,
        reason: `tool ${snapshot.name} defines no reconcile`,
      });
      continue;
    }
    let input: unknown;
    try {
      input = tool.inputSchema.parse(JSON.parse(snapshot.argumentsJson));
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      await appendReconciled(deps, snapshot.toolExecutionId, {
        outcome: "indeterminate",
        reason: `recorded input no longer parses; cannot verify: ${detail}`,
      });
      unresolved.push({
        toolExecutionId: snapshot.toolExecutionId,
        reason: "recorded input no longer parses",
      });
      continue;
    }
    const result = await runReconcile(reconcile, options.signal, input);
    await appendReconciled(deps, snapshot.toolExecutionId, result);
    if (result.outcome === "indeterminate") {
      unresolved.push({
        toolExecutionId: snapshot.toolExecutionId,
        reason: result.reason,
      });
    } else {
      settled.push({
        toolExecutionId: snapshot.toolExecutionId,
        outcome: result.outcome,
      });
    }
  }
  return { settled, unresolved };
}

type ReconciledPayload =
  | { outcome: "succeeded"; resultJson: string }
  | { outcome: "failed"; message: string }
  | { outcome: "indeterminate"; reason: string };

async function runReconcile(
  reconcile: (context: ToolExecutionContext, input: unknown) => Promise<ReconciliationOutcome>,
  signal: AbortSignal,
  input: unknown,
): Promise<ReconciledPayload> {
  let outcome: ReconciliationOutcome;
  try {
    outcome = await reconcile({ signal }, input);
  } catch (error) {
    // A crashing reconcile is an honest "tried, could not verify" — recorded
    // as such, never converted into a settled conclusion.
    const detail = error instanceof Error ? error.message : String(error);
    return { outcome: "indeterminate", reason: `reconcile attempt failed: ${detail}` };
  }
  if (outcome.status === "succeeded") {
    return { outcome: "succeeded", resultJson: outcome.resultJson };
  }
  if (outcome.status === "failed") {
    return { outcome: "failed", message: outcome.error.message };
  }
  return { outcome: "indeterminate", reason: outcome.reason };
}

async function appendReconciled(
  deps: RecoveryDeps,
  toolExecutionId: ToolExecutionId,
  payload: ReconciledPayload,
): Promise<DerivedSessionState> {
  return appendEvent(deps, {
    ...eventEnvelope(deps),
    type: "ToolReconciled",
    payload: { toolExecutionId, ...payload },
  });
}

/**
 * Escalation (docs/02 section 17 step 7): unresolved indeterminates close
 * the open turn and pause the session. The turn must not continue over an
 * unresolvable unknown effect; only a human-initiated SessionResumed (which
 * re-enters recovery and re-attempts reconciliation) unlocks the session.
 */
export async function pauseForUnresolvedIndeterminates(
  deps: RecoveryDeps,
  unresolved: ReadonlyArray<{ readonly toolExecutionId: ToolExecutionId }>,
): Promise<DerivedSessionState> {
  if (unresolved.length === 0) {
    return foldSessionEvents(await deps.store.readStream(deps.sessionId));
  }
  let state = foldSessionEvents(await deps.store.readStream(deps.sessionId));
  if (state.currentTurnId !== undefined) {
    state = await appendEvent(deps, {
      ...eventEnvelope(deps),
      type: "TurnCompleted",
      payload: { turnId: state.currentTurnId },
    });
  }
  return appendEvent(deps, {
    ...eventEnvelope(deps),
    type: "SessionPaused",
    payload: {},
  });
}
