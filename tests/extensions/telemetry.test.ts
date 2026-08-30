import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { SessionEventUnion } from "@praxis/contracts";
import { asEventId, asSessionId, asToolExecutionId, asTurnId } from "@praxis/contracts";
import { type AgentLoopDeps, createExtensionHost, runTurn } from "@praxis/core";
import { createTelemetryObserver, TELEMETRY_EXTENSION_NAME } from "@praxis/extension-telemetry";
import { ScriptedModelProvider, type ScriptItem } from "@praxis/testkit";
import { localReadTools } from "@praxis/tools-local";
import { afterEach, beforeEach, describe, expect, test } from "vitest";
import { inMemoryEventStore } from "../helpers/in-memory-event-store";
import { sessionCreated } from "../helpers/session-events";

/**
 * The telemetry observer is the first shipped consumer of the ADR-0013 seams
 * (M6-T002): every test registers it through the real host into runTurn deps
 * and asserts EXACT counts against the folded stream — never mere >=. The
 * redaction law (docs/02 section 20) is pinned by markers: the serialized
 * snapshot must not contain tool output, model text, or turn input payloads.
 */

const SESSION_ID = asSessionId("session-telemetry");

const PAYLOAD_MARKER = "TELEMETRY-PAYLOAD-7f3a91";
const MODEL_TEXT_MARKER = "TELEMETRY-MODEL-TEXT-2c4d6";
const INPUT_MARKER = "TELEMETRY-INPUT-9b8a7";

const SIGNAL = { signal: new AbortController().signal };
const TEXT = (text: string): ScriptItem => ({ kind: "event", event: { type: "textDelta", text } });
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
  TEXT(`All done. ${MODEL_TEXT_MARKER}`),
  { kind: "event", event: { type: "completed", finishReason: "stop" } },
];
const PROVIDER_ERROR: ScriptItem[] = [
  {
    kind: "event",
    event: {
      type: "providerError",
      error: { kind: "rateLimit", retryable: true, message: "slow down" },
    },
  },
];

let root: string;
beforeEach(async () => {
  root = await mkdtemp(join(tmpdir(), "praxis-telemetry-"));
  await writeFile(join(root, "note.txt"), `secret body ${PAYLOAD_MARKER} end`);
});
afterEach(async () => {
  await rm(root, { recursive: true, force: true });
});

function loopDeps(
  model: ScriptedModelProvider,
  extensions: AgentLoopDeps["extensions"],
): AgentLoopDeps {
  let counter = 5000;
  let turns = 0;
  let executions = 0;
  return {
    store: inMemoryEventStore(),
    sessionId: SESSION_ID,
    model,
    modelId: "scripted-model",
    systemPrompt: "You are the telemetry observer harness.",
    tools: localReadTools(root),
    now: () => {
      counter += 1;
      return counter;
    },
    newEventId: () => asEventId(`tel-${counter}`),
    newTurnId: () => {
      turns += 1;
      return asTurnId(`tel-turn-${turns}`);
    },
    newToolExecutionId: () => {
      executions += 1;
      return asToolExecutionId(`tel-exec-${executions}`);
    },
    ...(extensions === undefined ? {} : { extensions }),
  };
}

async function seedSession(deps: AgentLoopDeps): Promise<void> {
  await deps.store.append([{ ...sessionCreated(1), sessionId: SESSION_ID }], 0);
}

async function runToolTurn(deps: AgentLoopDeps): Promise<readonly SessionEventUnion[]> {
  await seedSession(deps);
  const outcome = await runTurn(deps, { input: `read the note ${INPUT_MARKER}` }, SIGNAL);
  expect(outcome.kind).toBe("completed");
  return deps.store.readStream(SESSION_ID);
}

/** Every +1 clock: each now() call advances by exactly one step. */
function stepClock(): () => number {
  let ticks = 0;
  return () => {
    ticks += 1;
    return ticks;
  };
}

function typeHistogram(events: readonly SessionEventUnion[]): Record<string, number> {
  const histogram: Record<string, number> = {};
  for (const event of events) {
    histogram[event.type] = (histogram[event.type] ?? 0) + 1;
  }
  return histogram;
}

describe("telemetry observer over the real extension host", () => {
  test("snapshot histograms exactly equal the folded stream over a tool-calling turn", async () => {
    const observer = createTelemetryObserver({ now: stepClock() });
    const host = createExtensionHost();
    host.register(observer.extension);

    const provider = new ScriptedModelProvider(TOOL_CALL, FINAL_LINE);
    const deps = loopDeps(provider, host);
    const events = await runToolTurn(deps);

    // The observing store only sees the turn's own appends (the seed append
    // happened on the raw store), so the expected histogram is the stream
    // minus SessionCreated — exact equality, not a subset check.
    const turnEvents = events.filter((event) => event.type !== "SessionCreated");
    const snapshot = observer.snapshot();
    expect(snapshot.events).toEqual(typeHistogram(turnEvents));
    expect(snapshot.totalEvents).toBe(turnEvents.length);

    expect(snapshot.turns).toEqual({
      started: 1,
      ended: 1,
      byOutcome: { completed: 1, paused: 0, cancelled: 0 },
      durationsMs: [5],
    });
    expect(snapshot.model).toEqual({
      requests: 2,
      byResult: { completed: 2, providerError: 0, endedSilently: 0 },
      toolCalls: 1,
      latenciesMs: [1, 1],
      totalLatencyMs: 2,
    });
    expect(snapshot.tools).toEqual({
      read_file: { REJECTED: 0, SUCCEEDED: 1, FAILED: 0, INDETERMINATE: 0 },
    });
  });

  test("redaction is structural: no payload marker ever reaches the snapshot", async () => {
    const observer = createTelemetryObserver({ now: stepClock() });
    const host = createExtensionHost();
    host.register(observer.extension);

    const provider = new ScriptedModelProvider(TOOL_CALL, FINAL_LINE);
    const deps = loopDeps(provider, host);
    const events = await runToolTurn(deps);

    // Sanity: the markers really are in the stream (tool result and model
    // text carried them), so their absence from the snapshot is meaningful.
    const stream = JSON.stringify(events);
    expect(stream).toContain(PAYLOAD_MARKER);
    expect(stream).toContain(MODEL_TEXT_MARKER);

    const serialized = JSON.stringify(observer.snapshot());
    expect(serialized).not.toContain(PAYLOAD_MARKER);
    expect(serialized).not.toContain(MODEL_TEXT_MARKER);
    expect(serialized).not.toContain(INPUT_MARKER);
    expect(serialized).not.toContain("note.txt");
  });

  test("injected clock determinism: two identical runs produce identical snapshots", async () => {
    const runOnce = () => {
      const observer = createTelemetryObserver({ now: stepClock() });
      const host = createExtensionHost();
      host.register(observer.extension);
      return runToolTurn(loopDeps(new ScriptedModelProvider(TOOL_CALL, FINAL_LINE), host)).then(
        () => observer,
      );
    };

    const first = await runOnce();
    const second = await runOnce();
    expect(second.snapshot()).toEqual(first.snapshot());
    expect(first.snapshot().model.latenciesMs).toEqual([1, 1]);
    expect(first.snapshot().turns.durationsMs).toEqual([5]);
  });

  test("provider errors are counted by result kind and the turn still completes", async () => {
    const observer = createTelemetryObserver({ now: stepClock() });
    const host = createExtensionHost();
    host.register(observer.extension);

    const provider = new ScriptedModelProvider(PROVIDER_ERROR, FINAL_LINE);
    const deps = loopDeps(provider, host);
    await seedSession(deps);
    const outcome = await runTurn(deps, { input: "summarize" }, SIGNAL);
    expect(outcome.kind).toBe("completed");

    const events = await deps.store.readStream(SESSION_ID);
    const turnEvents = events.filter((event) => event.type !== "SessionCreated");
    const snapshot = observer.snapshot();
    expect(snapshot.model.byResult).toEqual({
      completed: 1,
      providerError: 1,
      endedSilently: 0,
    });
    expect(snapshot.model.requests).toBe(2);
    expect(snapshot.events).toEqual(typeHistogram(turnEvents));
    expect(snapshot.events.ModelRequestFailed).toBe(1);
  });

  test("a throwing sink on every record leaves the turn unbroken and counts intact", async () => {
    const observer = createTelemetryObserver({
      now: stepClock(),
      sink: () => {
        throw new Error("sink down");
      },
    });
    const host = createExtensionHost();
    host.register(observer.extension);

    const provider = new ScriptedModelProvider(TOOL_CALL, FINAL_LINE);
    const deps = loopDeps(provider, host);
    const events = await runToolTurn(deps);

    expect(events.map((event) => event.type)).toContain("ToolSucceeded");
    expect(events.at(-1)?.type).toBe("TurnCompleted");
    // Counters increment before the sink runs, so the snapshot is complete
    // and accurate even though every sink call threw (host isolate policy).
    const turnEvents = events.filter((event) => event.type !== "SessionCreated");
    expect(observer.snapshot().totalEvents).toBe(turnEvents.length);
    expect(observer.snapshot().tools.read_file?.SUCCEEDED).toBe(1);
  });

  test("a deny from another extension is counted REJECTED; telemetry never sits on the veto path", async () => {
    const observer = createTelemetryObserver({ now: stepClock() });
    const host = createExtensionHost();
    host.register(observer.extension);
    host.register({
      name: "deny-reads",
      beforeTool: () => ({ decision: "deny", reason: "reads are paused" }),
    });

    const provider = new ScriptedModelProvider(TOOL_CALL, FINAL_LINE);
    const deps = loopDeps(provider, host);
    await seedSession(deps);
    const outcome = await runTurn(deps, { input: "read the note" }, SIGNAL);
    expect(outcome.kind).toBe("completed");

    const events = await deps.store.readStream(SESSION_ID);
    expect(events.map((event) => event.type)).toContain("ToolRejected");
    const snapshot = observer.snapshot();
    expect(snapshot.tools).toEqual({
      read_file: { REJECTED: 1, SUCCEEDED: 0, FAILED: 0, INDETERMINATE: 0 },
    });
  });

  test("unload freezes counting: a later turn grows zero counters, snapshot stays readable", async () => {
    const observer = createTelemetryObserver({ now: stepClock() });
    const host = createExtensionHost();
    host.register(observer.extension);

    // One provider, three scripts: turn 1 consumes the tool script and the
    // first final line; turn 2 (after unload) consumes the second.
    const deps = loopDeps(new ScriptedModelProvider(TOOL_CALL, FINAL_LINE, FINAL_LINE), host);
    await runToolTurn(deps);
    const before = observer.snapshot();

    expect(host.unload(TELEMETRY_EXTENSION_NAME)).toBe(true);
    expect(host.names).toEqual([]);

    const outcome = await runTurn(deps, { input: "summarize" }, SIGNAL);
    expect(outcome.kind).toBe("completed");
    const after = observer.snapshot();
    expect(after).toEqual(before);
    expect(Object.isFrozen(after)).toBe(true);
    expect(Object.isFrozen(after.tools)).toBe(true);
    expect(Object.isFrozen(after.model)).toBe(true);
  });
});
