import type {
  EventStore,
  ModelEvent,
  ModelProvider,
  ModelRequest,
  SessionEventUnion,
} from "@praxis/contracts";
import { asEventId, asSessionId, asToolExecutionId, asTurnId } from "@praxis/contracts";
import { type AgentLoopDeps, runTurn } from "@praxis/core";
import { type FetchLike, OpenAIChatProvider } from "@praxis/provider-openai";
import { describe, expect, test } from "vitest";
import { inMemoryEventStore } from "../helpers/in-memory-event-store";
import { sessionCreated } from "../helpers/session-events";

/**
 * Provider fault boundary (docs/02 §10, docs/subsystems/provider-openai.md):
 * the adapter owns provider retry, but a retryable failure may discard the
 * attempt ONLY while none of its events escaped to the consumer — once
 * anything is delivered, restarting would make the consumer assemble events
 * of two attempts into one logical response (doubled text, phantom tool
 * calls). These cases inject failures the unit suite does not: mid-body
 * resets AFTER delivered events, abort during the backoff sleep, and a
 * retryable→non-retryable downgrade across attempts.
 */

const encoder = new TextEncoder();

const REQUEST: ModelRequest = {
  model: "test-model",
  messages: [
    { role: "system", text: "sys" },
    { role: "user", text: "hi" },
  ],
  correlationId: "corr-fault",
};

const API_KEY = "sk-fault-suite-key";

function textChunk(content: string): unknown {
  return { choices: [{ index: 0, delta: { content }, finish_reason: null }] };
}

function toolCallFragment(index: number, id: string, name: string, args: string): unknown {
  return {
    choices: [
      {
        index: 0,
        delta: {
          tool_calls: [{ index, id, function: { name, arguments: args } }],
        },
        finish_reason: null,
      },
    ],
  };
}

function errorResponse(status: number, message: string): Response {
  return new Response(JSON.stringify({ error: { message } }), {
    status,
    headers: { "content-type": "application/json" },
  });
}

/**
 * A body that DELIVERS the given SSE frames on successive reads and then
 * resets the connection — the honest shape of a mid-stream network failure
 * (bytes arrive, are consumed, then the read errors), unlike a stream that
 * errors in start() and silently drops its queued frames.
 */
function resettingAfter(...frames: string[]): Response {
  let reads = 0;
  return new Response(
    new ReadableStream<Uint8Array>({
      pull(controller) {
        if (reads < frames.length) {
          controller.enqueue(encoder.encode(frames[reads]));
          reads += 1;
          return;
        }
        controller.error(new TypeError("connection reset mid-body"));
      },
    }),
    { status: 200, headers: { "content-type": "text/event-stream" } },
  );
}

async function collect(provider: ModelProvider, signal: AbortSignal): Promise<ModelEvent[]> {
  const events: ModelEvent[] = [];
  for await (const event of provider.complete(REQUEST, signal)) {
    events.push(event);
  }
  return events;
}

function countedFetch(steps: () => Response): {
  readonly fetchImpl: FetchLike;
  readonly calls: () => number;
} {
  let calls = 0;
  return {
    fetchImpl: () => {
      calls += 1;
      return Promise.resolve(steps());
    },
    calls: () => calls,
  };
}

describe("provider adapter fault boundary", () => {
  test("a mid-body reset after delivered text deltas is surfaced, never retried", async () => {
    const { fetchImpl, calls } = countedFetch(() =>
      resettingAfter(
        `data: ${JSON.stringify(textChunk("hel"))}\n\n`,
        `data: ${JSON.stringify(textChunk("lo"))}\n\n`,
      ),
    );
    const provider = new OpenAIChatProvider({
      apiKey: API_KEY,
      fetchImpl,
      maxRetries: 2,
      sleep: () => Promise.resolve(),
    });

    const events = await collect(provider, new AbortController().signal);

    expect(events).toEqual([
      { type: "textDelta", text: "hel" },
      { type: "textDelta", text: "lo" },
      {
        type: "providerError",
        error: {
          kind: "network",
          retryable: true,
          message: "connection reset mid-body",
        },
      },
    ]);
    expect(calls()).toBe(1);
  });

  test("a mid-body reset after a half-built tool call never completes the call", async () => {
    const { fetchImpl, calls } = countedFetch(() =>
      resettingAfter(
        `data: ${JSON.stringify(toolCallFragment(0, "call_1", "write_file", '{"path":"a'))}\n\n`,
      ),
    );
    const provider = new OpenAIChatProvider({
      apiKey: API_KEY,
      fetchImpl,
      maxRetries: 2,
      sleep: () => Promise.resolve(),
    });

    const events = await collect(provider, new AbortController().signal);

    expect(events).toEqual([
      { type: "toolCallStart", toolCallId: "call_1", name: "write_file" },
      { type: "toolCallDelta", toolCallId: "call_1", argumentsDelta: '{"path":"a' },
      {
        type: "providerError",
        error: {
          kind: "network",
          retryable: true,
          message: "connection reset mid-body",
        },
      },
    ]);
    expect(calls()).toBe(1);
  });

  test("abort during the backoff sleep ends silently without a further attempt", async () => {
    const controller = new AbortController();
    const { fetchImpl, calls } = countedFetch(() => errorResponse(429, "slow down"));
    let sleepEntered: (() => void) | undefined;
    const entered = new Promise<void>((resolve) => {
      sleepEntered = resolve;
    });
    const provider = new OpenAIChatProvider({
      apiKey: API_KEY,
      fetchImpl,
      maxRetries: 2,
      sleep: () => {
        sleepEntered?.();
        return new Promise<void>((resolve) => {
          controller.signal.addEventListener("abort", () => resolve(), { once: true });
        });
      },
    });

    const events: ModelEvent[] = [];
    const consuming = (async () => {
      for await (const event of provider.complete(REQUEST, controller.signal)) {
        events.push(event);
      }
    })();
    await entered;
    controller.abort();
    await consuming;

    expect(events).toEqual([]);
    expect(calls()).toBe(1);
  });

  test("a retryable failure downgraded to non-retryable stops at the downgrade", async () => {
    const sleeps: number[] = [];
    let call = 0;
    const provider = new OpenAIChatProvider({
      apiKey: API_KEY,
      fetchImpl: () => {
        call += 1;
        return Promise.resolve(
          call === 1 ? errorResponse(429, "slow down") : errorResponse(401, "bad key"),
        );
      },
      maxRetries: 2,
      sleep: (ms: number) => {
        sleeps.push(ms);
        return Promise.resolve();
      },
    });

    const events = await collect(provider, new AbortController().signal);

    expect(events.length).toBe(1);
    const failure = events[0];
    if (failure?.type !== "providerError") {
      throw new Error("expected a providerError");
    }
    expect(failure.error.kind).toBe("auth");
    expect(failure.error.retryable).toBe(false);
    expect(call).toBe(2);
    expect(sleeps).toEqual([500]);
  });
});

// ——— end to end: the durable facts of a full turn ———

const SESSION_ID = asSessionId("session-provider-fault");

function turnDeps(store: EventStore, model: ModelProvider): AgentLoopDeps {
  let counter = 7000;
  let turns = 0;
  let executions = 0;
  return {
    store,
    sessionId: SESSION_ID,
    model,
    modelId: "openai-test",
    systemPrompt: "provider fault harness",
    tools: [],
    now: () => {
      counter += 1;
      return counter;
    },
    newEventId: () => asEventId(`provider-fault-event-${counter}`),
    newTurnId: () => {
      turns += 1;
      return asTurnId(`provider-fault-turn-${turns}`);
    },
    newToolExecutionId: () => {
      executions += 1;
      return asToolExecutionId(`provider-fault-exec-${executions}`);
    },
  };
}

describe("provider adapter faults inside a real turn", () => {
  test("mid-stream resets land honest failures, never a corrupted completion", async () => {
    const store = inMemoryEventStore();
    await store.append(
      [sessionCreated(1)].map((event) => ({ ...event, sessionId: SESSION_ID })),
      0,
    );
    let fetches = 0;
    const model = new OpenAIChatProvider({
      apiKey: API_KEY,
      fetchImpl: () => {
        fetches += 1;
        return Promise.resolve(resettingAfter(`data: ${JSON.stringify(textChunk("partial"))}\n\n`));
      },
      maxRetries: 2,
      sleep: () => Promise.resolve(),
    });

    const outcome = await runTurn(
      turnDeps(store, model),
      { input: "hi" },
      { signal: new AbortController().signal },
    );

    // Every attempt fails the same way after one escaped delta, so the
    // adapter never restarts (1 fetch per core-level request) and core's
    // consecutive-failure guard pauses the turn.
    expect(outcome.kind).toBe("paused");
    expect(fetches).toBe(3);

    const events: readonly SessionEventUnion[] = await store.readStream(SESSION_ID);
    const failures = events.filter((event) => event.type === "ModelRequestFailed");
    expect(failures.length).toBe(3);
    for (const failure of failures) {
      if (failure.type !== "ModelRequestFailed") {
        continue;
      }
      expect(failure.payload.kind).toBe("network");
      expect(failure.payload.message).toBe("connection reset mid-body");
    }
    const completions = events.filter((event) => event.type === "ModelResponseCompleted");
    expect(completions).toEqual([]);
    // The escaped partial delta of any attempt never becomes a durable
    // fact: no event payload anywhere contains doubled or partial text.
    const serialized = JSON.stringify(events);
    expect(serialized.includes("partialpartial")).toBe(false);
    expect(serialized.includes("partial")).toBe(false);
  });
});
