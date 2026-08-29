import type { EventStore, PraxisExtension } from "@praxis/contracts";
import { asEventId, asSessionId, asToolExecutionId, asTurnId } from "@praxis/contracts";
import { type AgentLoopDeps, createExtensionHost, foldSessionEvents, runTurn } from "@praxis/core";
import { ScriptedModelProvider, type ScriptItem } from "@praxis/testkit";
import { describe, expect, test } from "vitest";
import { inMemoryEventStore } from "../helpers/in-memory-event-store";
import { sessionCreated } from "../helpers/session-events";

/**
 * Extension failure semantics (docs/02 sections 17 and 19, ADR-0013): a
 * fail_closed hook crash is an ordinary mid-turn crash — the persisted
 * prefix folds legally and the EXISTING recovery machinery resumes the
 * session with honest facts. No second failure path exists. An isolate
 * crash never surfaces at all.
 */

const SESSION_ID = asSessionId("session-ext-fault");
const SIGNAL = { signal: new AbortController().signal };
const TEXT = (text: string): ScriptItem => ({ kind: "event", event: { type: "textDelta", text } });
const FINAL_LINE: ScriptItem[] = [
  TEXT("Recovered."),
  { kind: "event", event: { type: "completed", finishReason: "stop" } },
];

function loopDeps(
  model: ScriptedModelProvider,
  extensions: AgentLoopDeps["extensions"],
  store: EventStore = inMemoryEventStore(),
): AgentLoopDeps {
  let counter = 7000;
  let turns = 0;
  let executions = 0;
  return {
    store,
    sessionId: SESSION_ID,
    model,
    modelId: "scripted-model",
    systemPrompt: "You are the extension fault harness.",
    tools: [],
    now: () => {
      counter += 1;
      return counter;
    },
    newEventId: () => asEventId(`ext-fault-${counter}`),
    newTurnId: () => {
      turns += 1;
      return asTurnId(`ext-fault-turn-${turns}`);
    },
    newToolExecutionId: () => {
      executions += 1;
      return asToolExecutionId(`ext-fault-exec-${executions}`);
    },
    ...(extensions === undefined ? {} : { extensions }),
  };
}

async function seed(deps: AgentLoopDeps): Promise<void> {
  await deps.store.append([{ ...sessionCreated(1), sessionId: SESSION_ID }], 0);
}

const CRASHING_BEFORE_MODEL: PraxisExtension = {
  name: "policy-guard",
  failurePolicy: "fail_closed",
  beforeModel: () => {
    throw new Error("policy precondition violated");
  },
};

describe("fail_closed extension crashes ride the existing recovery", () => {
  test("a crash in beforeModel leaves a legal prefix; resume closes it honestly", async () => {
    const host = createExtensionHost();
    host.register(CRASHING_BEFORE_MODEL);
    const deps = loopDeps(new ScriptedModelProvider(FINAL_LINE), host);
    await seed(deps);

    await expect(runTurn(deps, { input: "begin" }, SIGNAL)).rejects.toThrow(
      "extension 'policy-guard' hook beforeModel failed (fail_closed): policy precondition violated",
    );

    // The prefix folds legally: the turn is open with a dangling model request.
    const prefix = foldSessionEvents(await deps.store.readStream(SESSION_ID));
    expect(prefix.currentTurnId?.valueOf()).toBe("ext-fault-turn-1");
    expect(prefix.pendingModelRequest).toBeDefined();

    // A resumed process without the crashing extension recovers with the
    // standard honest fact, then finishes the turn.
    const resumed = loopDeps(new ScriptedModelProvider(FINAL_LINE), undefined, deps.store);
    const outcome = await runTurn(resumed, {}, SIGNAL);
    expect(outcome).toEqual({ kind: "completed", finalText: "Recovered." });

    const types = (await deps.store.readStream(SESSION_ID)).map((event) => event.type);
    expect(types).toEqual([
      "SessionCreated",
      "TurnStarted",
      "ModelRequestStarted",
      "ModelRequestFailed",
      "ModelRequestStarted",
      "ModelResponseCompleted",
      "TurnCompleted",
    ]);
  });

  test("a crash in onEvent propagates out of append; the append itself persisted", async () => {
    const host = createExtensionHost();
    host.register({
      name: "strict-observer",
      failurePolicy: "fail_closed",
      onEvent: (context) => {
        if (context.event.type === "ModelRequestStarted") {
          throw new Error("observer lost its sink");
        }
      },
    });
    const deps = loopDeps(new ScriptedModelProvider(FINAL_LINE), host);
    await seed(deps);

    await expect(runTurn(deps, { input: "begin" }, SIGNAL)).rejects.toThrow(
      "extension 'strict-observer' hook onEvent failed (fail_closed): observer lost its sink",
    );

    // TurnStarted and ModelRequestStarted both persisted (observation fires
    // after durability); the fold stays legal.
    const events = await deps.store.readStream(SESSION_ID);
    expect(events.map((event) => event.type)).toEqual([
      "SessionCreated",
      "TurnStarted",
      "ModelRequestStarted",
    ]);
    expect(() => foldSessionEvents(events)).not.toThrow();

    const resumed = loopDeps(new ScriptedModelProvider(FINAL_LINE), undefined, deps.store);
    const outcome = await runTurn(resumed, {}, SIGNAL);
    expect(outcome).toEqual({ kind: "completed", finalText: "Recovered." });
  });

  test("the same crash under 'isolate' never surfaces: the turn completes", async () => {
    const host = createExtensionHost();
    host.register({
      name: "flaky-telemetry",
      beforeModel: () => {
        throw new Error("sink down");
      },
      onEvent: () => {
        throw new Error("sink down");
      },
    });
    const deps = loopDeps(new ScriptedModelProvider(FINAL_LINE), host);
    await seed(deps);

    const outcome = await runTurn(deps, { input: "begin" }, SIGNAL);
    expect(outcome).toEqual({ kind: "completed", finalText: "Recovered." });
    const types = (await deps.store.readStream(SESSION_ID)).map((event) => event.type);
    expect(types).not.toContain("ModelRequestFailed");
  });
});
