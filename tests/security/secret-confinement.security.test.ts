import type { EventStore, ModelProvider } from "@praxis/contracts";
import { asEventId, asSessionId, asToolExecutionId, asTurnId } from "@praxis/contracts";
import { type AgentLoopDeps, runTurn } from "@praxis/core";
import { type FetchLike, OpenAIChatProvider } from "@praxis/provider-openai";
import { describe, expect, test } from "vitest";
import { inMemoryEventStore } from "../helpers/in-memory-event-store";
import { sessionCreated } from "../helpers/session-events";

/**
 * Secret confinement (docs/02 §18: API key 不写入 config/event/model
 * context；telemetry 必须 redaction). The adapter holds the key in its
 * constructor and the Authorization header only; these tests pin that law
 * end to end — the key must be discoverable nowhere in the wire body, in
 * any durable event of a real turn, or in the model-facing messages,
 * while the control assertion proves the key is real and in flight.
 */

const encoder = new TextEncoder();

const API_KEY = "sk-security-confinement-key";

const SESSION_ID = asSessionId("session-secret-confinement");

type CapturedRequest = {
  readonly url: string;
  readonly authorization: string;
  readonly body: unknown;
};

/** Deep search over the whole serialized JSON graph. */
function graphContains(value: unknown, needle: string): boolean {
  return JSON.stringify(value).includes(needle);
}

function textChunk(content: string): unknown {
  return { choices: [{ index: 0, delta: { content }, finish_reason: null }] };
}

function finishChunk(reason: string): unknown {
  return { choices: [{ index: 0, delta: {}, finish_reason: reason }] };
}

function sseResponse(...payloads: unknown[]): Response {
  const text = payloads.map((payload) => `data: ${JSON.stringify(payload)}\n\n`).join("");
  return new Response(encoder.encode(`${text}data: [DONE]\n\n`), {
    status: 200,
    headers: { "content-type": "text/event-stream" },
  });
}

/** Real adapter against a captured fake endpoint; one clean turn's worth
 *  of scripted SSE per fetch call. */
function capturingFetch(captured: CapturedRequest[]): FetchLike {
  return (input, init) => {
    // The adapter always sends a plain header record; the cast is isolated
    // to this test-owned capture boundary.
    const headers = (init?.headers ?? {}) as Record<string, string>;
    captured.push({
      url: String(input),
      authorization: headers.authorization ?? "",
      body: JSON.parse(String(init?.body ?? "{}")),
    });
    return Promise.resolve(sseResponse(textChunk("done"), finishChunk("stop")));
  };
}

function turnDeps(store: EventStore, model: ModelProvider): AgentLoopDeps {
  let counter = 8000;
  let turns = 0;
  let executions = 0;
  return {
    store,
    sessionId: SESSION_ID,
    model,
    modelId: "openai-test",
    systemPrompt: "secret confinement harness",
    tools: [],
    now: () => {
      counter += 1;
      return counter;
    },
    newEventId: () => asEventId(`confinement-event-${counter}`),
    newTurnId: () => {
      turns += 1;
      return asTurnId(`confinement-turn-${turns}`);
    },
    newToolExecutionId: () => {
      executions += 1;
      return asToolExecutionId(`confinement-exec-${executions}`);
    },
  };
}

async function runProviderTurn(): Promise<{
  readonly captured: CapturedRequest[];
  readonly store: EventStore;
}> {
  const store = inMemoryEventStore();
  await store.append(
    [sessionCreated(1)].map((event) => ({ ...event, sessionId: SESSION_ID })),
    0,
  );
  const captured: CapturedRequest[] = [];
  const model = new OpenAIChatProvider({
    apiKey: API_KEY,
    fetchImpl: capturingFetch(captured),
  });
  const outcome = await runTurn(
    turnDeps(store, model),
    { input: "hi" },
    { signal: new AbortController().signal },
  );
  expect(outcome.kind).toBe("completed");
  expect(captured.length).toBe(1);
  return { captured, store };
}

describe("api key confinement (docs/02 §18)", () => {
  test("the key travels in the Authorization header and nowhere in the wire body", async () => {
    const { captured } = await runProviderTurn();
    const request = captured[0];
    if (request === undefined) {
      throw new Error("expected one captured request");
    }
    // Control: the key is real and in flight — otherwise the absence
    // assertions below would be vacuous.
    expect(request.authorization).toBe(`Bearer ${API_KEY}`);
    expect(graphContains(request.body, API_KEY)).toBe(false);
  });

  test("no durable event of a full real-adapter turn contains the key", async () => {
    const { store } = await runProviderTurn();
    const events = await store.readStream(SESSION_ID);
    expect(events.length).toBeGreaterThan(0);
    expect(graphContains(events, API_KEY)).toBe(false);
  });

  test("model-facing messages (the wire projection of model context) contain no key", async () => {
    const { captured } = await runProviderTurn();
    const request = captured[0];
    if (request === undefined) {
      throw new Error("expected one captured request");
    }
    const messages = (request.body as { messages?: unknown }).messages;
    if (!Array.isArray(messages)) {
      throw new Error("expected a messages array in the wire body");
    }
    expect(messages.length).toBeGreaterThan(0);
    expect(graphContains(messages, API_KEY)).toBe(false);
  });
});
