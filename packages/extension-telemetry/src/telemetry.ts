import type {
  EventHookContext,
  ExtensionToolResultStatus,
  ModelResultHookContext,
  PraxisExtension,
  ToolResultHookContext,
  TurnEndHookContext,
  TurnStartHookContext,
} from "@praxis/contracts";

/**
 * Read-only telemetry observer over the ADR-0013 seams (docs/02 section 19).
 * The first shipped consumer of the extension surface: it proves an extension
 * can observe turns, model results, tool outcomes, and events WITHOUT editing
 * packages/core — and that the redaction law (docs/02 section 20: never write
 * secrets or full sensitive tool output to telemetry) can be structural.
 *
 * The snapshot schema carries only counts, durations, outcome/status enums,
 * tool names, and event type names. No field can hold tool arguments, tool
 * output, model text, or provider payloads, so no hook bug can leak them.
 *
 * The extension deliberately does NOT implement contributeContext (an
 * observe-only extension adds zero prompt bytes) and NOT beforeTool (the veto
 * path is for policy extensions; telemetry has no opinion). Hooks are six of
 * the eight: onTurnStart, beforeModel, afterModel, afterTool, onEvent,
 * onTurnEnd.
 *
 * failurePolicy is 'isolate' (docs/02 section 19: telemetry defaults
 * non-blocking). Sink errors are NOT caught here on purpose: the host's
 * isolate policy swallows them, which is exactly the law this package rides.
 */

export type TelemetryTurnOutcomeKind = "completed" | "paused" | "cancelled";
export type TelemetryModelResultKind = "completed" | "providerError" | "endedSilently";

/** One observed fact, handed to the optional sink (names/enums/numbers only). */
export type TelemetryRecord =
  | { readonly kind: "turnStarted"; readonly turnId: string }
  | {
      readonly kind: "turnEnded";
      readonly turnId: string | undefined;
      readonly outcome: TelemetryTurnOutcomeKind;
      /** Undefined when the host never saw this turn open (pre-turn reconciliation pause). */
      readonly durationMs: number | undefined;
    }
  | {
      readonly kind: "modelResult";
      readonly turnId: string;
      readonly result: TelemetryModelResultKind;
      readonly latencyMs: number;
      readonly toolCalls: number;
    }
  | {
      readonly kind: "toolResult";
      readonly turnId: string;
      readonly name: string;
      readonly status: ExtensionToolResultStatus;
    }
  | { readonly kind: "event"; readonly type: string };

export type TelemetrySnapshot = {
  readonly turns: {
    readonly started: number;
    readonly ended: number;
    readonly byOutcome: Readonly<Record<TelemetryTurnOutcomeKind, number>>;
    /** Only turns whose start this observer saw; unordered. */
    readonly durationsMs: readonly number[];
  };
  readonly model: {
    readonly requests: number;
    readonly byResult: Readonly<Record<TelemetryModelResultKind, number>>;
    readonly toolCalls: number;
    readonly latenciesMs: readonly number[];
    readonly totalLatencyMs: number;
  };
  /** Per tool name, per terminal status (including REJECTED). */
  readonly tools: Readonly<Record<string, Readonly<Record<ExtensionToolResultStatus, number>>>>;
  /** Per durable event type appended while this observer was registered. */
  readonly events: Readonly<Record<string, number>>;
  readonly totalEvents: number;
};

export type TelemetryOptions = {
  /** Injectable for determinism; defaults to Date.now. */
  readonly now?: () => number;
  /** Called with every observed record; errors are isolated by the host policy. */
  readonly sink?: (record: TelemetryRecord) => void;
};

export type TelemetryObserver = {
  /** The extension value to register into a core extension host. */
  readonly extension: PraxisExtension;
  /** Frozen point-in-time copy; readable at any time, including after unload. */
  snapshot(): TelemetrySnapshot;
};

export const TELEMETRY_EXTENSION_NAME = "telemetry-observer";

function zeroOutcomeCounts(): Record<TelemetryTurnOutcomeKind, number> {
  return { completed: 0, paused: 0, cancelled: 0 };
}

function zeroModelResultCounts(): Record<TelemetryModelResultKind, number> {
  return { completed: 0, providerError: 0, endedSilently: 0 };
}

function zeroStatusCounts(): Record<ExtensionToolResultStatus, number> {
  return { REJECTED: 0, SUCCEEDED: 0, FAILED: 0, INDETERMINATE: 0 };
}

function bump(map: Record<string, number>, key: string): void {
  map[key] = (map[key] ?? 0) + 1;
}

function frozenCopy(map: Record<string, number>): Readonly<Record<string, number>> {
  return Object.freeze({ ...map });
}

export function createTelemetryObserver(options?: TelemetryOptions): TelemetryObserver {
  const now = options?.now ?? Date.now;
  const sink = options?.sink;

  // Closure-scoped working state only (AGENTS.md: no module-global state).
  let turnsStarted = 0;
  let turnsEnded = 0;
  const turnsByOutcome = zeroOutcomeCounts();
  const turnDurationsMs: number[] = [];
  const turnStartedAt = new Map<string, number>();

  let modelRequests = 0;
  const modelByResult = zeroModelResultCounts();
  let modelToolCalls = 0;
  const modelLatenciesMs: number[] = [];
  let modelTotalLatencyMs = 0;
  // The agent loop runs one model step at a time, so the last beforeModel
  // timestamp is unambiguously the start of the afterModel now closing.
  let lastModelStartedAt: number | undefined;

  const toolCounts = new Map<string, Record<ExtensionToolResultStatus, number>>();
  const eventCounts: Record<string, number> = {};
  let totalEvents = 0;

  const emit = (record: TelemetryRecord): void => {
    sink?.(record);
  };

  const extension: PraxisExtension = {
    name: TELEMETRY_EXTENSION_NAME,
    failurePolicy: "isolate",

    onTurnStart(context: TurnStartHookContext): void {
      turnsStarted += 1;
      turnStartedAt.set(context.turnId, now());
      emit({ kind: "turnStarted", turnId: context.turnId });
    },

    beforeModel(): void {
      lastModelStartedAt = now();
    },

    afterModel(context: ModelResultHookContext): void {
      const startedAt = lastModelStartedAt;
      lastModelStartedAt = undefined;
      const latencyMs = startedAt === undefined ? 0 : Math.max(0, now() - startedAt);
      modelRequests += 1;
      const result = context.result.kind;
      modelByResult[result] += 1;
      if (result === "completed") {
        modelToolCalls += context.result.toolCalls.length;
      }
      modelLatenciesMs.push(latencyMs);
      modelTotalLatencyMs += latencyMs;
      emit({
        kind: "modelResult",
        turnId: context.turnId,
        result,
        latencyMs,
        toolCalls: result === "completed" ? context.result.toolCalls.length : 0,
      });
    },

    afterTool(context: ToolResultHookContext): void {
      let byStatus = toolCounts.get(context.name);
      if (byStatus === undefined) {
        byStatus = zeroStatusCounts();
        toolCounts.set(context.name, byStatus);
      }
      byStatus[context.status] += 1;
      emit({
        kind: "toolResult",
        turnId: context.turnId,
        name: context.name,
        status: context.status,
      });
    },

    onEvent(context: EventHookContext): void {
      totalEvents += 1;
      bump(eventCounts, context.event.type);
      emit({ kind: "event", type: context.event.type });
    },

    onTurnEnd(context: TurnEndHookContext): void {
      turnsEnded += 1;
      const outcome: TelemetryTurnOutcomeKind = context.outcome.kind;
      turnsByOutcome[outcome] += 1;
      const startedAt =
        context.turnId === undefined ? undefined : turnStartedAt.get(context.turnId);
      const durationMs = startedAt === undefined ? undefined : Math.max(0, now() - startedAt);
      if (durationMs !== undefined) {
        turnDurationsMs.push(durationMs);
      }
      if (context.turnId !== undefined) {
        turnStartedAt.delete(context.turnId);
      }
      emit({ kind: "turnEnded", turnId: context.turnId, outcome, durationMs });
    },
  };

  const snapshot = (): TelemetrySnapshot => {
    const tools: Record<string, Readonly<Record<ExtensionToolResultStatus, number>>> = {};
    for (const [name, byStatus] of toolCounts) {
      tools[name] = Object.freeze({ ...byStatus });
    }
    const snapshotValue: TelemetrySnapshot = {
      turns: Object.freeze({
        started: turnsStarted,
        ended: turnsEnded,
        byOutcome: Object.freeze({ ...turnsByOutcome }),
        durationsMs: Object.freeze([...turnDurationsMs]),
      }),
      model: Object.freeze({
        requests: modelRequests,
        byResult: Object.freeze({ ...modelByResult }),
        toolCalls: modelToolCalls,
        latenciesMs: Object.freeze([...modelLatenciesMs]),
        totalLatencyMs: modelTotalLatencyMs,
      }),
      tools: Object.freeze(tools),
      events: frozenCopy(eventCounts),
      totalEvents,
    };
    return Object.freeze(snapshotValue);
  };

  return { extension, snapshot };
}
