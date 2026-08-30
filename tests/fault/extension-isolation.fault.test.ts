import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type {
  EventStore,
  ModelRequest,
  PraxisExtension,
  SessionEventUnion,
} from "@praxis/contracts";
import { asEventId, asSessionId, asToolExecutionId, asTurnId } from "@praxis/contracts";
import { type AgentLoopDeps, createExtensionHost, foldSessionEvents, runTurn } from "@praxis/core";
import { createStandingOrdersExtension } from "@praxis/extension-standing-orders";
import { createTelemetryObserver } from "@praxis/extension-telemetry";
import { ScriptedModelProvider, type ScriptItem } from "@praxis/testkit";
import { localReadTools } from "@praxis/tools-local";
import { afterEach, beforeEach, describe, expect, test } from "vitest";
import { inMemoryEventStore } from "../helpers/in-memory-event-store";
import { sessionCreated } from "../helpers/session-events";

/**
 * Extension unload and failure isolation audit (M6-T004, docs/02 sections 17
 * and 19, ADR-0013) over the SHIPPED extensions composed in one host through
 * the real loop. The host snapshots its extension list per hook invocation,
 * so this suite pins the two unload boundaries: an unload landing BETWEEN
 * hooks takes effect immediately for the rest of the turn; an unload fired
 * INSIDE one hook's iteration lets the already-snapshotted sibling contribute
 * for that hook only. Neither may throw or corrupt the stream. An isolate
 * failure in one shipped extension must be invisible in the durable facts;
 * a fail_closed sibling crash must leave observer state coherent with the
 * persisted prefix and the session resumable.
 */

const SESSION_ID = asSessionId("session-ext-isolation");
const SIGNAL = { signal: new AbortController().signal };
const TOOL_CALL: ScriptItem[] = [
  { kind: "event", event: { type: "toolCallStart", toolCallId: "call-1", name: "read_file" } },
  {
    kind: "event",
    event: { type: "toolCallDelta", toolCallId: "call-1", argumentsDelta: '{"path":"note.' },
  },
  {
    kind: "event",
    event: { type: "toolCallDelta", toolCallId: "call-1", argumentsDelta: 'txt"}' },
  },
  { kind: "event", event: { type: "toolCallEnd", toolCallId: "call-1" } },
  { kind: "event", event: { type: "completed", finishReason: "toolCalls" } },
];
const FINAL_LINE: ScriptItem[] = [
  { kind: "event", event: { type: "textDelta", text: "All done." } },
  { kind: "event", event: { type: "completed", finishReason: "stop" } },
];

let root: string;
beforeEach(async () => {
  root = await mkdtemp(join(tmpdir(), "praxis-ext-isolation-"));
  await writeFile(join(root, "note.txt"), "isolation audit note");
});
afterEach(async () => {
  await rm(root, { recursive: true, force: true });
});

function loopDeps(
  model: ScriptedModelProvider,
  extensions: AgentLoopDeps["extensions"],
  store: EventStore = inMemoryEventStore(),
): AgentLoopDeps {
  let counter = 9000;
  let turns = 0;
  let executions = 0;
  return {
    store,
    sessionId: SESSION_ID,
    model,
    modelId: "scripted-model",
    systemPrompt: "You are the isolation audit harness.",
    tools: localReadTools(root),
    now: () => {
      counter += 1;
      return counter;
    },
    newEventId: () => asEventId(`iso-${counter}`),
    newTurnId: () => {
      turns += 1;
      return asTurnId(`iso-turn-${turns}`);
    },
    newToolExecutionId: () => {
      executions += 1;
      return asToolExecutionId(`iso-exec-${executions}`);
    },
    ...(extensions === undefined ? {} : { extensions }),
  };
}

async function seed(deps: AgentLoopDeps): Promise<void> {
  await deps.store.append([{ ...sessionCreated(1), sessionId: SESSION_ID }], 0);
}

function streamFingerprint(events: readonly SessionEventUnion[]): string {
  return JSON.stringify(events.map((event) => [event.seq, event.type, event.payload]));
}

function requestFingerprint(request: ModelRequest): string {
  return JSON.stringify(request);
}

const systemText = (provider: ScriptedModelProvider, index: number): string =>
  provider.requests[index]?.messages[0]?.text ?? "";

describe("unload and failure isolation across shipped extensions", () => {
  test("mid-turn unload between hook boundaries: the policy is gone for the rest of the turn", async () => {
    const host = createExtensionHost();
    const observer = createTelemetryObserver();
    host.register(observer.extension);
    host.register(
      createStandingOrdersExtension({
        instructions: "Always cite the file you read.",
        deniedTools: ["read_file"],
      }),
    );
    // Fires after the two shipped extensions' onTurnStart (registration
    // order) and unloads the policy BEFORE contributeContext ever runs.
    const unloader: PraxisExtension = {
      name: "unloader",
      onTurnStart: () => {
        expect(host.unload("standing-orders")).toBe(true);
      },
    };
    host.register(unloader);

    const provider = new ScriptedModelProvider(TOOL_CALL, FINAL_LINE);
    const deps = loopDeps(provider, host);
    await seed(deps);
    const outcome = await runTurn(deps, { input: "read the note" }, SIGNAL);
    expect(outcome.kind).toBe("completed");

    // No section rendered, and the would-be denied tool EXECUTED: beforeTool
    // never consulted the unloaded policy.
    expect(systemText(provider, 0)).not.toContain("## Extension: standing-orders");
    const types = (await deps.store.readStream(SESSION_ID)).map((event) => event.type);
    expect(types).toContain("ToolSucceeded");
    expect(types).not.toContain("ToolRejected");
    expect(types.at(-1)).toBe("TurnCompleted");

    // M6.yaml: unload does not corrupt state — the stream folds legally.
    const stream = await deps.store.readStream(SESSION_ID);
    expect(() => foldSessionEvents(stream)).not.toThrow();

    // The observer (registered before the unload) counted the full turn.
    expect(observer.snapshot().tools).toEqual({
      read_file: { REJECTED: 0, SUCCEEDED: 1, FAILED: 0, INDETERMINATE: 0 },
    });
    expect(observer.snapshot().turns.byOutcome.completed).toBe(1);
  });

  test("unload inside one hook's iteration: the snapshotted sibling contributes for that hook only", async () => {
    const host = createExtensionHost();
    // Registered FIRST: its contributeContext unloads the sibling mid-hook
    // iteration, then contributes its own fragment.
    const lead: PraxisExtension = {
      name: "lead-contributor",
      contributeContext: () => {
        host.unload("standing-orders");
        return [{ source: "lead-contributor", text: "lead contributor still here" }];
      },
    };
    host.register(lead);
    host.register(
      createStandingOrdersExtension({ instructions: "Always cite the file you read." }),
    );

    const provider = new ScriptedModelProvider(FINAL_LINE, FINAL_LINE);
    const deps = loopDeps(provider, host);
    await seed(deps);
    const first = await runTurn(deps, { input: "one" }, SIGNAL);
    expect(first.kind).toBe("completed");
    const second = await runTurn(deps, { input: "two" }, SIGNAL);
    expect(second.kind).toBe("completed");

    // Turn 1: the snapshot already contained standing-orders, so BOTH
    // sections render — the unload lands at the next hook boundary, no throw.
    expect(systemText(provider, 0)).toContain("## Extension: lead-contributor");
    expect(systemText(provider, 0)).toContain("## Extension: standing-orders");
    // Turn 2: only the lead remains.
    expect(systemText(provider, 1)).toContain("## Extension: lead-contributor");
    expect(systemText(provider, 1)).not.toContain("## Extension: standing-orders");
    expect(host.names).toEqual(["lead-contributor"]);

    const events = await deps.store.readStream(SESSION_ID);
    expect(events.filter((event) => event.type === "TurnCompleted")).toHaveLength(2);
    expect(() => foldSessionEvents(events)).not.toThrow();
  });

  test("an isolate telemetry failure is invisible next to a fail_closed policy: stream identity", async () => {
    const orders = () =>
      createStandingOrdersExtension({
        instructions: "Always cite the file you read.",
        deniedTools: ["read_file"],
      });

    const aloneHost = createExtensionHost();
    aloneHost.register(orders());
    const aloneProvider = new ScriptedModelProvider(TOOL_CALL, FINAL_LINE);
    const alone = loopDeps(aloneProvider, aloneHost);
    await seed(alone);
    const aloneOutcome = await runTurn(alone, { input: "read the note" }, SIGNAL);
    const aloneEvents = await alone.store.readStream(SESSION_ID);

    const observer = createTelemetryObserver({
      sink: () => {
        throw new Error("sink down");
      },
    });
    const mixedHost = createExtensionHost();
    mixedHost.register(observer.extension);
    mixedHost.register(orders());
    const mixedProvider = new ScriptedModelProvider(TOOL_CALL, FINAL_LINE);
    const mixed = loopDeps(mixedProvider, mixedHost);
    await seed(mixed);
    const mixedOutcome = await runTurn(mixed, { input: "read the note" }, SIGNAL);
    const mixedEvents = await mixed.store.readStream(SESSION_ID);

    // The dead sink changed nothing durable: identical outcome, stream, and
    // both model requests (the first carries the section).
    expect(mixedOutcome).toEqual(aloneOutcome);
    expect(streamFingerprint(mixedEvents)).toBe(streamFingerprint(aloneEvents));
    expect(requestFingerprint(mixedProvider.requests[0] as ModelRequest)).toBe(
      requestFingerprint(aloneProvider.requests[0] as ModelRequest),
    );

    // The policy still bit (deny landed, no execution) while the observer —
    // failing on every single record — still counted everything.
    expect(mixedEvents.map((event) => event.type)).toContain("ToolRejected");
    expect(mixedEvents.map((event) => event.type)).not.toContain("ToolStarted");
    expect(observer.snapshot().tools).toEqual({
      read_file: { REJECTED: 1, SUCCEEDED: 0, FAILED: 0, INDETERMINATE: 0 },
    });
  });

  test("a fail_closed sibling crash: legal prefix, coherent observer state, successful resume", async () => {
    const host = createExtensionHost();
    const observer = createTelemetryObserver();
    host.register(observer.extension);
    const crasher: PraxisExtension = {
      name: "after-model-crasher",
      failurePolicy: "fail_closed",
      afterModel: () => {
        throw new Error("audit boom");
      },
    };
    host.register(crasher);

    const provider = new ScriptedModelProvider(FINAL_LINE);
    const deps = loopDeps(provider, host);
    await seed(deps);
    await expect(runTurn(deps, { input: "begin" }, SIGNAL)).rejects.toThrow(
      "extension 'after-model-crasher' hook afterModel failed (fail_closed): audit boom",
    );

    // afterModel fires BEFORE the ModelResponseCompleted append, so the
    // durable prefix ends at ModelRequestStarted and folds legally.
    const events = await deps.store.readStream(SESSION_ID);
    expect(events.map((event) => event.type)).toEqual([
      "SessionCreated",
      "TurnStarted",
      "ModelRequestStarted",
    ]);
    const folded = foldSessionEvents(events);
    expect(folded.pendingModelRequest).toBeDefined();
    expect(folded.currentTurnId?.valueOf()).toBe("iso-turn-1");

    // Coherent observer state at crash time: it observed exactly the two
    // turn events that persisted, and its own afterModel (invoked before the
    // crasher's, in registration order) recorded the model call that DID
    // happen — the resume will write the honest ModelRequestFailed fact for
    // the durable record.
    const snapshot = observer.snapshot();
    expect(snapshot.totalEvents).toBe(2);
    expect(snapshot.model.requests).toBe(1);
    expect(snapshot.model.byResult.completed).toBe(1);
    expect(snapshot.turns).toEqual({
      started: 1,
      ended: 0,
      byOutcome: { completed: 0, paused: 0, cancelled: 0 },
      durationsMs: [],
    });

    // The standard recovery closes the turn; the unwired observer's state
    // does not change across the resumed process boundary.
    const resumed = loopDeps(new ScriptedModelProvider(FINAL_LINE), undefined, deps.store);
    const outcome = await runTurn(resumed, {}, SIGNAL);
    expect(outcome).toEqual({ kind: "completed", finalText: "All done." });
    expect(observer.snapshot()).toEqual(snapshot);
    expect((await deps.store.readStream(SESSION_ID)).map((event) => event.type)).toEqual([
      "SessionCreated",
      "TurnStarted",
      "ModelRequestStarted",
      "ModelRequestFailed",
      "ModelRequestStarted",
      "ModelResponseCompleted",
      "TurnCompleted",
    ]);
  });
});
