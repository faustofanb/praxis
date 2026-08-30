import type { ModelRequest, ToolDefinition } from "@praxis/contracts";
import { asEventId, asToolExecutionId, asTurnId } from "@praxis/contracts";
import type { AgentLoopDeps } from "@praxis/core";
import { runTurn } from "@praxis/core";
import { ScriptedModelProvider, type ScriptItem } from "@praxis/testkit";
import { inMemoryEventStore } from "@praxis/testkit/in-memory-event-store";
import { goalSet, sessionCreated, TEST_SESSION_ID } from "@praxis/testkit/session-events";
import { describe, expect, test } from "vitest";
import { z } from "zod";

/**
 * providerOptions passthrough (M7-T011): deps-level request personalization
 * must reach the provider's ModelRequest verbatim, and ABSENT means the
 * field stays absent — byte-identical request (zero-change identity).
 * Runtime rules never read it: the scripted turn completes identically in
 * both runs.
 */

const SIGNAL = new AbortController().signal;

const DECIDE_INPUT = z.object({ note: z.string() });

const DECIDE: ToolDefinition = {
  name: "decide_probe",
  description: "record a decision",
  effect: "read_only",
  inputSchema: DECIDE_INPUT,
  parametersJson: JSON.stringify({
    type: "object",
    additionalProperties: false,
    required: ["note"],
    properties: { note: { type: "string" } },
  }),
  async execute(_context, input) {
    const parsed = DECIDE_INPUT.parse(input);
    return { status: "succeeded", resultJson: JSON.stringify({ note: parsed.note }) };
  },
};

function scriptedDecide(): ScriptedModelProvider {
  // One script per model request: first the tool-call stream, then the
  // closing text stream after the probe executes.
  const toolCallStream: ScriptItem[] = [
    { kind: "event", event: { type: "toolCallStart", toolCallId: "call-1", name: "decide_probe" } },
    {
      kind: "event",
      event: { type: "toolCallDelta", toolCallId: "call-1", argumentsDelta: '{"note":"ok"}' },
    },
    { kind: "event", event: { type: "toolCallEnd", toolCallId: "call-1" } },
    { kind: "event", event: { type: "completed", finishReason: "toolCalls" } },
  ];
  const textStream: ScriptItem[] = [
    { kind: "event", event: { type: "textDelta", text: "done" } },
    { kind: "event", event: { type: "completed", finishReason: "stop" } },
  ];
  return new ScriptedModelProvider(toolCallStream, textStream);
}

function deps(
  provider: ScriptedModelProvider,
  providerOptions: Record<string, unknown> | undefined,
): AgentLoopDeps {
  let events = 0;
  let turns = 0;
  let tools = 0;
  return {
    store: inMemoryEventStore(),
    sessionId: TEST_SESSION_ID,
    model: provider,
    modelId: "integration-model",
    systemPrompt: "integration",
    tools: [DECIDE],
    ...(providerOptions === undefined ? {} : { providerOptions }),
    now: () => 1_000,
    newEventId: () => {
      events += 1;
      return asEventId(`po-event-${events}`);
    },
    newTurnId: () => {
      turns += 1;
      return asTurnId(`po-turn-${turns}`);
    },
    newToolExecutionId: () => {
      tools += 1;
      return asToolExecutionId(`po-tool-${tools}`);
    },
  };
}

async function seed(deps: AgentLoopDeps): Promise<void> {
  await deps.store.append(
    [sessionCreated(1), goalSet(2, { goal: "provider options passthrough" })],
    0,
  );
}

async function lastRequest(provider: ScriptedModelProvider): Promise<ModelRequest> {
  const request = provider.requests.at(-1);
  if (request === undefined) {
    throw new Error("the provider never saw a request");
  }
  return request;
}

describe("providerOptions passthrough (M7-T011)", () => {
  test("deps.providerOptions reaches the provider request verbatim", async () => {
    const provider = scriptedDecide();
    const wired = deps(provider, { reasoning_effort: "high", thinking: { type: "enabled" } });
    await seed(wired);
    const outcome = await runTurn(wired, { input: "decide" }, { signal: SIGNAL });

    expect(outcome.kind).toBe("completed");
    const request = await lastRequest(provider);
    expect(request.providerOptions).toEqual({
      reasoning_effort: "high",
      thinking: { type: "enabled" },
    });
  });

  test("absent providerOptions keeps the request field absent and behavior identical", async () => {
    const provider = scriptedDecide();
    const wired = deps(provider, undefined);
    await seed(wired);
    const outcome = await runTurn(wired, { input: "decide" }, { signal: SIGNAL });

    expect(outcome.kind).toBe("completed");
    const request = await lastRequest(provider);
    expect("providerOptions" in request).toBe(false);
  });
});
