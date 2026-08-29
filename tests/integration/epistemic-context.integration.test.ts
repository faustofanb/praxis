import type { ToolDefinition } from "@praxis/contracts";
import { asEventId, asTurnId } from "@praxis/contracts";
import { type AgentLoopDeps, foldSessionEvents, reduceSession, runTurn } from "@praxis/core";
import { ScriptedModelProvider } from "@praxis/testkit";
import { describe, expect, test } from "vitest";
import { inMemoryEventStore } from "../helpers/in-memory-event-store";
import {
  challengeRaised,
  challengeResolved,
  goalSet,
  hypothesisProposed,
  hypothesisStatusChanged,
  observationRecorded,
  planSet,
  sessionCompleted,
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

  test("a falsified hypothesis invalidates its plan at turn entry, so the model sees no active plan", async () => {
    const provider = new ScriptedModelProvider([
      { kind: "event", event: { type: "textDelta", text: "replanning" } },
      { kind: "event", event: { type: "completed", finishReason: "stop" } },
    ]);
    const harness = deps(provider);
    await harness.store.append(
      [
        sessionCreated(1),
        goalSet(2, { goal: "restore the missing payment record" }),
        hypothesisProposed(3, 1),
        hypothesisStatusChanged(4, 1, "falsified", { evidence: [1] }),
        planSet(5, 1, { hypothesis: 1, nextAction: "replay the payment webhook" }),
      ],
      0,
    );

    const outcome = await runTurn(
      harness,
      { input: "proceed" },
      { signal: new AbortController().signal },
    );
    expect(outcome.kind).toBe("completed");

    // The turn-entry pass appended the invalidation as a durable fact.
    const stream = await harness.store.readStream(harness.sessionId);
    const invalidations = stream.filter((event) => event.type === "PlanInvalidated");
    expect(invalidations).toHaveLength(1);

    // The model was told the goal but not the dead plan.
    const system = provider.requests[0]?.messages.find((message) => message.role === "system");
    if (system?.role !== "system") {
      throw new Error("expected a system message");
    }
    expect(system.text).toContain("Goal: restore the missing payment record");
    expect(system.text).not.toContain("## Active plan");
    expect(system.text).not.toContain("replay the payment webhook");
  });

  test("a completion-target challenge changes the session path: completion is refused until resolved", async () => {
    const provider = new ScriptedModelProvider([
      { kind: "event", event: { type: "textDelta", text: "working under protest" } },
      { kind: "event", event: { type: "completed", finishReason: "stop" } },
    ]);
    const harness = deps(provider);
    await harness.store.append(
      [
        sessionCreated(1),
        goalSet(2, { goal: "restore the missing payment record" }),
        challengeRaised(3, 1, {
          targetType: "completion",
          claim: "the restoration was never verified",
        }),
      ],
      0,
    );

    const outcome = await runTurn(
      harness,
      { input: "proceed" },
      { signal: new AbortController().signal },
    );
    expect(outcome.kind).toBe("completed");

    // The model saw the block as a structured fragment.
    const system = provider.requests[0]?.messages.find((message) => message.role === "system");
    if (system?.role !== "system") {
      throw new Error("expected a system message");
    }
    expect(system.text).toContain("## Completion blocked");
    expect(system.text).toContain("Challenge: challenge-1 — the restoration was never verified");

    // Completion over the open challenge is refused by the reducer...
    const blockedState = foldSessionEvents(await harness.store.readStream(harness.sessionId));
    expect(() => reduceSession(blockedState, sessionCompleted(blockedState.headSeq + 1))).toThrow(
      /completion-target/,
    );

    // ...and the legal path: resolve the challenge, then complete.
    const resolution = challengeResolved(
      blockedState.headSeq + 1,
      1,
      "resolved",
      "verification recorded",
    );
    await harness.store.append([resolution], blockedState.headSeq);
    const stream = await harness.store.readStream(harness.sessionId);
    const beforeCompletion = foldSessionEvents(stream);
    expect(beforeCompletion.openChallenges).toHaveLength(0);
    const completed = reduceSession(beforeCompletion, sessionCompleted(stream.length + 1));
    expect(completed.status).toBe("COMPLETED");
  });
});
