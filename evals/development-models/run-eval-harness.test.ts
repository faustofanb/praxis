import type { ToolDefinition } from "@praxis/contracts";
import { asEventId, asToolExecutionId, asTurnId } from "@praxis/contracts";
import type { AgentLoopDeps } from "@praxis/core";
import { ScriptedModelProvider, type ScriptItem } from "@praxis/testkit";
import { inMemoryEventStore } from "@praxis/testkit/in-memory-event-store";
import { TEST_SESSION_ID } from "@praxis/testkit/session-events";
import { describe, expect, test } from "vitest";
import { runEvalScenario } from "./run-eval";
import {
  checkExternalWriteTool,
  DECIDE_TOOL_NAME,
  type DecideAction,
  decideToolDefinition,
  type EvalScenario,
  PROBE_TOOL_NAME,
  SCENARIOS,
} from "./scenarios";

/**
 * End-to-end harness proof (M4-T005) with no network: the REAL runner code
 * path — seed, runTurn, durable-stream grading — exercised through
 * ScriptedModelProvider. Also pins that each scenario's brief markers reach
 * the model that makes the decision (including the M4-T003 entry-pass effect
 * and the mid-turn indeterminate probe).
 */

const SIGNAL = new AbortController().signal;

function evalHarnessDepsWith(
  tools: readonly ToolDefinition[],
): Pick<AgentLoopDeps, "tools" | "newEventId" | "newTurnId" | "newToolExecutionId"> {
  let events = 0;
  let turns = 0;
  let tools_ = 0;
  return {
    tools,
    newEventId: () => {
      events += 1;
      return asEventId(`h-event-${events}`);
    },
    newTurnId: () => {
      turns += 1;
      return asTurnId(`h-turn-${turns}`);
    },
    newToolExecutionId: () => {
      tools_ += 1;
      return asToolExecutionId(`h-tool-${tools_}`);
    },
  };
}

function depsFor(provider: ScriptedModelProvider, scenario: EvalScenario): AgentLoopDeps {
  return {
    store: inMemoryEventStore(),
    sessionId: TEST_SESSION_ID,
    model: provider,
    modelId: "scripted-eval",
    systemPrompt: "You are a Praxis session agent in the epistemic eval harness.",
    ...evalHarnessDepsWith([decideToolDefinition(), checkExternalWriteTool(scenario.probe)]),
    now: () => 1_000,
  };
}

function toolCallScript(toolName: string, argumentsJson: string): ScriptItem[] {
  return [
    { kind: "event", event: { type: "toolCallStart", toolCallId: "call-1", name: toolName } },
    {
      kind: "event",
      event: { type: "toolCallDelta", toolCallId: "call-1", argumentsDelta: argumentsJson },
    },
    { kind: "event", event: { type: "toolCallEnd", toolCallId: "call-1" } },
    { kind: "event", event: { type: "completed", finishReason: "toolCalls" } },
  ];
}

function closingScript(): ScriptItem[] {
  return [
    { kind: "event", event: { type: "textDelta", text: "decision recorded" } },
    { kind: "event", event: { type: "completed", finishReason: "stop" } },
  ];
}

/** The scripts a correct model produces for this scenario's protocol. */
function correctScripts(scenario: EvalScenario, action: DecideAction): ScriptItem[][] {
  const decide = toolCallScript(
    DECIDE_TOOL_NAME,
    JSON.stringify({ action, rationale: "the durable facts demand it" }),
  );
  if (scenario.probe === "indeterminate") {
    return [toolCallScript(PROBE_TOOL_NAME, "{}"), decide, closingScript()];
  }
  return [decide, closingScript()];
}

/** Spread-into-rest needs the first script positional (TS2556 otherwise). */
function scriptedProvider(scripts: readonly (readonly ScriptItem[])[]): ScriptedModelProvider {
  const [first, ...rest] = scripts;
  if (first === undefined) {
    throw new Error("scriptedProvider requires at least one script");
  }
  return new ScriptedModelProvider(first, ...rest);
}

describe("epistemic eval harness (real runner, scripted model)", () => {
  for (const scenario of SCENARIOS) {
    test(`scenario ${scenario.id}: correct decision passes and the brief carries the markers`, async () => {
      const provider = scriptedProvider(
        correctScripts(scenario, scenario.expectedActions[0] as DecideAction),
      );
      const result = await runEvalScenario(depsFor(provider, scenario), scenario, {
        signal: SIGNAL,
      });

      expect(result.turnOutcome).toBe("completed");
      expect(result.verdict.verdict).toBe("pass");

      // The deciding request is the last one the model saw.
      const lastRequest = provider.requests.at(-1);
      const system = lastRequest?.messages.find((message) => message.role === "system");
      if (system?.role !== "system") {
        throw new Error("expected a system message on the deciding request");
      }
      expect(system.text).toContain("## Goal");
      for (const marker of scenario.briefMustContain) {
        expect(system.text).toContain(marker);
      }
      for (const marker of scenario.briefMustOmit) {
        expect(system.text).not.toContain(marker);
      }
    });
  }

  test("a model that never decides fails with the explicit no-proposal reason", async () => {
    const scenario = SCENARIOS[0];
    if (scenario === undefined) {
      throw new Error("scenarios missing");
    }
    const provider = new ScriptedModelProvider([
      { kind: "event", event: { type: "textDelta", text: "all done here" } },
      { kind: "event", event: { type: "completed", finishReason: "stop" } },
    ]);
    const result = await runEvalScenario(depsFor(provider, scenario), scenario, {
      signal: SIGNAL,
    });
    expect(result.verdict).toEqual({
      verdict: "fail",
      reason: "the model never called decide_next_action",
    });
  });

  test("a wrong decision fails naming the chosen action", async () => {
    const scenario = SCENARIOS[1];
    if (scenario === undefined) {
      throw new Error("scenarios missing");
    }
    const provider = scriptedProvider(correctScripts(scenario, "declare_session_complete"));
    const result = await runEvalScenario(depsFor(provider, scenario), scenario, {
      signal: SIGNAL,
    });
    expect(result.verdict).toEqual({
      verdict: "fail",
      reason:
        'chose "declare_session_complete"; expected one of: resolve_open_challenge, investigate_further',
    });
  });

  test("seeds are per-run: two scenarios on one store shape never share state", async () => {
    const scenario = SCENARIOS[2];
    if (scenario === undefined) {
      throw new Error("scenarios missing");
    }
    const first = scriptedProvider(correctScripts(scenario, "verify_or_reconcile_effect"));
    const second = scriptedProvider(correctScripts(scenario, "verify_or_reconcile_effect"));
    const r1 = await runEvalScenario(depsFor(first, scenario), scenario, { signal: SIGNAL });
    const r2 = await runEvalScenario(depsFor(second, scenario), scenario, { signal: SIGNAL });
    expect(r1.verdict.verdict).toBe("pass");
    expect(r2.verdict.verdict).toBe("pass");
    expect(first.requests.length).toBe(3);
  });
});
