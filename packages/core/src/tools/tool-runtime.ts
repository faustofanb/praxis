import type {
  CapabilityRequirement,
  EventActor,
  EventId,
  EventStore,
  SessionEventUnion,
  SessionId,
  ToolDefinition,
  ToolEffect,
  ToolExecutionId,
} from "@praxis/contracts";
import { EVENT_SCHEMA_VERSION } from "@praxis/contracts";
import type { ExtensionHost } from "../extensions/host";
import type { DerivedSessionState } from "../state/reducer";
import { foldSessionEvents } from "../state/reducer";

/**
 * Read-only tool runtime executor (docs/02 section 8). Orchestrates the
 * durable lifecycle around injected ports: the store persists facts, tools
 * do the work, and clock/ID sources are injected so Core itself stays
 * deterministic. Replay never runs this; everything it decides is already a
 * fact in the stream.
 */

export type ToolRuntimeDeps = {
  readonly store: EventStore;
  readonly sessionId: SessionId;
  readonly tools: readonly ToolDefinition[];
  readonly now: () => number;
  readonly newEventId: () => EventId;
  readonly newToolExecutionId: () => ToolExecutionId;
  readonly actor?: EventActor;
};

export type ToolAuthorizationDecision =
  | { decision: "authorized" }
  | { decision: "rejected"; reason: string };

export type ToolAuthorizer = (request: {
  readonly name: string;
  readonly effect: ToolEffect;
  readonly argumentsJson: string;
  /** The registered tool's declared requirement, when it declares one. */
  readonly requiredCapability?: CapabilityRequirement;
}) => ToolAuthorizationDecision;

/**
 * v1 default policy: deny by default, allow read_only only (docs/03 M2
 * scope). Capability machinery arrives in M3; this hook is its seam.
 */
export function readOnlyAuthorizer(request: {
  name: string;
  effect: ToolEffect;
}): ToolAuthorizationDecision {
  if (request.effect === "read_only") {
    return { decision: "authorized" };
  }
  return {
    decision: "rejected",
    reason: `effect ${request.effect} is not permitted in a read-only session`,
  };
}

export type ExecutedToolSummary = {
  readonly toolExecutionId: ToolExecutionId;
  readonly status: "REJECTED" | "SUCCEEDED" | "FAILED" | "INDETERMINATE";
};

type EventInit<T> = T extends { seq: number } ? Omit<T, "seq"> : never;
type SessionEventInit = EventInit<SessionEventUnion>;

export async function executeToolCall(
  deps: ToolRuntimeDeps,
  proposal: {
    readonly name: string;
    readonly argumentsJson: string;
    /** Optional correlation with the model tool call that caused this. */
    readonly toolCallId?: string;
  },
  options: {
    readonly signal: AbortSignal;
    readonly authorizer?: ToolAuthorizer;
    readonly extensions?: ExtensionHost;
  },
): Promise<ExecutedToolSummary> {
  const priorState = await projectSessionState(deps);
  if (priorState.status !== "ACTIVE" || priorState.currentTurnId === undefined) {
    throw new Error(
      `executeToolCall requires an ACTIVE session with an open turn (status ${priorState.status})`,
    );
  }
  const turnId = priorState.currentTurnId;

  const authorizer = options.authorizer ?? readOnlyAuthorizer;
  const actor = deps.actor ?? { kind: "system" };
  const toolExecutionId = deps.newToolExecutionId();
  let seq = priorState.headSeq;

  const appendOne = async (init: SessionEventInit): Promise<void> => {
    seq += 1;
    const event: SessionEventUnion = { ...init, seq };
    await deps.store.append([event], seq - 1);
  };
  const envelope = () => ({
    id: deps.newEventId(),
    sessionId: deps.sessionId,
    schemaVersion: EVENT_SCHEMA_VERSION,
    occurredAt: deps.now(),
    actor,
  });
  // Every terminal path funnels through here so afterTool observes the
  // settled execution (ADR-0013), exactly once per tool call.
  const settle = async (
    status: ExecutedToolSummary["status"],
    detail?: string,
  ): Promise<ExecutedToolSummary> => {
    await options.extensions?.hooks.afterTool({
      sessionId: deps.sessionId,
      turnId,
      toolExecutionId,
      name: proposal.name,
      status,
      ...(detail === undefined ? {} : { detail }),
    });
    return { toolExecutionId, status };
  };

  const registry = new Map(deps.tools.map((tool) => [tool.name, tool]));
  const tool = registry.get(proposal.name);
  // An unregistered tool is proposed under the most conservative effect
  // class and then denied: the model's intent stays a recorded fact, the
  // denial stays explicit.
  const effect: ToolEffect = tool?.effect ?? "non_idempotent_write";

  await appendOne({
    ...envelope(),
    type: "ToolProposed",
    payload: {
      toolExecutionId,
      name: proposal.name,
      argumentsJson: proposal.argumentsJson,
      effect,
      ...(proposal.toolCallId === undefined ? {} : { toolCallId: proposal.toolCallId }),
    },
  });

  if (tool === undefined) {
    const reason = `unknown tool ${proposal.name}`;
    await appendOne({
      ...envelope(),
      type: "ToolRejected",
      payload: { toolExecutionId, reason },
    });
    return settle("REJECTED", reason);
  }

  let input: unknown;
  try {
    input = tool.inputSchema.parse(JSON.parse(proposal.argumentsJson));
  } catch (error) {
    const reason = `invalid arguments for ${proposal.name}: ${
      error instanceof Error ? error.message : String(error)
    }`;
    await appendOne({
      ...envelope(),
      type: "ToolRejected",
      payload: { toolExecutionId, reason },
    });
    return settle("REJECTED", reason);
  }

  const decision = authorizer({
    name: proposal.name,
    effect,
    argumentsJson: proposal.argumentsJson,
    ...(tool.requiredCapability === undefined
      ? {}
      : { requiredCapability: tool.requiredCapability }),
  });
  if (decision.decision === "rejected") {
    await appendOne({
      ...envelope(),
      type: "ToolRejected",
      payload: { toolExecutionId, reason: decision.reason },
    });
    return settle("REJECTED", decision.reason);
  }

  // Extension veto composes AFTER the authorizer approves (ADR-0007/0013):
  // extensions only ever restrict. A deny is an explicit ToolRejected fact
  // citing the extension; the call never executes.
  const denial =
    options.extensions === undefined
      ? undefined
      : await options.extensions.hooks.beforeTool({
          sessionId: deps.sessionId,
          turnId,
          name: proposal.name,
          effect,
          argumentsJson: proposal.argumentsJson,
          ...(proposal.toolCallId === undefined ? {} : { toolCallId: proposal.toolCallId }),
        });
  if (denial !== undefined) {
    const reason = `extension ${denial.extensionName} denied: ${denial.decision.reason}`;
    await appendOne({
      ...envelope(),
      type: "ToolRejected",
      payload: { toolExecutionId, reason },
    });
    return settle("REJECTED", reason);
  }

  await appendOne({
    ...envelope(),
    type: "ToolAuthorized",
    payload: { toolExecutionId },
  });
  await appendOne({
    ...envelope(),
    type: "ToolStarted",
    payload: { toolExecutionId },
  });

  let outcome: Awaited<ReturnType<ToolDefinition["execute"]>>;
  try {
    outcome = await tool.execute({ signal: options.signal }, input);
  } catch (error) {
    // A crash inside execute proves nothing about the effect. Read-only
    // tools cannot have side effects, so they may fail fast; anything else
    // stays indeterminate (docs/02 section 8.2 hard rules).
    if (effect === "read_only") {
      const message = `executor crashed: ${error instanceof Error ? error.message : String(error)}`;
      await appendOne({
        ...envelope(),
        type: "ToolFailed",
        payload: { toolExecutionId, message },
      });
      return settle("FAILED", message);
    }
    const reason = `executor crashed before outcome was known: ${
      error instanceof Error ? error.message : String(error)
    }`;
    await appendOne({
      ...envelope(),
      type: "ToolIndeterminate",
      payload: { toolExecutionId, reason },
    });
    return settle("INDETERMINATE", reason);
  }

  switch (outcome.status) {
    case "succeeded":
      await appendOne({
        ...envelope(),
        type: "ToolSucceeded",
        payload: { toolExecutionId, resultJson: outcome.resultJson },
      });
      return settle("SUCCEEDED");
    case "failed":
      await appendOne({
        ...envelope(),
        type: "ToolFailed",
        payload: { toolExecutionId, message: outcome.error.message },
      });
      return settle("FAILED", outcome.error.message);
    case "indeterminate":
      await appendOne({
        ...envelope(),
        type: "ToolIndeterminate",
        payload: { toolExecutionId, reason: outcome.reason },
      });
      return settle("INDETERMINATE", outcome.reason);
  }
}

/**
 * Fold the derived state through the port. Callers (and tests) use it to
 * observe the projection the executor just extended.
 */
export async function projectSessionState(
  deps: Pick<ToolRuntimeDeps, "store" | "sessionId">,
): Promise<DerivedSessionState> {
  const events = await deps.store.readStream(deps.sessionId);
  return foldSessionEvents(events);
}
