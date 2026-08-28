import type { ModelEvent } from "@praxis/contracts";
import { ModelRequestSchema } from "@praxis/contracts";
import { buildContext } from "@praxis/core";
import { ScriptedModelProvider } from "@praxis/testkit";
import { describe, expect, test } from "vitest";

describe("context builder feeding the model boundary end to end", () => {
  test("a built context becomes a schema-valid request a scripted model can serve", async () => {
    const built = buildContext({
      systemPrompt: "You are Praxis running a read-only session.",
      history: [
        { role: "user", text: "Read the fixture config and summarize it." },
        {
          role: "assistant",
          text: "Reading the fixture config.",
          toolCalls: [
            {
              id: "call-1",
              name: "read_file",
              argumentsJson: '{"path":"fixtures/config.json"}',
            },
          ],
        },
        {
          role: "tool",
          toolCallId: "call-1",
          text: `${'{"version": 1}\n'.repeat(80)}`,
        },
        { role: "user", text: "Now summarize what you read." },
      ],
      tools: [
        {
          name: "read_file",
          description: "Read a file from the workspace root",
          parametersJson:
            '{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}',
        },
      ],
    });

    const request = ModelRequestSchema.parse({
      model: "scripted-1",
      messages: built.messages,
      tools: built.tools,
      correlationId: "integration-1",
    });

    const provider = new ScriptedModelProvider([
      { kind: "event", event: { type: "textDelta", text: "It is versioned " } },
      { kind: "event", event: { type: "textDelta", text: "config data." } },
      { kind: "event", event: { type: "completed", finishReason: "stop" } },
    ]);

    const events: ModelEvent[] = [];
    for await (const event of provider.complete(request, new AbortController().signal)) {
      events.push(event);
    }

    expect(built.messages[0]?.role).toBe("system");
    expect(built.estimate.droppedMessages).toBe(0);
    expect(events.map((event) => event.type)).toEqual(["textDelta", "textDelta", "completed"]);
    const terminal = events[events.length - 1];
    if (terminal?.type !== "completed") {
      throw new Error("expected a completed terminal event");
    }
    expect(terminal.finishReason).toBe("stop");
  });

  test("a tool result over the default cap is truncated but still schema-valid", () => {
    const built = buildContext({
      systemPrompt: "s",
      history: [
        { role: "tool", toolCallId: "call-1", text: "x".repeat(20_000) },
        { role: "user", text: "summarize" },
      ],
    });

    const request = ModelRequestSchema.parse({
      model: "scripted-1",
      messages: built.messages,
    });
    const toolMessage = request.messages.find((m) => m.role === "tool");
    if (toolMessage?.role !== "tool") {
      throw new Error("expected a tool message in the request");
    }
    expect(toolMessage.text).toMatch(/…\[\+\d+ bytes truncated\]/u);
    expect(built.estimate.truncatedFragments).toBe(1);
  });
});
