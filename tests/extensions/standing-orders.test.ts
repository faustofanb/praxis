import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { SessionEventUnion } from "@praxis/contracts";
import {
  asEventId,
  asSessionId,
  asToolExecutionId,
  asTurnId,
  validatePraxisExtension,
} from "@praxis/contracts";
import { type AgentLoopDeps, createExtensionHost, runTurn } from "@praxis/core";
import {
  createStandingOrdersExtension,
  STANDING_ORDERS_EXTENSION_NAME,
} from "@praxis/extension-standing-orders";
import { createTelemetryObserver } from "@praxis/extension-telemetry";
import { ScriptedModelProvider, type ScriptItem } from "@praxis/testkit";
import { localReadTools } from "@praxis/tools-local";
import { afterEach, beforeEach, describe, expect, test } from "vitest";
import { inMemoryEventStore } from "../helpers/in-memory-event-store";
import { sessionCreated } from "../helpers/session-events";

/**
 * The standing-orders extension is the shipped POLICY consumer of the
 * ADR-0013 seams (M6-T003): fail_closed per docs/02 section 19, contributing
 * operator instructions as a capped context fragment and denying configured
 * tools through the deny-only lifecycle seam — with zero edits under
 * packages/core or packages/contracts (the M6 'without core edit' scenario,
 * context + tool halves).
 */

const SESSION_ID = asSessionId("session-standing-orders");

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
  root = await mkdtemp(join(tmpdir(), "praxis-standing-orders-"));
  await writeFile(join(root, "note.txt"), "standing orders integration note");
});
afterEach(async () => {
  await rm(root, { recursive: true, force: true });
});

function loopDeps(
  model: ScriptedModelProvider,
  extensions: AgentLoopDeps["extensions"],
): AgentLoopDeps {
  let counter = 7000;
  let turns = 0;
  let executions = 0;
  return {
    store: inMemoryEventStore(),
    sessionId: SESSION_ID,
    model,
    modelId: "scripted-model",
    systemPrompt: "You are the standing orders harness.",
    tools: localReadTools(root),
    now: () => {
      counter += 1;
      return counter;
    },
    newEventId: () => asEventId(`so-${counter}`),
    newTurnId: () => {
      turns += 1;
      return asTurnId(`so-turn-${turns}`);
    },
    newToolExecutionId: () => {
      executions += 1;
      return asToolExecutionId(`so-exec-${executions}`);
    },
    ...(extensions === undefined ? {} : { extensions }),
  };
}

async function seedSession(deps: AgentLoopDeps): Promise<void> {
  await deps.store.append([{ ...sessionCreated(1), sessionId: SESSION_ID }], 0);
}

function fingerprint(events: readonly SessionEventUnion[]): string {
  return JSON.stringify(events.map((event) => [event.seq, event.type, event.payload]));
}

describe("standing orders extension over the real extension host", () => {
  test("declares fail_closed, passes structural validation, and renders instructions after the prompt", async () => {
    const extension = createStandingOrdersExtension({
      instructions: "Always cite the file you read.",
    });
    expect(extension.name).toBe(STANDING_ORDERS_EXTENSION_NAME);
    expect(extension.failurePolicy).toBe("fail_closed");
    expect(() => validatePraxisExtension(extension)).not.toThrow();

    const host = createExtensionHost();
    host.register(extension);
    const provider = new ScriptedModelProvider(FINAL_LINE);
    const deps = loopDeps(provider, host);
    await seedSession(deps);
    const outcome = await runTurn(deps, { input: "summarize" }, SIGNAL);
    expect(outcome.kind).toBe("completed");

    const system = provider.requests[0]?.messages[0];
    expect(system?.role).toBe("system");
    const systemText = system?.text ?? "";
    expect(systemText).toContain("## Extension: standing-orders");
    expect(systemText).toContain("Always cite the file you read.");
    expect(systemText.indexOf("## Extension: standing-orders")).toBeGreaterThan(
      systemText.indexOf("standing orders harness"),
    );
  });

  test("zero-config identity: a registered-but-unconfigured extension is byte-inert", async () => {
    const bareProvider = new ScriptedModelProvider(TOOL_CALL, FINAL_LINE);
    const bare = loopDeps(bareProvider, undefined);
    await seedSession(bare);
    const bareOutcome = await runTurn(bare, { input: "read the note" }, SIGNAL);
    const bareEvents = await bare.store.readStream(SESSION_ID);

    const host = createExtensionHost();
    host.register(createStandingOrdersExtension());
    const wiredProvider = new ScriptedModelProvider(TOOL_CALL, FINAL_LINE);
    const wired = loopDeps(wiredProvider, host);
    await seedSession(wired);
    const wiredOutcome = await runTurn(wired, { input: "read the note" }, SIGNAL);
    const wiredEvents = await wired.store.readStream(SESSION_ID);

    expect(wiredOutcome).toEqual(bareOutcome);
    expect(fingerprint(wiredEvents)).toBe(fingerprint(bareEvents));
    expect(JSON.stringify(wiredProvider.requests[0])).toBe(
      JSON.stringify(bareProvider.requests[0]),
    );
  });

  test("a denied tool produces ToolRejected citing standing orders and never executes", async () => {
    const host = createExtensionHost();
    host.register(
      createStandingOrdersExtension({
        deniedTools: ["read_file"],
      }),
    );
    const provider = new ScriptedModelProvider(TOOL_CALL, FINAL_LINE);
    const deps = loopDeps(provider, host);
    await seedSession(deps);
    const outcome = await runTurn(deps, { input: "read the note" }, SIGNAL);
    expect(outcome.kind).toBe("completed");

    const events = await deps.store.readStream(SESSION_ID);
    const types = events.map((event) => event.type);
    expect(types).toContain("ToolProposed");
    expect(types).not.toContain("ToolStarted");
    expect(types).not.toContain("ToolSucceeded");
    const rejected = events.find((event) => event.type === "ToolRejected");
    if (rejected?.type === "ToolRejected") {
      expect(rejected.payload.reason).toBe(
        "extension standing-orders denied: standing orders forbid tool 'read_file'",
      );
    }
  });

  test("composes with the telemetry observer in one host: the deny is counted REJECTED", async () => {
    const observer = createTelemetryObserver();
    const host = createExtensionHost();
    host.register(observer.extension);
    host.register(
      createStandingOrdersExtension({
        deniedTools: ["read_file"],
      }),
    );

    const provider = new ScriptedModelProvider(TOOL_CALL, FINAL_LINE);
    const deps = loopDeps(provider, host);
    await seedSession(deps);
    const outcome = await runTurn(deps, { input: "read the note" }, SIGNAL);
    expect(outcome.kind).toBe("completed");

    expect(observer.snapshot().tools).toEqual({
      read_file: { REJECTED: 1, SUCCEEDED: 0, FAILED: 0, INDETERMINATE: 0 },
    });
    expect(observer.snapshot().turns.byOutcome).toEqual({
      completed: 1,
      paused: 0,
      cancelled: 0,
    });
  });

  test("construction is loud about configuration bugs", () => {
    expect(() => createStandingOrdersExtension({ instructions: "   " })).toThrow(
      /instructions must be a non-empty string/,
    );
    expect(() => createStandingOrdersExtension({ deniedTools: ["read_file", "  "] })).toThrow(
      /deniedTools entries must be non-empty strings/,
    );
    expect(() =>
      createStandingOrdersExtension({ deniedTools: ["read_file"] as readonly string[] }),
    ).not.toThrow();
  });

  test("policy inputs are frozen against later caller mutation", () => {
    const deniedTools = ["read_file"];
    const extension = createStandingOrdersExtension({ deniedTools });
    deniedTools.push("write_file");

    const toolContext = (name: string) => ({
      sessionId: SESSION_ID,
      turnId: asTurnId("so-turn-1"),
      name,
      effect: "read_only" as const,
      argumentsJson: "{}",
    });
    // The frozen copy: the pushed name is not enforced...
    expect(extension.beforeTool?.(toolContext("write_file"))).toBeUndefined();
    // ...while the configured name still denies.
    expect(extension.beforeTool?.(toolContext("read_file"))).toEqual({
      decision: "deny",
      reason: "standing orders forbid tool 'read_file'",
    });
  });

  test("unload stops both contributions on the next turn", async () => {
    const host = createExtensionHost();
    host.register(
      createStandingOrdersExtension({
        instructions: "Always cite the file you read.",
        deniedTools: ["read_file"],
      }),
    );
    // Turn 1 (tool script + first final line) runs WITH the orders.
    const provider = new ScriptedModelProvider(TOOL_CALL, FINAL_LINE, FINAL_LINE);
    const deps = loopDeps(provider, host);
    await seedSession(deps);
    const first = await runTurn(deps, { input: "read the note" }, SIGNAL);
    expect(first.kind).toBe("completed");

    expect(host.unload(STANDING_ORDERS_EXTENSION_NAME)).toBe(true);

    // Turn 2 (second final line) runs WITHOUT: no section, and the would-be
    // denied tool script is not consumed — this turn proposes no tool call.
    const second = await runTurn(deps, { input: "summarize" }, SIGNAL);
    expect(second.kind).toBe("completed");
    const events = await deps.store.readStream(SESSION_ID);
    expect(events.filter((event) => event.type === "ToolRejected")).toHaveLength(1);

    const firstSystem = provider.requests[0]?.messages[0]?.text ?? "";
    const lastSystem = provider.requests.at(-1)?.messages[0]?.text ?? "";
    expect(firstSystem).toContain("## Extension: standing-orders");
    expect(lastSystem).not.toContain("## Extension: standing-orders");
  });
});
