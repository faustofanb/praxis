import type {
  EventActor,
  EventId,
  EventStore,
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
import { buildContext } from "../context/builder";
import type { DerivedSessionState } from "../state/reducer";
import { foldSessionEvents } from "../state/reducer";
import { validateToolDefinitions } from "../tools/effect-policy";
import type { ToolAuthorizer } from "../tools/tool-runtime";
import { executeToolCall } from "../tools/tool-runtime";
import { appendEvent, eventEnvelope } from "./append-event";
import { projectConversation } from "./conversation";
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
  const modelTools = toModelTools(deps.tools);

  let state = foldSessionEvents(await deps.store.readStream(deps.sessionId));
  if (state.status !== "ACTIVE") {
    throw new Error(`runTurn requires an ACTIVE session (status ${state.status})`);
  }

  if (await recoverDanglingWork(deps, state)) {
    state = foldSessionEvents(await deps.store.readStream(deps.sessionId));
  }

  // Crash-after-side-effect recovery (docs/02 section 17 steps 6-7): verify
  // what can be verified, then escalate instead of continuing a turn over an
  // unresolvable unknown effect. Only a human-initiated resume re-attempts.
  const reconciliation = await reconcileIndeterminateExecutions(deps, {
    signal: options.signal,
  });
  if (reconciliation.unresolved.length > 0) {
    await pauseForUnresolvedIndeterminates(deps, reconciliation.unresolved);
    const ids = reconciliation.unresolved
      .map((entry) => entry.toolExecutionId.valueOf())
      .join(", ");
    return {
      kind: "paused",
      reason: `${reconciliation.unresolved.length} indeterminate tool execution(s) could not be reconciled (${ids}); session paused for human decision`,
    };
  }

  if (state.currentTurnId === undefined) {
    const text = input.input;
    if (text === undefined) {
      throw new Error("runTurn requires user input to start a turn");
    }
    state = await appendEvent(deps, {
      id: deps.newEventId(),
      sessionId: deps.sessionId,
      schemaVersion: EVENT_SCHEMA_VERSION,
      occurredAt: deps.now(),
      actor: deps.actor ?? { kind: "system" },
      type: "TurnStarted",
      payload: { turnId: deps.newTurnId(), input: text },
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

  let consecutiveFailures = 0;
  for (let step = 1; step <= guards.maxStepsPerTurn; step += 1) {
    const turnEvents = await deps.store.readStream(deps.sessionId);
    const { messages, tools } = buildContext(
      {
        systemPrompt: deps.systemPrompt,
        history: projectConversation(turnEvents),
        tools: modelTools,
      },
      options.budget,
    );
    const request: ModelRequest = {
      model: deps.modelId,
      messages: [...messages],
      ...(tools.length === 0 ? {} : { tools: [...tools] }),
      correlationId: deps.sessionId,
    };

    state = await appendEvent(deps, {
      id: deps.newEventId(),
      sessionId: deps.sessionId,
      schemaVersion: EVENT_SCHEMA_VERSION,
      occurredAt: deps.now(),
      actor: deps.actor ?? { kind: "system" },
      type: "ModelRequestStarted",
      payload: { model: deps.modelId },
    });

    const result = await consumeModelStream(deps.model.complete(request, options.signal));

    if (result.kind === "endedSilently") {
      await appendEvent(deps, {
        id: deps.newEventId(),
        sessionId: deps.sessionId,
        schemaVersion: EVENT_SCHEMA_VERSION,
        occurredAt: deps.now(),
        actor: deps.actor ?? { kind: "system" },
        type: "ModelRequestFailed",
        payload: {
          kind: "unknown",
          retryable: false,
          message: "model stream ended without a terminal event (cancelled)",
        },
      });
      return { kind: "cancelled" };
    }

    if (result.kind === "providerError") {
      state = await appendEvent(deps, {
        id: deps.newEventId(),
        sessionId: deps.sessionId,
        schemaVersion: EVENT_SCHEMA_VERSION,
        occurredAt: deps.now(),
        actor: deps.actor ?? { kind: "system" },
        type: "ModelRequestFailed",
        payload: {
          kind: result.error.kind,
          retryable: result.error.retryable,
          message: result.error.message,
        },
      });
      consecutiveFailures += 1;
      if (consecutiveFailures >= guards.maxConsecutiveModelFailures) {
        return {
          kind: "paused",
          reason: `model failed ${consecutiveFailures} times in a row (${result.error.kind})`,
        };
      }
      continue;
    }

    state = await appendEvent(deps, {
      id: deps.newEventId(),
      sessionId: deps.sessionId,
      schemaVersion: EVENT_SCHEMA_VERSION,
      occurredAt: deps.now(),
      actor: deps.actor ?? { kind: "system" },
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
            store: deps.store,
            sessionId: deps.sessionId,
            tools: deps.tools,
            now: deps.now,
            newEventId: deps.newEventId,
            newToolExecutionId: deps.newToolExecutionId,
            ...(deps.actor === undefined ? {} : { actor: deps.actor }),
          },
          { name: call.name, argumentsJson: call.argumentsJson, toolCallId: call.id },
          {
            signal: options.signal,
            ...(options.authorizer === undefined ? {} : { authorizer: options.authorizer }),
          },
        );
      }
      continue;
    }

    if (result.text !== "") {
      await appendEvent(deps, {
        id: deps.newEventId(),
        sessionId: deps.sessionId,
        schemaVersion: EVENT_SCHEMA_VERSION,
        occurredAt: deps.now(),
        actor: deps.actor ?? { kind: "system" },
        type: "TurnCompleted",
        payload: { turnId },
      });
      return { kind: "completed", finalText: result.text };
    }

    consecutiveFailures += 1;
    if (consecutiveFailures >= guards.maxConsecutiveModelFailures) {
      return {
        kind: "paused",
        reason: "model produced empty responses too many times in a row",
      };
    }
  }

  return {
    kind: "paused",
    reason: `turn exceeded ${guards.maxStepsPerTurn} model steps without a final answer`,
  };
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
