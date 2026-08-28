import type { ModelEvent, ModelRequest } from "@praxis/contracts";
import { ModelEventSchema, ModelRequestSchema } from "@praxis/contracts";
import type { ScriptItem } from "@praxis/testkit";
import { ScriptedModelProvider } from "@praxis/testkit";
import { describe, expect, test } from "vitest";

function request(model: string): ModelRequest {
  return ModelRequestSchema.parse({
    model,
    messages: [{ role: "user", text: "hi" }],
  });
}

const TEXT: ScriptItem = { kind: "event", event: { type: "textDelta", text: "Hello" } };
const COMPLETED: ScriptItem = {
  kind: "event",
  event: { type: "completed", finishReason: "stop" },
};
const PROVIDER_ERROR: ScriptItem = {
  kind: "event",
  event: {
    type: "providerError",
    error: { kind: "rateLimit", retryable: true, message: "slow down" },
  },
};

async function collect(
  provider: ScriptedModelProvider,
  modelRequest: ModelRequest,
  signal: AbortSignal,
): Promise<ModelEvent[]> {
  const events: ModelEvent[] = [];
  for await (const event of provider.complete(modelRequest, signal)) {
    events.push(event);
  }
  return events;
}

describe("ScriptedModelProvider script replay", () => {
  test("streams each script in order and records the requests it served", async () => {
    const provider = new ScriptedModelProvider([TEXT, COMPLETED], [PROVIDER_ERROR]);
    const first = await collect(provider, request("scripted-1"), new AbortController().signal);
    const second = await collect(provider, request("scripted-2"), new AbortController().signal);

    expect(first).toEqual([
      { type: "textDelta", text: "Hello" },
      { type: "completed", finishReason: "stop" },
    ]);
    expect(second).toEqual([
      {
        type: "providerError",
        error: { kind: "rateLimit", retryable: true, message: "slow down" },
      },
    ]);
    expect(provider.requests.map((r) => r.model)).toEqual(["scripted-1", "scripted-2"]);
  });

  test("every emitted event validates against the ModelEvent union", async () => {
    const provider = new ScriptedModelProvider([TEXT, COMPLETED]);
    const events = await collect(provider, request("scripted-1"), new AbortController().signal);
    for (const event of events) {
      expect(ModelEventSchema.parse(event)).toBeTruthy();
    }
  });
});

describe("ScriptedModelProvider cancellation", () => {
  test("an aborted signal yields an empty stream without throwing", async () => {
    const provider = new ScriptedModelProvider([TEXT, COMPLETED]);
    const controller = new AbortController();
    controller.abort();

    const events = await collect(provider, request("scripted-1"), controller.signal);

    expect(events).toEqual([]);
    expect(provider.requests).toHaveLength(1);
  });

  test("aborting at waitForAbort ends the stream quietly with no terminal event", async () => {
    const provider = new ScriptedModelProvider([TEXT, { kind: "waitForAbort" }, COMPLETED]);
    const controller = new AbortController();

    const events: ModelEvent[] = [];
    const consumer = (async () => {
      for await (const event of provider.complete(request("scripted-1"), controller.signal)) {
        events.push(event);
      }
    })();

    await new Promise((resolve) => setImmediate(resolve));
    controller.abort();
    await consumer;

    expect(events).toEqual([{ type: "textDelta", text: "Hello" }]);
  });

  test("aborting between events stops the stream before the next event", async () => {
    const provider = new ScriptedModelProvider([TEXT, COMPLETED]);
    const controller = new AbortController();

    const events: ModelEvent[] = [];
    for await (const event of provider.complete(request("scripted-1"), controller.signal)) {
      events.push(event);
      controller.abort();
    }

    expect(events).toEqual([{ type: "textDelta", text: "Hello" }]);
  });
});

describe("ScriptedModelProvider failure injection", () => {
  test("a providerError script item surfaces as a normalized providerError event", async () => {
    const provider = new ScriptedModelProvider([PROVIDER_ERROR]);
    const events = await collect(provider, request("scripted-1"), new AbortController().signal);

    expect(events).toEqual([
      {
        type: "providerError",
        error: { kind: "rateLimit", retryable: true, message: "slow down" },
      },
    ]);
  });

  test("consuming beyond the script end throws an explicit invariant error", async () => {
    const provider = new ScriptedModelProvider([COMPLETED]);
    await collect(provider, request("scripted-1"), new AbortController().signal);

    await expect(
      collect(provider, request("scripted-2"), new AbortController().signal),
    ).rejects.toThrow(/script exhausted/u);
  });
});
