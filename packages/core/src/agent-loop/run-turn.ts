import type {
  EventActor,
  EventId,
  EventStore,
  ExtensionModelResult,
  ModelEvent,
  ModelProvider,
  ModelProviderErrorInfo,
  ModelRequest,
  ModelToolDefinition,
  SessionId,
  ToolCallRequest,
  ToolDefinition,
  ToolExecutionId,
  TurnId,
} from "@praxis/contracts";
import { EVENT_SCHEMA_VERSION } from "@praxis/contracts";
import type { ContextBudget } from "../context/budget";
import { DEFAULT_CONTEXT_BUDGET } from "../context/budget";
import { buildContext } from "../context/builder";
import { projectEpistemicBrief } from "../context/epistemic-brief";
import type { ExtensionHost } from "../extensions/host";
import { observeEventStore } from "../extensions/host";
import type { DerivedSessionState } from "../state/reducer";
import { foldSessionEvents } from "../state/reducer";
import { validateToolDefinitions } from "../tools/effect-policy";
import type { ToolAuthorizer } from "../tools/tool-runtime";
import { executeToolCall } from "../tools/tool-runtime";
import { appendEvent, eventEnvelope } from "./append-event";
import { projectConversation } from "./conversation";
import { invalidatePlansFalsifiedByHypotheses } from "./plan-invalidation";
import { pauseForUnresolvedIndeterminates, reconcileIndeterminateExecutions } from "./recovery";

/**
 * Minimal recoverable Agent Loop (docs/02 sections 10-12, 16-17). One
 * process, one session, one open turn at a time: the loop folds the durable
 * stream, closes anything a crash left dangling, then alternates model
 * requests and tool executions until the model answers with plain text.
 *
 * Hard rules honored here:
 * - Single writer: every append goes through the store with an expected
 *   head seq; derived state is re-folded from the stream after each append.
 * - Crash recovery never guesses: dangling EXECUTING becomes INDETERMINATE,
 *   dangling PROPOSED/AUTHORIZED become explicit rejections, a dangling
 *   model request becomes a failed request fact. Historical tools are never
 *   re-executed.
 * - Guards (step budget, consecutive model failures) are deterministic and
 *   counted per runTurn invocation; a resumed process gets a fresh budget.
 * - Cancellation is cooperative: the model stream ends silently, which the
 *   loop records as a ModelRequestFailed fact and returns `cancelled`.
 */

export type AgentLoopDeps = {
  readonly store: EventStore;
  readonly sessionId: SessionId;
  readonly model: ModelProvider;
  readonly modelId: string;
  readonly systemPrompt: string;
  readonly tools: readonly ToolDefinition[];
  readonly now: () => number;
  readonly newEventId: () => EventId;
  readonly newTurnId: () => TurnId;
  readonly newToolExecutionId: () => ToolExecutionId;
  readonly actor?: EventActor;
  /**
   * Pass-through provider request fields (e.g. reasoning effort, thinking
   * toggles), spread into the wire body by the adapter. Request
   * personalization ONLY: runtime rules (capabilities, state transitions,
   * completion requirements) never depend on it. Absent means a
   * byte-identical request.
   */
  readonly providerOptions?: Record<string, unknown>;
  /**
   * Extension host (docs/02 section 19, ADR-0013). Absent or empty means
   * byte-identical behavior to an extension-free loop (zero-extension
   * identity). The host instance is caller-owned; Core keeps no module
   * state.
   */
  readonly extensions?: ExtensionHost;
};

export type TurnGuards = {
  readonly maxStepsPerTurn: number;
  readonly maxConsecutiveModelFailures: number;
};

export const DEFAULT_TURN_GUARDS: TurnGuards = {
  maxStepsPerTurn: 16,
  maxConsecutiveModelFailures: 3,
};

export class InvalidTurnGuardsError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "InvalidTurnGuardsError";
  }
}

export function validateTurnGuards(guards: TurnGuards): void {
  if (!Number.isInteger(guards.maxStepsPerTurn) || guards.maxStepsPerTurn < 1) {
    throw new InvalidTurnGuardsError("maxStepsPerTurn must be a positive integer");
  }
  if (
    !Number.isInteger(guards.maxConsecutiveModelFailures) ||
    guards.maxConsecutiveModelFailures < 1
  ) {
    throw new InvalidTurnGuardsError("maxConsecutiveModelFailures must be a positive integer");
  }
}

export type TurnOutcome =
  | { readonly kind: "completed"; readonly finalText: string }
  | { readonly kind: "paused"; readonly reason: string }
  | { readonly kind: "cancelled" };

type ModelStreamResult =
  | { readonly kind: "completed"; readonly text: string; readonly toolCalls: ToolCallRequest[] }
  | { readonly kind: "providerError"; readonly error: ModelProviderErrorInfo }
  | { readonly kind: "endedSilently" };

export type RunTurnOptions = {
  readonly signal: AbortSignal;
  readonly guards?: TurnGuards;
  readonly authorizer?: ToolAuthorizer;
  readonly budget?: ContextBudget;
};

export async function runTurn(
  deps: AgentLoopDeps,
  input: { readonly input?: string },
  options: RunTurnOptions,
): Promise<TurnOutcome> {
  const guards = options.guards ?? DEFAULT_TURN_GUARDS;
  validateTurnGuards(guards);
  // Fail closed before any execution: effect-class promises (ADR-0006) are
  // checked here, not trusted from tool authors at call time.
  validateToolDefinitions(deps.tools);
  // Extension seams (docs/02 section 19, ADR-0013): absent host -> identical
  // deps (zero-extension identity); present host -> every append below is
  // observed via onEvent through the wrapped store.
  const wired: AgentLoopDeps =
    deps.extensions === undefined
      ? deps
      : { ...deps, store: observeEventStore(deps.store, deps.extensions) };
  const modelTools = toModelTools(wired.tools);

  let state = foldSessionEvents(await wired.store.readStream(wired.sessionId));
  if (state.status !== "ACTIVE") {
    throw new Error(`runTurn requires an ACTIVE session (status ${state.status})`);
  }

  if (await recoverDanglingWork(wired, state)) {
    state = foldSessionEvents(await wired.store.readStream(wired.sessionId));
  }

  // Falsifiable-plan decision (ADR-0012 reserved it for the runtime, white
  // paper "evidence can invalidate plan"): close active plans whose
  // hypothesis died. Appends nothing when nothing matches.
  await invalidatePlansFalsifiedByHypotheses(wired);

  // Crash-after-side-effect recovery (docs/02 section 17 steps 6-7): verify
  // what can be verified, then escalate instead of continuing a turn over an
  // unresolvable unknown effect. Only a human-initiated resume re-attempts.
  const reconciliation = await reconcileIndeterminateExecutions(wired, {
    signal: options.signal,
  });
  if (reconciliation.unresolved.length > 0) {
    await pauseForUnresolvedIndeterminates(wired, reconciliation.unresolved);
    const ids = reconciliation.unresolved
      .map((entry) => entry.toolExecutionId.valueOf())
      .join(", ");
    await wired.extensions?.hooks.onTurnEnd({
      sessionId: wired.sessionId,
      turnId: state.currentTurnId,
      outcome: {
        kind: "paused",
        reason: `${reconciliation.unresolved.length} indeterminate tool execution(s) could not be reconciled (${ids}); session paused for human decision`,
      },
    });
    return {
      kind: "paused",
      reason: `${reconciliation.unresolved.length} indeterminate tool execution(s) could not be reconciled (${ids}); session paused for human decision`,
    };
  }

  const openingTurn = state.currentTurnId === undefined;
  if (openingTurn) {
    const text = input.input;
    if (text === undefined) {
      throw new Error("runTurn requires user input to start a turn");
    }
    state = await appendEvent(wired, {
      id: wired.newEventId(),
      sessionId: wired.sessionId,
      schemaVersion: EVENT_SCHEMA_VERSION,
      occurredAt: wired.now(),
      actor: wired.actor ?? { kind: "system" },
      type: "TurnStarted",
      payload: { turnId: wired.newTurnId(), input: text },
    });
  } else if (input.input !== undefined) {
    throw new Error(
      `turn ${state.currentTurnId} is already open; resume it by calling runTurn without input`,
    );
  }
  const turnId = state.currentTurnId;
  if (turnId === undefined) {
    throw new Error("failed to open a turn");
  }

  if (openingTurn && input.input !== undefined) {
    await wired.extensions?.hooks.onTurnStart({
      sessionId: wired.sessionId,
      turnId,
      input: input.input,
    });
  }

  // Every TurnOutcome path passes through here so onTurnEnd fires exactly
  // once per outcome; crashes (fail_closed hooks, store failures) bypass it
  // honestly — the turn stays dangling for section-17 recovery.
  const endTurn = async (outcome: TurnOutcome): Promise<TurnOutcome> => {
    await wired.extensions?.hooks.onTurnEnd({
      sessionId: wired.sessionId,
      turnId,
      outcome,
    });
    return outcome;
  };

  let consecutiveFailures = 0;
  const budget = options.budget;
  for (let step = 1; step <= guards.maxStepsPerTurn; step += 1) {
    const turnEvents = await wired.store.readStream(wired.sessionId);
    const folded = foldSessionEvents(turnEvents);
    const epistemicBrief = projectEpistemicBrief(folded, budget ?? DEFAULT_CONTEXT_BUDGET);
    const extensionFragments =
      wired.extensions === undefined
        ? []
        : await wired.extensions.hooks.contributeContext({
            sessionId: wired.sessionId,
            turnId,
          });
    const { messages, tools } = buildContext(
      {
        systemPrompt: wired.systemPrompt,
        // docs/02 section 12.2: goal/plan/challenge/pending-indeterminate facts
        // ride as structured fragments of the system message, re-folded fresh
        // every step so mid-session facts reach the next model request.
        ...(epistemicBrief === undefined ? {} : { epistemicBrief }),
        ...(extensionFragments.length === 0 ? {} : { extensionFragments }),
        history: projectConversation(turnEvents),
        tools: modelTools,
      },
      budget,
    );
    const request: ModelRequest = {
      model: wired.modelId,
      messages: [...messages],
      ...(tools.length === 0 ? {} : { tools: [...tools] }),
      correlationId: wired.sessionId,
      ...(wired.providerOptions === undefined ? {} : { providerOptions: wired.providerOptions }),
    };

    state = await appendEvent(wired, {
      id: wired.newEventId(),
      sessionId: wired.sessionId,
      schemaVersion: EVENT_SCHEMA_VERSION,
      occurredAt: wired.now(),
      actor: wired.actor ?? { kind: "system" },
      type: "ModelRequestStarted",
      payload: { model: wired.modelId },
    });

    await wired.extensions?.hooks.beforeModel({
      sessionId: wired.sessionId,
      turnId,
      request,
    });
    const result = await consumeModelStream(wired.model.complete(request, options.signal));
    await wired.extensions?.hooks.afterModel({
      sessionId: wired.sessionId,
      turnId,
      request,
      result: toExtensionModelResult(result),
    });

    if (result.kind === "endedSilently") {
      await appendEvent(wired, {
        id: wired.newEventId(),
        sessionId: wired.sessionId,
        schemaVersion: EVENT_SCHEMA_VERSION,
        occurredAt: wired.now(),
        actor: wired.actor ?? { kind: "system" },
        type: "ModelRequestFailed",
        payload: {
          kind: "unknown",
          retryable: false,
          message: "model stream ended without a terminal event (cancelled)",
        },
      });
      return endTurn({ kind: "cancelled" });
    }

    if (result.kind === "providerError") {
      state = await appendEvent(wired, {
        id: wired.newEventId(),
        sessionId: wired.sessionId,
        schemaVersion: EVENT_SCHEMA_VERSION,
        occurredAt: wired.now(),
        actor: wired.actor ?? { kind: "system" },
        type: "ModelRequestFailed",
        payload: {
          kind: result.error.kind,
          retryable: result.error.retryable,
          message: result.error.message,
        },
      });
      consecutiveFailures += 1;
      if (consecutiveFailures >= guards.maxConsecutiveModelFailures) {
        return endTurn({
          kind: "paused",
          reason: `model failed ${consecutiveFailures} times in a row (${result.error.kind})`,
        });
      }
      continue;
    }

    state = await appendEvent(wired, {
      id: wired.newEventId(),
      sessionId: wired.sessionId,
      schemaVersion: EVENT_SCHEMA_VERSION,
      occurredAt: wired.now(),
      actor: wired.actor ?? { kind: "system" },
      type: "ModelResponseCompleted",
      payload: {
        ...(result.text === "" ? {} : { text: result.text }),
        toolCalls: result.toolCalls.map((call) => ({ ...call })),
      },
    });
    consecutiveFailures = 0;

    if (result.toolCalls.length > 0) {
      for (const call of result.toolCalls) {
        await executeToolCall(
          {
            store: wired.store,
            sessionId: wired.sessionId,
            tools: wired.tools,
            now: wired.now,
            newEventId: wired.newEventId,
            newToolExecutionId: wired.newToolExecutionId,
            ...(wired.actor === undefined ? {} : { actor: wired.actor }),
          },
          { name: call.name, argumentsJson: call.argumentsJson, toolCallId: call.id },
          {
            signal: options.signal,
            ...(options.authorizer === undefined ? {} : { authorizer: options.authorizer }),
            ...(wired.extensions === undefined ? {} : { extensions: wired.extensions }),
          },
        );
      }
      continue;
    }

    if (result.text !== "") {
      await appendEvent(wired, {
        id: wired.newEventId(),
        sessionId: wired.sessionId,
        schemaVersion: EVENT_SCHEMA_VERSION,
        occurredAt: wired.now(),
        actor: wired.actor ?? { kind: "system" },
        type: "TurnCompleted",
        payload: { turnId },
      });
      return endTurn({ kind: "completed", finalText: result.text });
    }

    consecutiveFailures += 1;
    if (consecutiveFailures >= guards.maxConsecutiveModelFailures) {
      return endTurn({
        kind: "paused",
        reason: "model produced empty responses too many times in a row",
      });
    }
  }

  return endTurn({
    kind: "paused",
    reason: `turn exceeded ${guards.maxStepsPerTurn} model steps without a final answer`,
  });
}

/**
 * Close whatever a prior crash left open, as facts, and report whether
 * anything was appended. Nothing is retried and no historical tool is
 * re-executed: EXECUTING without a terminal event is a potential
 * INDETERMINATE (docs/02 section 17), never an assumed failure.
 */
async function recoverDanglingWork(
  deps: AgentLoopDeps,
  state: DerivedSessionState,
): Promise<boolean> {
  let appended = false;

  const dangling = [...state.toolExecutions.values()].filter(
    (snapshot) =>
      snapshot.status === "PROPOSED" ||
      snapshot.status === "AUTHORIZED" ||
      snapshot.status === "EXECUTING",
  );
  for (const snapshot of dangling) {
    if (snapshot.status === "EXECUTING") {
      await appendEvent(deps, {
        ...eventEnvelope(deps),
        type: "ToolIndeterminate",
        payload: {
          toolExecutionId: snapshot.toolExecutionId,
          reason: "process crashed before a terminal tool event; outcome unknown",
        },
      });
    } else {
      const stage = snapshot.status === "AUTHORIZED" ? "authorization" : "proposal";
      await appendEvent(deps, {
        ...eventEnvelope(deps),
        type: "ToolRejected",
        payload: {
          toolExecutionId: snapshot.toolExecutionId,
          reason: `abandoned at ${stage} by crash recovery; never executed`,
        },
      });
    }
    appended = true;
  }

  const afterTools = foldSessionEvents(await deps.store.readStream(deps.sessionId));
  if (afterTools.pendingModelRequest !== undefined) {
    await appendEvent(deps, {
      ...eventEnvelope(deps),
      type: "ModelRequestFailed",
      payload: {
        kind: "unknown",
        retryable: false,
        message: "process crashed before the model stream finished; response unknown",
      },
    });
    appended = true;
  }
  return appended;
}

/** Copy the internal stream result into the contracts read-only view. */
function toExtensionModelResult(result: ModelStreamResult): ExtensionModelResult {
  switch (result.kind) {
    case "completed":
      return {
        kind: "completed",
        text: result.text,
        toolCalls: result.toolCalls.map((call) => ({ ...call })),
      };
    case "providerError":
      return { kind: "providerError", error: result.error };
    case "endedSilently":
      return { kind: "endedSilently" };
  }
}

async function consumeModelStream(stream: AsyncIterable<ModelEvent>): Promise<ModelStreamResult> {
  let text = "";
  const calls = new Map<string, { id: string; name: string; buffer: string }>();
  for await (const chunk of stream) {
    switch (chunk.type) {
      case "textDelta":
        text += chunk.text;
        break;
      case "toolCallStart":
        calls.set(chunk.toolCallId, { id: chunk.toolCallId, name: chunk.name, buffer: "" });
        break;
      case "toolCallDelta": {
        const call = calls.get(chunk.toolCallId);
        if (call !== undefined) {
          call.buffer += chunk.argumentsDelta;
        }
        break;
      }
      case "toolCallEnd":
        break;
      case "completed": {
        const toolCalls = [...calls.values()].map(({ id, name, buffer }) => ({
          id,
          name,
          argumentsJson: buffer,
        }));
        return { kind: "completed", text, toolCalls };
      }
      case "providerError":
        return { kind: "providerError", error: chunk.error };
      default:
        break;
    }
  }
  return { kind: "endedSilently" };
}

function toModelTools(tools: readonly ToolDefinition[]): ModelToolDefinition[] {
  return tools.map((tool) => {
    JSON.parse(tool.parametersJson);
    return {
      name: tool.name,
      description: tool.description,
      parametersJson: tool.parametersJson,
    };
  });
}
