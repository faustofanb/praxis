import type { ToolDefinition } from "@praxis/contracts";
import { asEventId, asTurnId } from "@praxis/contracts";
import { type AgentLoopDeps, runTurn } from "@praxis/core";
import { ScriptedModelProvider } from "@praxis/testkit";
import { describe, expect, test } from "vitest";
import { inMemoryEventStore } from "../helpers/in-memory-event-store";
import {
  goalSet,
  observationRecorded,
  planSet,
  sessionCreated,
  TEST_SESSION_ID,
} from "../helpers/session-events";

/**
 * Epistemic projection end to end (docs/02 section 12, M4.2): facts appended
 * before and during a turn ride as structured fragments of the system message
 * on every model request, re-folded fresh each step. The ScriptedModelProvider
 * records each request, so the assertions run against what the model would
 * actually see.
 */

const SESSION_ID = TEST_SESSION_ID;

function deps(model: ScriptedModelProvider): AgentLoopDeps {
  return {
    store: inMemoryEventStore(),
    sessionId: SESSION_ID,
    model,
    modelId: "scripted-1",
    systemPrompt: "You are Praxis running a read-only session.",
    tools: [] as readonly ToolDefinition[],
    now: () => 1_000,
    newEventId: (() => {
      let n = 0;
      return () => {
        n += 1;
        return asEventId(`event-${n}`);
      };
    })(),
    newTurnId: () => asTurnId("turn-1"),
    newToolExecutionId: () => {
      throw new Error("no tool executions in this suite");
    },
  };
}

describe("runTurn epistemic context projection", () => {
  test("mid-session facts reach the model as structured system fragments", async () => {
    const provider = new ScriptedModelProvider(
      [
        { kind: "event", event: { type: "textDelta", text: "checking the ledger" } },
        { kind: "event", event: { type: "completed", finishReason: "stop" } },
      ],
      [
        { kind: "event", event: { type: "textDelta", text: "restored" } },
        { kind: "event", event: { type: "completed", finishReason: "stop" } },
      ],
    );
    const harness = deps(provider);
    await harness.store.append(
      [
        sessionCreated(1),
        goalSet(2, { goal: "restore the missing payment record" }),
        observationRecorded(3, 1, { claim: "payment pay_1 has no ledger entry" }),
        planSet(4, 1, { nextAction: "replay the payment webhook" }),
      ],
      0,
    );

    const outcome = await runTurn(
      harness,
      { input: "proceed" },
      { signal: new AbortController().signal },
    );
    expect(outcome.kind).toBe("completed");

    // First request of the turn: pre-turn facts are already in the brief.
    const firstSystem = provider.requests[0]?.messages.find((message) => message.role === "system");
    if (firstSystem?.role !== "system") {
      throw new Error("expected a system message in the first request");
    }
    expect(firstSystem.text).toContain("You are Praxis running a read-only session.\n\n## Goal");
    expect(firstSystem.text).toContain("Goal: restore the missing payment record");
    expect(firstSystem.text).toContain("Next action: replay the payment webhook");
    expect(firstSystem.text).toContain("- payment pay_1 has no ledger entry");
  });

  test("a session without epistemic facts builds the plain system prompt", async () => {
    const provider = new ScriptedModelProvider([
      { kind: "event", event: { type: "textDelta", text: "nothing epistemic here" } },
      { kind: "event", event: { type: "completed", finishReason: "stop" } },
    ]);
    const harness = deps(provider);
    await harness.store.append([sessionCreated(1)], 0);

    const outcome = await runTurn(
      harness,
      { input: "hello" },
      { signal: new AbortController().signal },
    );
    expect(outcome.kind).toBe("completed");

    const system = provider.requests[0]?.messages.find((message) => message.role === "system");
    if (system?.role !== "system") {
      throw new Error("expected a system message");
    }
    expect(system.text).toBe("You are Praxis running a read-only session.");
  });
});
