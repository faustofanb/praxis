import type { ModelEvent, ModelProvider, ModelRequest } from "@praxis/contracts";
import { type FetchLike, OpenAIChatProvider } from "@praxis/provider-openai";
import { describe, expect, test } from "vitest";

/**
 * Deterministic adapter tests: fetch and sleep are injected, so nothing here
 * touches the network. Wire chunk shapes mirror the openai-node types the
 * adapter was verified against.
 */

type FetchCall = {
  readonly url: string;
  readonly authorization: string;
  readonly body: unknown;
  readonly signal: AbortSignal | undefined;
};

type FetchStep = Response | Error;

const encoder = new TextEncoder();

const REQUEST: ModelRequest = {
  model: "test-model",
  messages: [
    { role: "system", text: "sys" },
    { role: "user", text: "read the note" },
    {
      role: "assistant",
      toolCalls: [{ id: "call-1", name: "read_file", argumentsJson: '{"path":"note.txt"}' }],
    },
    { role: "tool", toolCallId: "call-1", text: "note body" },
  ],
  tools: [{ name: "read_file", description: "read a file", parametersJson: '{"type":"object"}' }],
  maxOutputTokens: 128,
  providerOptions: { temperature: 0 },
  correlationId: "corr-1",
};

function textChunk(content: string): unknown {
  return { choices: [{ index: 0, delta: { content }, finish_reason: null }] };
}

function toolCallFragment(
  index: number,
  fragment: { id?: string; name?: string; arguments?: string },
): unknown {
  const functionField: Record<string, string> = {};
  if (fragment.name !== undefined) functionField.name = fragment.name;
  if (fragment.arguments !== undefined) functionField.arguments = fragment.arguments;
  return {
    choices: [
      {
        index: 0,
        delta: {
          tool_calls: [
            {
              index,
              ...(fragment.id === undefined ? {} : { id: fragment.id }),
              function: functionField,
            },
          ],
        },
        finish_reason: null,
      },
    ],
  };
}

function finishChunk(reason: string | null): unknown {
  return { choices: [{ index: 0, delta: {}, finish_reason: reason }] };
}

function usageChunk(promptTokens: number, completionTokens: number): unknown {
  return {
    choices: [],
    usage: { prompt_tokens: promptTokens, completion_tokens: completionTokens },
  };
}

function sseBody(...payloads: unknown[]): ReadableStream<Uint8Array> {
  const text = payloads
    .map(
      (payload) => `data: ${typeof payload === "string" ? payload : JSON.stringify(payload)}\n\n`,
    )
    .join("");
  return new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(encoder.encode(text));
      controller.close();
    },
  });
}

function sseResponse(...payloads: unknown[]): Response {
  return new Response(sseBody(...payloads), {
    status: 200,
    headers: { "content-type": "text/event-stream" },
  });
}

function errorResponse(status: number, message: string): Response {
  return new Response(JSON.stringify({ error: { message } }), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function makeProvider(
  steps: FetchStep[],
  options: { sleeps?: number[]; maxRetries?: number } = {},
): { provider: ModelProvider; calls: FetchCall[] } {
  const calls: FetchCall[] = [];
  const fetchImpl: FetchLike = async (input, init) => {
    const headers = new Headers(init?.headers);
    calls.push({
      url: String(input),
      authorization: headers.get("authorization") ?? "",
      body: JSON.parse(String(init?.body ?? "null")),
      signal: init?.signal ?? undefined,
    });
    const step = steps.shift();
    if (step === undefined) {
      throw new Error("test fetch: unexpected extra call");
    }
    if (step instanceof Error) {
      throw step;
    }
    return step;
  };
  const provider = new OpenAIChatProvider({
    apiKey: "test-key",
    fetchImpl,
    sleep: (ms) => {
      options.sleeps?.push(ms);
      return Promise.resolve();
    },
    ...(options.maxRetries === undefined ? {} : { maxRetries: options.maxRetries }),
  });
  return { provider, calls };
}

async function collect(
  provider: ModelProvider,
  request: ModelRequest = REQUEST,
  signal: AbortSignal = new AbortController().signal,
): Promise<ModelEvent[]> {
  const events: ModelEvent[] = [];
  for await (const event of provider.complete(request, signal)) {
    events.push(event);
  }
  return events;
}

describe("OpenAIChatProvider request mapping", () => {
  test("maps the normalized request onto the chat completions wire body", async () => {
    const { provider, calls } = makeProvider([sseResponse(finishChunk("stop"))]);
    await collect(provider);

    expect(calls.length).toBe(1);
    const call = calls[0];
    if (call === undefined) {
      throw new Error("expected one fetch call");
    }
    expect(call.url).toBe("https://api.openai.com/v1/chat/completions");
    expect(call.authorization).toBe("Bearer test-key");
    expect(call.body).toEqual({
      model: "test-model",
      messages: [
        { role: "system", content: "sys" },
        { role: "user", content: "read the note" },
        {
          role: "assistant",
          tool_calls: [
            {
              id: "call-1",
              type: "function",
              function: { name: "read_file", arguments: '{"path":"note.txt"}' },
            },
          ],
        },
        { role: "tool", tool_call_id: "call-1", content: "note body" },
      ],
      tools: [
        {
          type: "function",
          function: {
            name: "read_file",
            description: "read a file",
            parameters: { type: "object" },
          },
        },
      ],
      max_completion_tokens: 128,
      temperature: 0,
      stream: true,
      stream_options: { include_usage: true },
    });
  });

  test("refuses an empty apiKey and a negative maxRetries", () => {
    expect(() => new OpenAIChatProvider({ apiKey: "  " })).toThrow("non-empty apiKey");
    expect(() => new OpenAIChatProvider({ apiKey: "k", maxRetries: -1 })).toThrow("maxRetries");
  });
});

describe("OpenAIChatProvider stream mapping", () => {
  test("maps text deltas, usage, and finish_reason=stop in order", async () => {
    const { provider } = makeProvider([
      sseResponse(
        textChunk("Hello"),
        textChunk(" world"),
        finishChunk("stop"),
        usageChunk(10, 5),
        "[DONE]",
      ),
    ]);
    const events = await collect(provider);
    expect(events).toEqual([
      { type: "textDelta", text: "Hello" },
      { type: "textDelta", text: " world" },
      { type: "usage", inputTokens: 10, outputTokens: 5 },
      { type: "completed", finishReason: "stop" },
    ]);
  });

  test("maps streamed tool-call fragments to start/delta/end plus completed(toolCalls)", async () => {
    const { provider } = makeProvider([
      sseResponse(
        toolCallFragment(0, { id: "call-1", name: "read_file", arguments: "" }),
        toolCallFragment(0, { arguments: '{"pa' }),
        toolCallFragment(0, { arguments: 'th":"note.txt"}' }),
        finishChunk("tool_calls"),
        "[DONE]",
      ),
    ]);
    const events = await collect(provider);
    expect(events).toEqual([
      { type: "toolCallStart", toolCallId: "call-1", name: "read_file" },
      { type: "toolCallDelta", toolCallId: "call-1", argumentsDelta: '{"pa' },
      { type: "toolCallDelta", toolCallId: "call-1", argumentsDelta: 'th":"note.txt"}' },
      { type: "toolCallEnd", toolCallId: "call-1" },
      { type: "completed", finishReason: "toolCalls" },
    ]);
  });

  test("keeps two parallel tool calls apart by wire index", async () => {
    const { provider } = makeProvider([
      sseResponse(
        toolCallFragment(0, { id: "call-1", name: "read_file", arguments: '{"path":"a"}' }),
        toolCallFragment(1, { id: "call-2", name: "list_dir", arguments: '{"path":"."}' }),
        finishChunk("tool_calls"),
        "[DONE]",
      ),
    ]);
    const events = await collect(provider);
    expect(events).toEqual([
      { type: "toolCallStart", toolCallId: "call-1", name: "read_file" },
      { type: "toolCallDelta", toolCallId: "call-1", argumentsDelta: '{"path":"a"}' },
      { type: "toolCallStart", toolCallId: "call-2", name: "list_dir" },
      { type: "toolCallDelta", toolCallId: "call-2", argumentsDelta: '{"path":"."}' },
      { type: "toolCallEnd", toolCallId: "call-1" },
      { type: "toolCallEnd", toolCallId: "call-2" },
      { type: "completed", finishReason: "toolCalls" },
    ]);
  });

  test("maps finish_reason=length", async () => {
    const { provider } = makeProvider([sseResponse(finishChunk("length"), "[DONE]")]);
    const events = await collect(provider);
    expect(events).toEqual([{ type: "completed", finishReason: "length" }]);
  });

  test("surfaces finish_reason values outside the v1 set as providerError, never coerced", async () => {
    const { provider, calls } = makeProvider(
      [sseResponse(finishChunk("content_filter"), "[DONE]")],
      {
        maxRetries: 2,
      },
    );
    const events = await collect(provider);
    expect(events.length).toBe(1);
    const failure = events[0];
    if (failure?.type !== "providerError") {
      throw new Error("expected a providerError");
    }
    expect(failure.error.kind).toBe("unknown");
    expect(failure.error.retryable).toBe(false);
    expect(failure.error.message).toContain("content_filter");
    expect(calls.length).toBe(1);
  });

  test("reports a tool-call fragment without id and name as malformed", async () => {
    const { provider } = makeProvider([
      sseResponse(
        toolCallFragment(0, { arguments: '{"x":1}' }),
        finishChunk("tool_calls"),
        "[DONE]",
      ),
    ]);
    const events = await collect(provider);
    expect(events.length).toBe(1);
    const failure = events[0];
    if (failure?.type !== "providerError") {
      throw new Error("expected a providerError");
    }
    expect(failure.error.kind).toBe("unknown");
    expect(failure.error.message).toContain("without id and name");
  });

  test("reports non-JSON data lines and a missing finish_reason as malformed", async () => {
    const malformed = await collect(makeProvider([sseResponse("{not-json")]).provider);
    expect(malformed.length).toBe(1);
    const malformedFailure = malformed[0];
    if (malformedFailure?.type !== "providerError") {
      throw new Error("expected a providerError");
    }
    expect(malformedFailure.error.message).toContain("malformed model output");

    const unfinished = await collect(makeProvider([sseResponse(textChunk("hi"))]).provider);
    expect(unfinished.length).toBe(2);
    expect(unfinished[0]).toEqual({ type: "textDelta", text: "hi" });
    const unfinishedFailure = unfinished[1];
    if (unfinishedFailure?.type !== "providerError") {
      throw new Error("expected a providerError");
    }
    expect(unfinishedFailure.error.message).toContain("without finish_reason");
  });
});

describe("OpenAIChatProvider failure classification and retry", () => {
  test("HTTP 401 maps to auth, non-retryable, one attempt", async () => {
    const { provider, calls } = makeProvider([errorResponse(401, "bad key")], { maxRetries: 2 });
    const events = await collect(provider);
    expect(events.length).toBe(1);
    const failure = events[0];
    if (failure?.type !== "providerError") {
      throw new Error("expected a providerError");
    }
    expect(failure.error.kind).toBe("auth");
    expect(failure.error.retryable).toBe(false);
    expect(failure.error.message).toContain("HTTP 401");
    expect(failure.error.message).toContain("bad key");
    expect(calls.length).toBe(1);
  });

  test("HTTP 429 is retried once by the adapter, then completes", async () => {
    const sleeps: number[] = [];
    const { provider, calls } = makeProvider(
      [errorResponse(429, "slow down"), sseResponse(finishChunk("stop"), "[DONE]")],
      { sleeps },
    );
    const events = await collect(provider);
    expect(events).toEqual([{ type: "completed", finishReason: "stop" }]);
    expect(calls.length).toBe(2);
    expect(sleeps).toEqual([500]);
  });

  test("HTTP 500 exhausts retries with exponential backoff, then providerError overloaded", async () => {
    const sleeps: number[] = [];
    const { provider, calls } = makeProvider(
      [errorResponse(500, "boom"), errorResponse(500, "boom"), errorResponse(500, "boom")],
      { sleeps },
    );
    const events = await collect(provider);
    expect(events.length).toBe(1);
    const failure = events[0];
    if (failure?.type !== "providerError") {
      throw new Error("expected a providerError");
    }
    expect(failure.error.kind).toBe("overloaded");
    expect(failure.error.retryable).toBe(true);
    expect(calls.length).toBe(3);
    expect(sleeps).toEqual([500, 1000]);
  });

  test("a network throw is retryable and the retry can succeed", async () => {
    const sleeps: number[] = [];
    const { provider } = makeProvider(
      [new TypeError("fetch failed"), sseResponse(textChunk("ok"), finishChunk("stop"), "[DONE]")],
      { sleeps },
    );
    const events = await collect(provider);
    expect(events).toEqual([
      { type: "textDelta", text: "ok" },
      { type: "completed", finishReason: "stop" },
    ]);
    expect(sleeps).toEqual([500]);
  });

  test("a read timeout maps to providerError timeout, retryable", async () => {
    const hangingFetch: FetchLike = (_input, init) =>
      new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => {
          reject(new DOMException("aborted", "AbortError"));
        });
      });
    const provider = new OpenAIChatProvider({
      apiKey: "test-key",
      fetchImpl: hangingFetch,
      timeoutMs: 20,
      maxRetries: 0,
      sleep: () => Promise.resolve(),
    });
    const events = await collect(provider);
    expect(events.length).toBe(1);
    const failure = events[0];
    if (failure?.type !== "providerError") {
      throw new Error("expected a providerError");
    }
    expect(failure.error.kind).toBe("timeout");
    expect(failure.error.retryable).toBe(true);
  });
});

describe("OpenAIChatProvider cancellation", () => {
  test("an already-aborted signal ends the stream silently without retrying", async () => {
    const { provider, calls } = makeProvider([new DOMException("aborted", "AbortError")], {
      maxRetries: 2,
    });
    const controller = new AbortController();
    controller.abort();
    const events = await collect(provider, REQUEST, controller.signal);
    expect(events).toEqual([]);
    expect(calls.length).toBe(1);
  });

  test("aborting mid-stream ends silently: no events after, no throw, no providerError", async () => {
    const controller = new AbortController();
    const fetchImpl: FetchLike = (_input, init) =>
      Promise.resolve(
        new Response(
          new ReadableStream<Uint8Array>({
            start(streamController) {
              streamController.enqueue(
                encoder.encode(`data: ${JSON.stringify(textChunk("hel"))}\n\n`),
              );
              init?.signal?.addEventListener("abort", () => {
                streamController.error(new DOMException("aborted", "AbortError"));
              });
            },
          }),
          { status: 200, headers: { "content-type": "text/event-stream" } },
        ),
      );
    const provider = new OpenAIChatProvider({
      apiKey: "test-key",
      fetchImpl,
      sleep: () => Promise.resolve(),
    });

    const iterator = provider.complete(REQUEST, controller.signal);
    const first = await iterator.next();
    expect(first.done).toBe(false);
    expect(first.value).toEqual({ type: "textDelta", text: "hel" });

    setTimeout(() => controller.abort(), 5);
    const second = await iterator.next();
    expect(second.done).toBe(true);
  });
});
