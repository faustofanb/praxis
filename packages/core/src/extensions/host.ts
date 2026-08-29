import type {
  ContextContributionContext,
  ContextFragment,
  EventHookContext,
  EventStore,
  ExtensionHookName,
  ModelHookContext,
  ModelResultHookContext,
  PraxisExtension,
  SessionEventUnion,
  SessionId,
  ToolHookContext,
  ToolHookDecision,
  ToolResultHookContext,
  TurnEndHookContext,
  TurnId,
  TurnStartHookContext,
} from "@praxis/contracts";
import { InvalidExtensionError, validatePraxisExtension } from "@praxis/contracts";

/**
 * Extension host, v1 (docs/02 section 19, ADR-0013). Instance-scoped by
 * construction: all state lives in this closure, so unloading or dropping a
 * host leaves no residue anywhere (AGENTS.md forbids module-global mutable
 * state in Core). Registration order is the invocation order on every hook;
 * unload removes an extension and later invocations skip it immediately.
 *
 * Failure policy is applied per extension, per hook call:
 * - 'isolate' (default): the error is swallowed and the hook contributes
 *   nothing — telemetry-grade observers cannot break a turn.
 * - 'fail_closed': the error propagates (wrapped with the extension and hook
 *   names) and the EXISTING crash-recovery machinery handles it (docs/02
 *   section 17). There is no extension-specific failure path.
 *
 * Return-shape violations are contract violations, not incidental failures,
 * and throw regardless of policy: a beforeTool returning anything other than
 * a deny, or contributeContext returning non-fragments.
 */

export class DuplicateExtensionError extends Error {
  constructor(name: string) {
    super(`extension ${name} is already registered`);
    this.name = "DuplicateExtensionError";
  }
}

export class ExtensionHookError extends Error {
  constructor(extensionName: string, hookName: ExtensionHookName, cause: unknown) {
    super(
      `extension '${extensionName}' hook ${hookName} failed (fail_closed): ${
        cause instanceof Error ? cause.message : String(cause)
      }`,
    );
    this.name = "ExtensionHookError";
    if (cause instanceof Error) {
      this.cause = cause;
    }
  }
}

/** A beforeTool deny, attributed to the extension that issued it. */
export type ExtensionDenial = {
  readonly extensionName: string;
  readonly decision: ToolHookDecision;
};

export type ExtensionHookInvokers = {
  onTurnStart(context: TurnStartHookContext): Promise<void>;
  contributeContext(context: ContextContributionContext): Promise<readonly ContextFragment[]>;
  beforeModel(context: ModelHookContext): Promise<void>;
  afterModel(context: ModelResultHookContext): Promise<void>;
  /** First deny in registration order wins; undefined means no extension denied. */
  beforeTool(context: ToolHookContext): Promise<ExtensionDenial | undefined>;
  afterTool(context: ToolResultHookContext): Promise<void>;
  onEvent(context: EventHookContext): Promise<void>;
  onTurnEnd(context: TurnEndHookContext): Promise<void>;
};

export type ExtensionHost = {
  /** Registered names in registration order (read-only snapshot). */
  readonly names: readonly string[];
  register(extension: PraxisExtension): void;
  unload(name: string): boolean;
  readonly hooks: ExtensionHookInvokers;
};

export function createExtensionHost(): ExtensionHost {
  const registered: PraxisExtension[] = [];

  const registeredNow = (): readonly PraxisExtension[] => [...registered];

  const guarded = async <T>(
    extension: PraxisExtension,
    hookName: ExtensionHookName,
    call: () => T | Promise<T>,
  ): Promise<T | undefined> => {
    try {
      return await call();
    } catch (error) {
      if (extension.failurePolicy === "fail_closed") {
        throw new ExtensionHookError(extension.name, hookName, error);
      }
      return undefined;
    }
  };

  const host: ExtensionHost = {
    get names(): readonly string[] {
      return registered.map((extension) => extension.name);
    },
    register(extension: PraxisExtension): void {
      validatePraxisExtension(extension);
      if (registered.some((existing) => existing.name === extension.name)) {
        throw new DuplicateExtensionError(extension.name);
      }
      registered.push(extension);
    },
    unload(name: string): boolean {
      const index = registered.findIndex((extension) => extension.name === name);
      if (index === -1) {
        return false;
      }
      registered.splice(index, 1);
      return true;
    },
    hooks: {
      async onTurnStart(context: TurnStartHookContext): Promise<void> {
        for (const extension of registeredNow()) {
          const hook = extension.onTurnStart;
          if (hook === undefined) {
            continue;
          }
          await guarded(extension, "onTurnStart", () => hook(context));
        }
      },
      async contributeContext(
        context: ContextContributionContext,
      ): Promise<readonly ContextFragment[]> {
        const fragments: ContextFragment[] = [];
        for (const extension of registeredNow()) {
          const hook = extension.contributeContext;
          if (hook === undefined) {
            continue;
          }
          const contributed = await guarded(extension, "contributeContext", () => hook(context));
          if (contributed === undefined || contributed === null) {
            continue;
          }
          if (typeof contributed !== "object" || !Array.isArray(contributed)) {
            throw new InvalidExtensionError(
              `extension '${extension.name}' contributeContext returned a non-array (${typeof contributed}); contract violation`,
            );
          }
          // The host stamps `source` itself: an extension can never render a
          // section under another extension's name.
          for (const fragment of contributed) {
            if (
              fragment === null ||
              typeof fragment !== "object" ||
              typeof fragment.text !== "string"
            ) {
              throw new InvalidExtensionError(
                `extension '${extension.name}' contributeContext returned a malformed fragment; contract violation`,
              );
            }
            fragments.push({ source: extension.name, text: fragment.text });
          }
        }
        return fragments;
      },
      async beforeModel(context: ModelHookContext): Promise<void> {
        for (const extension of registeredNow()) {
          const hook = extension.beforeModel;
          if (hook === undefined) {
            continue;
          }
          await guarded(extension, "beforeModel", () => hook(context));
        }
      },
      async afterModel(context: ModelResultHookContext): Promise<void> {
        for (const extension of registeredNow()) {
          const hook = extension.afterModel;
          if (hook === undefined) {
            continue;
          }
          await guarded(extension, "afterModel", () => hook(context));
        }
      },
      async beforeTool(context: ToolHookContext): Promise<ExtensionDenial | undefined> {
        for (const extension of registeredNow()) {
          const hook = extension.beforeTool;
          if (hook === undefined) {
            continue;
          }
          const decision = await guarded(extension, "beforeTool", () => hook(context));
          if (decision === undefined || decision === null) {
            continue;
          }
          if (
            typeof decision === "object" &&
            decision.decision === "deny" &&
            typeof decision.reason === "string"
          ) {
            return { extensionName: extension.name, decision };
          }
          throw new InvalidExtensionError(
            `extension '${extension.name}' beforeTool returned a decision other than deny; only a deny is representable`,
          );
        }
        return undefined;
      },
      async afterTool(context: ToolResultHookContext): Promise<void> {
        for (const extension of registeredNow()) {
          const hook = extension.afterTool;
          if (hook === undefined) {
            continue;
          }
          await guarded(extension, "afterTool", () => hook(context));
        }
      },
      async onEvent(context: EventHookContext): Promise<void> {
        for (const extension of registeredNow()) {
          const hook = extension.onEvent;
          if (hook === undefined) {
            continue;
          }
          await guarded(extension, "onEvent", () => hook(context));
        }
      },
      async onTurnEnd(context: TurnEndHookContext): Promise<void> {
        for (const extension of registeredNow()) {
          const hook = extension.onTurnEnd;
          if (hook === undefined) {
            continue;
          }
          await guarded(extension, "onTurnEnd", () => hook(context));
        }
      },
    },
  };
  return host;
}

/**
 * Wrap an EventStore so every durable append fires onEvent, once per event,
 * after the append succeeds (observe-only; extensions never append). The
 * open turn is tracked from TurnStarted/TurnCompleted facts — no store reads,
 * fully deterministic. A fail_closed onEvent rethrows out of append, which
 * the existing crash-recovery path handles like any crash between effects.
 */
export function observeEventStore(store: EventStore, host: ExtensionHost): EventStore {
  let openTurnId: TurnId | undefined;
  return {
    async append(events: readonly SessionEventUnion[], expectedHeadSeq: number): Promise<void> {
      await store.append(events, expectedHeadSeq);
      for (const event of events) {
        if (event.type === "TurnStarted") {
          openTurnId = event.payload.turnId;
        }
        await host.hooks.onEvent({
          sessionId: event.sessionId,
          turnId: openTurnId,
          event,
        });
        if (event.type === "TurnCompleted") {
          openTurnId = undefined;
        }
      }
    },
    readStream(sessionId: SessionId, afterSeq?: number) {
      return store.readStream(sessionId, afterSeq);
    },
  };
}
