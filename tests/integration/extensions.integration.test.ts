import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { ModelRequest, PraxisExtension, SessionEventUnion } from "@praxis/contracts";
import { asEventId, asSessionId, asToolExecutionId, asTurnId } from "@praxis/contracts";
import {
  type AgentLoopDeps,
  ContextBudgetExceededError,
  createExtensionHost,
  runTurn,
} from "@praxis/core";
import { ScriptedModelProvider, type ScriptItem } from "@praxis/testkit";
import { localReadTools } from "@praxis/tools-local";
import { afterEach, beforeEach, describe, expect, test } from "vitest";
import { inMemoryEventStore } from "../helpers/in-memory-event-store";
import { sessionCreated } from "../helpers/session-events";

/**
 * Extension seams through the real loop (docs/02 section 19, ADR-0013): a
 * test-file extension registers out-of-core, observes a full turn in the
 * documented hook order, contributes a capped context fragment, denies a
 * tool call into an explicit ToolRejected — and writes zero durable events:
 * the stream and the model request are identical to an extension-free run.
 */

const SESSION_ID = asSessionId("session-ext-integration");

let root: string;
beforeEach(async () => {
  root = await mkdtemp(join(tmpdir(), "praxis-ext-"));
  await writeFile(join(root, "note.txt"), "extension integration note");
});
afterEach(async () => {
  await rm(root, { recursive: true, force: true });
});

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
  TEXT("All done."),
  { kind: "event", event: { type: "completed", finishReason: "stop" } },
];

function loopDeps(
  model: ScriptedModelProvider,
  extensions: AgentLoopDeps["extensions"],
): AgentLoopDeps {
  let counter = 5000;
  let turns = 0;
  let executions = 0;
  const store = inMemoryEventStore();
  return {
    store,
    sessionId: SESSION_ID,
    model,
    modelId: "scripted-model",
    systemPrompt: "You are the extension integration harness.",
    tools: localReadTools(root),
    now: () => {
      counter += 1;
      return counter;
    },
    newEventId: () => asEventId(`ext-int-${counter}`),
    newTurnId: () => {
      turns += 1;
      return asTurnId(`ext-int-turn-${turns}`);
    },
    newToolExecutionId: () => {
      executions += 1;
      return asToolExecutionId(`ext-int-exec-${executions}`);
    },
    ...(extensions === undefined ? {} : { extensions }),
  };
}

async function seedSession(deps: AgentLoopDeps): Promise<void> {
  await deps.store.append([{ ...sessionCreated(1), sessionId: SESSION_ID }], 0);
}

function observingExtension(log: string[], fragments: string[] = []): PraxisExtension {
  return {
    name: "observer",
    onTurnStart: (context) => {
      log.push(`onTurnStart:${context.turnId.valueOf()}`);
    },
    contributeContext: () => {
      log.push("contributeContext");
      return fragments.map((text) => ({ source: "observer", text }));
    },
    beforeModel: (context) => {
      log.push(`beforeModel:${context.request.messages.length}`);
    },
    afterModel: (context) => {
      log.push(`afterModel:${context.result.kind}`);
    },
    beforeTool: (context) => {
      log.push(`beforeTool:${context.name}`);
      return undefined;
    },
    afterTool: (context) => {
      log.push(`afterTool:${context.status}`);
    },
    onEvent: (context) => {
      log.push(`onEvent:${context.event.type}`);
    },
    onTurnEnd: (context) => {
      log.push(`onTurnEnd:${context.outcome.kind}`);
    },
  };
}

function streamFingerprint(events: readonly SessionEventUnion[]): string {
  return JSON.stringify(events.map((event) => [event.seq, event.type, event.payload]));
}

function requestFingerprint(request: ModelRequest): string {
  return JSON.stringify(request);
}

describe("extension seams through runTurn", () => {
  test("hooks fire in the documented order across a tool-calling turn", async () => {
    const host = createExtensionHost();
    const log: string[] = [];
    host.register(observingExtension(log));

    const provider = new ScriptedModelProvider(TOOL_CALL, FINAL_LINE);
    const deps = loopDeps(provider, host);
    await seedSession(deps);

    const outcome = await runTurn(deps, { input: "read the note" }, SIGNAL);
    expect(outcome).toEqual({ kind: "completed", finalText: "All done." });

    expect(log).toEqual([
      "onEvent:TurnStarted",
      "onTurnStart:ext-int-turn-1",
      "contributeContext",
      "onEvent:ModelRequestStarted",
      "beforeModel:2",
      "afterModel:completed",
      "onEvent:ModelResponseCompleted",
      "onEvent:ToolProposed",
      "beforeTool:read_file",
      "onEvent:ToolAuthorized",
      "onEvent:ToolStarted",
      "onEvent:ToolSucceeded",
      "afterTool:SUCCEEDED",
      "contributeContext",
      "onEvent:ModelRequestStarted",
      "beforeModel:4",
      "afterModel:completed",
      "onEvent:ModelResponseCompleted",
      "onEvent:TurnCompleted",
      "onTurnEnd:completed",
    ]);
  });

  test("zero-extension identity: an observing extension leaves stream and request byte-identical", async () => {
    const bareProvider = new ScriptedModelProvider(TOOL_CALL, FINAL_LINE);
    const bare = loopDeps(bareProvider, undefined);
    await seedSession(bare);
    const bareOutcome = await runTurn(bare, { input: "read the note" }, SIGNAL);
    const bareEvents = await bare.store.readStream(SESSION_ID);

    const host = createExtensionHost();
    const log: string[] = [];
    host.register(observingExtension(log));
    const observedProvider = new ScriptedModelProvider(TOOL_CALL, FINAL_LINE);
    const observed = loopDeps(observedProvider, host);
    await seedSession(observed);
    const observedOutcome = await runTurn(observed, { input: "read the note" }, SIGNAL);
    const observedEvents = await observed.store.readStream(SESSION_ID);

    expect(observedOutcome).toEqual(bareOutcome);
    expect(streamFingerprint(observedEvents)).toBe(streamFingerprint(bareEvents));
    expect(requestFingerprint(observedProvider.requests[1] as ModelRequest)).toBe(
      requestFingerprint(bareProvider.requests[1] as ModelRequest),
    );
    expect(log.length).toBeGreaterThan(0);
  });

  test("a contributed fragment renders as a capped '## Extension' section after the prompt", async () => {
    const host = createExtensionHost();
    host.register(observingExtension([], ["remember the backup schedule"]));
    const provider = new ScriptedModelProvider(FINAL_LINE);
    const deps = loopDeps(provider, host);
    await seedSession(deps);

    const outcome = await runTurn(deps, { input: "summarize" }, SIGNAL);
    expect(outcome.kind).toBe("completed");

    const system = provider.requests[0]?.messages[0];
    expect(system?.role).toBe("system");
    expect(system?.text).toContain("## Extension: observer");
    expect(system?.text).toContain("remember the backup schedule");
    // The section lands after the base prompt, never inside it.
    const systemText = system?.text ?? "";
    expect(systemText.indexOf("## Extension: observer")).toBeGreaterThan(
      systemText.indexOf("extension integration harness"),
    );
  });

  test("an over-budget fragment set fails closed through the existing budget law", async () => {
    const host = createExtensionHost();
    host.register(observingExtension([], ["x".repeat(200)]));
    const provider = new ScriptedModelProvider(FINAL_LINE);
    const deps = loopDeps(provider, host);
    await seedSession(deps);

    await expect(
      runTurn(
        deps,
        { input: "summarize" },
        {
          ...SIGNAL,
          budget: {
            maxRecentMessages: 8,
            maxFragmentBytes: 40,
            maxToolResultBytes: 40,
            maxActiveObservations: 2,
            maxActiveHypotheses: 2,
            maxEstimatedTokens: 2048,
          },
        },
      ),
    ).rejects.toThrow(ContextBudgetExceededError);
  });

  test("a deny produces an explicit ToolRejected citing the extension and never executes", async () => {
    const host = createExtensionHost();
    const log: string[] = [];
    host.register({
      ...observingExtension(log),
      beforeTool: (context) => {
        log.push(`beforeTool:${context.name}`);
        if (context.name === "read_file") {
          return { decision: "deny", reason: "reads are paused for this session" };
        }
        return undefined;
      },
    });
    const provider = new ScriptedModelProvider(TOOL_CALL, FINAL_LINE);
    const deps = loopDeps(provider, host);
    await seedSession(deps);

    const outcome = await runTurn(deps, { input: "read the note" }, SIGNAL);
    expect(outcome).toEqual({ kind: "completed", finalText: "All done." });

    const events = await deps.store.readStream(SESSION_ID);
    const rejected = events.find((event) => event.type === "ToolRejected");
    expect(rejected?.type).toBe("ToolRejected");
    if (rejected?.type === "ToolRejected") {
      expect(rejected.payload.reason).toBe(
        "extension observer denied: reads are paused for this session",
      );
    }
    // Denied before ToolAuthorized: the call never started.
    const types = events.map((event) => event.type);
    expect(types).toContain("ToolProposed");
    expect(types).not.toContain("ToolStarted");
    expect(types).not.toContain("ToolSucceeded");
    expect(log).toContain("afterTool:REJECTED");
  });

  test("unload mid-session makes behavior indistinguishable from never-registered", async () => {
    const host = createExtensionHost();
    const log: string[] = [];
    host.register(observingExtension(log));

    const provider = new ScriptedModelProvider(TOOL_CALL, FINAL_LINE);
    const deps = loopDeps(provider, host);
    await seedSession(deps);

    // Drop the extension before the turn starts: no hook may fire.
    expect(host.unload("observer")).toBe(true);
    const outcome = await runTurn(deps, { input: "read the note" }, SIGNAL);
    expect(outcome.kind).toBe("completed");
    expect(log).toEqual([]);
    const events = await deps.store.readStream(SESSION_ID);
    expect(events.map((event) => event.type)).not.toContain("ToolRejected");
  });
});
