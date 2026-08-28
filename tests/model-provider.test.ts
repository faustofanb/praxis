import type { ModelProvider, ModelRequest } from "@praxis/contracts";
import {
  ModelEventSchema,
  ModelMessageSchema,
  ModelProviderErrorInfoSchema,
  ModelRequestSchema,
} from "@praxis/contracts";
import { describe, expect, test } from "vitest";

function sampleRequest(): unknown {
  return {
    model: "scripted-1",
    messages: [
      { role: "system", text: "You are a test harness." },
      { role: "user", text: "summarize the fixture" },
      {
        role: "assistant",
        toolCalls: [
          {
            id: "call-1",
            name: "read_file",
            argumentsJson: '{"path":"fixture.txt"}',
          },
        ],
      },
      { role: "tool", toolCallId: "call-1", text: "fixture body" },
    ],
    tools: [
      {
        name: "read_file",
        description: "read a file",
        parametersJson: '{"type":"object"}',
      },
    ],
    maxOutputTokens: 512,
    providerOptions: { seed: 7 },
    correlationId: "corr-1",
  };
}

describe("ModelRequestSchema", () => {
  test("parses a full normalized request", () => {
    const parsed = ModelRequestSchema.parse(sampleRequest());
    expect(parsed.model).toBe("scripted-1");
    expect(parsed.messages).toHaveLength(4);
    expect(parsed.providerOptions).toEqual({ seed: 7 });
  });

  test("parses a minimal request without optional fields", () => {
    const parsed = ModelRequestSchema.parse({
      model: "scripted-1",
      messages: [{ role: "user", text: "hi" }],
    });
    expect(parsed.tools).toBeUndefined();
    expect(parsed.maxOutputTokens).toBeUndefined();
  });

  test("rejects an empty message list", () => {
    expect(() => ModelRequestSchema.parse({ model: "m", messages: [] })).toThrow();
  });

  test("rejects a request without a model id", () => {
    expect(() => ModelRequestSchema.parse({ messages: [{ role: "user", text: "hi" }] })).toThrow();
  });

  test("rejects an unknown message role", () => {
    expect(() => ModelMessageSchema.parse({ role: "developer", text: "hi" })).toThrow();
  });

  test("rejects a non-positive maxOutputTokens", () => {
    const request = sampleRequest() as { maxOutputTokens?: number };
    request.maxOutputTokens = 0;
    expect(() => ModelRequestSchema.parse(request)).toThrow();
  });
});

describe("ModelEventSchema", () => {
  test("parses each event type in the stream vocabulary", () => {
    const samples: unknown[] = [
      { type: "textDelta", text: "Hello" },
      { type: "toolCallStart", toolCallId: "call-1", name: "read_file" },
      { type: "toolCallDelta", toolCallId: "call-1", argumentsDelta: '{"pa' },
      { type: "toolCallEnd", toolCallId: "call-1" },
      { type: "usage", inputTokens: 10, outputTokens: 5 },
      { type: "completed", finishReason: "toolCalls" },
      {
        type: "providerError",
        error: { kind: "rateLimit", retryable: true, message: "slow down" },
      },
    ];
    for (const sample of samples) {
      expect(ModelEventSchema.parse(sample)).toBeTruthy();
    }
  });

  test("rejects an unknown event type", () => {
    expect(() => ModelEventSchema.parse({ type: "thinkingDelta", text: "hm" })).toThrow();
  });

  test("rejects a finishReason outside the enum", () => {
    expect(() =>
      ModelEventSchema.parse({ type: "completed", finishReason: "contentFilter" }),
    ).toThrow();
  });

  test("rejects negative token usage", () => {
    expect(() =>
      ModelEventSchema.parse({ type: "usage", inputTokens: -1, outputTokens: 0 }),
    ).toThrow();
  });
});

describe("ModelProviderErrorInfoSchema", () => {
  test("accepts every normalized error kind", () => {
    for (const kind of [
      "network",
      "rateLimit",
      "invalidRequest",
      "auth",
      "overloaded",
      "timeout",
      "unknown",
    ] as const) {
      expect(
        ModelProviderErrorInfoSchema.parse({
          kind,
          retryable: false,
          message: "x",
        }).kind,
      ).toBe(kind);
    }
  });

  test("rejects an ad-hoc error kind", () => {
    expect(() =>
      ModelProviderErrorInfoSchema.parse({
        kind: "serverOnFire",
        retryable: false,
        message: "x",
      }),
    ).toThrow();
  });
});

describe("ModelProvider port", () => {
  test("an object with the complete() signature satisfies the port", async () => {
    const provider: ModelProvider = {
      async *complete(request: ModelRequest, signal: AbortSignal) {
        if (signal.aborted) return;
        yield { type: "completed" as const, finishReason: "stop" as const };
        void request;
      },
    };
    const events = [];
    for await (const event of provider.complete(
      ModelRequestSchema.parse(sampleRequest()),
      new AbortController().signal,
    )) {
      events.push(event);
    }
    expect(events).toEqual([{ type: "completed", finishReason: "stop" }]);
  });
});
