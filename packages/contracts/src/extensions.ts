import type { SessionEventUnion } from "./events/session-events";
import type { SessionId, ToolExecutionId, TurnId } from "./ids";
import type { ModelProviderErrorInfo } from "./model/events";
import type { ModelRequest, ToolCallRequest } from "./model/request";
import type { ToolEffect } from "./tools/tool-effect";

/**
 * Extension seams, v1 (docs/02 section 19, ADR-0013). An extension is an
 * out-of-core observer that may contribute context and add tool vetoes. It
 * is NOT an Event Bus framework and NOT a capability grant path:
 *
 * - Every hook is optional; the count is fixed at eight and does not grow
 *   per feature.
 * - All hook contexts are read-only views. They never carry the store, the
 *   folded state, or anything an extension could mutate. Extensions append
 *   nothing; their own durable state must live in Event form or explicit
 *   storage they own (out of scope for v1).
 * - ToolHookDecision is deny-only by type: `{ decision: "deny", reason }`.
 *   "Allow" is unrepresentable, so no extension can authorize anything the
 *   capability/authorizer layer denied — the M6 failure-acceptance property
 *   holds by construction, not by discipline.
 * - Failure semantics are declared per extension: 'isolate' (default)
 *   swallows hook errors so telemetry-grade observers cannot break a turn;
 *   'fail_closed' propagates so the existing crash-recovery machinery
 *   (docs/02 section 17) handles the failure honestly. There is no second
 *   failure path.
 */

export const EXTENSION_HOOKS = [
  "onTurnStart",
  "contributeContext",
  "beforeModel",
  "afterModel",
  "beforeTool",
  "afterTool",
  "onEvent",
  "onTurnEnd",
] as const;
export type ExtensionHookName = (typeof EXTENSION_HOOKS)[number];

export const EXTENSION_FAILURE_POLICIES = ["isolate", "fail_closed"] as const;
export type ExtensionFailurePolicy = (typeof EXTENSION_FAILURE_POLICIES)[number];

/** A section of extension-contributed context text (docs/02 section 19). */
export type ContextFragment = {
  /** Owning extension name; the host stamps its own name, never the caller's. */
  readonly source: string;
  readonly text: string;
};

/**
 * DENY-ONLY. Returning nothing (void/undefined) means "no opinion". The type
 * cannot express "allow": authorization stays the sole possession of the
 * authorizer/capability layer (ADR-0007).
 */
export type ToolHookDecision = { readonly decision: "deny"; readonly reason: string };

/** Read-only base every hook context extends. */
export type ExtensionContext = {
  readonly sessionId: SessionId;
};

export type TurnStartHookContext = ExtensionContext & {
  readonly turnId: TurnId;
  readonly input: string;
};

export type ContextContributionContext = ExtensionContext & {
  readonly turnId: TurnId;
};

export type ModelHookContext = ExtensionContext & {
  readonly turnId: TurnId;
  readonly request: ModelRequest;
};

/** Read-only view of one model call's outcome, normalized by Core. */
export type ExtensionModelResult =
  | {
      readonly kind: "completed";
      readonly text: string;
      readonly toolCalls: readonly ToolCallRequest[];
    }
  | { readonly kind: "providerError"; readonly error: ModelProviderErrorInfo }
  | { readonly kind: "endedSilently" };

export type ModelResultHookContext = ExtensionContext & {
  readonly turnId: TurnId;
  readonly request: ModelRequest;
  readonly result: ExtensionModelResult;
};

export type ToolHookContext = ExtensionContext & {
  readonly turnId: TurnId;
  readonly name: string;
  readonly effect: ToolEffect;
  readonly argumentsJson: string;
  /** Correlation id of the model tool call that caused this execution. */
  readonly toolCallId?: string;
};

export const EXTENSION_TOOL_RESULT_STATUSES = [
  "REJECTED",
  "SUCCEEDED",
  "FAILED",
  "INDETERMINATE",
] as const;
export type ExtensionToolResultStatus = (typeof EXTENSION_TOOL_RESULT_STATUSES)[number];

export type ToolResultHookContext = ExtensionContext & {
  readonly turnId: TurnId;
  readonly toolExecutionId: ToolExecutionId;
  readonly name: string;
  readonly status: ExtensionToolResultStatus;
  /** Terminal-event detail: rejection reason, failure message, or indeterminate reason. */
  readonly detail?: string;
};

export type EventHookContext = ExtensionContext & {
  /** Open turn at append time; undefined for pre-turn events (recovery facts). */
  readonly turnId: TurnId | undefined;
  readonly event: SessionEventUnion;
};

export type ExtensionTurnOutcome =
  | { readonly kind: "completed"; readonly finalText: string }
  | { readonly kind: "paused"; readonly reason: string }
  | { readonly kind: "cancelled" };

export type TurnEndHookContext = ExtensionContext & {
  /** Turn the outcome belongs to; undefined only on the pre-turn reconciliation pause. */
  readonly turnId: TurnId | undefined;
  readonly outcome: ExtensionTurnOutcome;
};

/**
 * The extension surface (docs/02 section 19). All hooks optional; the host
 * invokes present hooks in registration order. Hooks may be sync or async.
 */
export interface PraxisExtension {
  /** Unique within a host; non-empty, starts alphanumerically, <= 64 chars. */
  readonly name: string;
  /** Default 'isolate'. */
  readonly failurePolicy?: ExtensionFailurePolicy;
  /** After the TurnStarted append, in the invocation that opened the turn. */
  onTurnStart?(context: TurnStartHookContext): void | Promise<void>;
  /**
   * Per model step, before context assembly. Returned fragments render as
   * capped `## Extension: <name>` sections in the system fragment, after the
   * epistemic brief. The host stamps `source` with the extension's own name.
   */
  contributeContext?(
    context: ContextContributionContext,
  ): readonly ContextFragment[] | undefined | Promise<readonly ContextFragment[] | undefined>;
  /** Immediately before model.complete, with the frozen request. */
  beforeModel?(context: ModelHookContext): void | Promise<void>;
  /** After the model stream settles (completed/providerError/endedSilently). */
  afterModel?(context: ModelResultHookContext): void | Promise<void>;
  /**
   * After the authorizer approves, before ToolAuthorized. Deny appends
   * ToolRejected citing this extension; the call never executes. Only a
   * deny is expressible.
   */
  beforeTool?(
    context: ToolHookContext,
  ): ToolHookDecision | undefined | Promise<ToolHookDecision | undefined>;
  /** On settle, for every terminal status including REJECTED. */
  afterTool?(context: ToolResultHookContext): void | Promise<void>;
  /** After each durable append succeeds (observe-only). */
  onEvent?(context: EventHookContext): void | Promise<void>;
  /** On every TurnOutcome path (completed/paused/cancelled); not on crashes. */
  onTurnEnd?(context: TurnEndHookContext): void | Promise<void>;
}

export class InvalidExtensionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "InvalidExtensionError";
  }
}

const EXTENSION_NAME_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;
const EXTENSION_NAME_MAX_BYTES = 64;

/**
 * Structural validation at registration: name rules, hook arity/shape,
 * failurePolicy domain. Return-shape violations (contributeContext/beforeTool
 * garbage) are detected by the host at invocation time — functions cannot be
 * validated ahead of calling them.
 */
export function validatePraxisExtension(extension: PraxisExtension): void {
  if (extension === null || typeof extension !== "object") {
    throw new InvalidExtensionError("extension must be an object");
  }
  if (
    typeof extension.name !== "string" ||
    extension.name.length === 0 ||
    extension.name.trim() !== extension.name ||
    extension.name.length > EXTENSION_NAME_MAX_BYTES ||
    !EXTENSION_NAME_PATTERN.test(extension.name)
  ) {
    throw new InvalidExtensionError(
      `extension name must be non-empty, start alphanumerically, contain only [A-Za-z0-9._-], and be at most ${EXTENSION_NAME_MAX_BYTES} chars (got ${JSON.stringify(extension.name)})`,
    );
  }
  if (
    extension.failurePolicy !== undefined &&
    !EXTENSION_FAILURE_POLICIES.includes(extension.failurePolicy)
  ) {
    throw new InvalidExtensionError(
      `extension ${extension.name}: failurePolicy must be one of ${EXTENSION_FAILURE_POLICIES.join(", ")}`,
    );
  }
  for (const hookName of EXTENSION_HOOKS) {
    const hook = extension[hookName];
    if (hook !== undefined && typeof hook !== "function") {
      throw new InvalidExtensionError(
        `extension ${extension.name}: hook ${hookName} must be a function or undefined`,
      );
    }
  }
}
