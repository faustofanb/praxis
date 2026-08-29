import type { ModelMessage } from "@praxis/contracts";
import { ModelMessageSchema } from "@praxis/contracts";
import type { ContextBudget } from "@praxis/core";
import {
  buildContext,
  ContextBudgetExceededError,
  DEFAULT_CONTEXT_BUDGET,
  InvalidContextBudgetError,
  InvalidContextError,
} from "@praxis/core";
import { describe, expect, test } from "vitest";

const encoder = new TextEncoder();
const utf8Bytes = (text: string): number => encoder.encode(text).length;

const tinyBudget: ContextBudget = {
  maxRecentMessages: 3,
  maxFragmentBytes: 120,
  maxToolResultBytes: 60,
  maxActiveObservations: 2,
  maxEstimatedTokens: 10_000,
};

describe("buildContext composition", () => {
  test("places the system fragment first and passes tools through", () => {
    const built = buildContext({
      systemPrompt: "You are a test harness.",
      history: [{ role: "user", text: "hi" }],
      tools: [
        {
          name: "read_file",
          description: "read a file",
          parametersJson: '{"type":"object"}',
        },
      ],
    });

    expect(built.messages[0]).toEqual({
      role: "system",
      text: "You are a test harness.",
    });
    expect(built.messages[1]).toEqual({ role: "user", text: "hi" });
    expect(built.tools).toHaveLength(1);
    expect(built.estimate.estimatedTokens).toBeGreaterThan(0);
    expect(built.estimate.droppedMessages).toBe(0);
    expect(built.estimate.truncatedFragments).toBe(0);
  });

  test("every built message stays valid against the contracts schema", () => {
    const built = buildContext({
      systemPrompt: "s",
      history: [
        { role: "user", text: "read it".repeat(60) },
        {
          role: "assistant",
          text: "reading",
          toolCalls: [
            {
              id: "call-1",
              name: "read_file",
              argumentsJson: `{"blob":"${"x".repeat(300)}"}`,
            },
          ],
        },
        { role: "tool", toolCallId: "call-1", text: "y".repeat(300) },
      ],
    });
    for (const message of built.messages) {
      expect(ModelMessageSchema.parse(message)).toBeTruthy();
    }
  });

  test("same input and budget always build the same context", () => {
    const input = {
      systemPrompt: "s",
      history: [
        { role: "user", text: "one" },
        { role: "tool", toolCallId: "c1", text: "r".repeat(100) },
        { role: "user", text: "two" },
      ] as ModelMessage[],
    };
    expect(JSON.stringify(buildContext(input, tinyBudget))).toBe(
      JSON.stringify(buildContext(input, tinyBudget)),
    );
  });
});

describe("buildContext windowing and budget caps", () => {
  test("keeps only the newest maxRecentMessages in original order", () => {
    const history: ModelMessage[] = [1, 2, 3, 4, 5].map((n) => ({
      role: "user" as const,
      text: `msg-${n}`,
    }));
    const built = buildContext({ systemPrompt: "s", history }, tinyBudget);

    expect(built.messages.slice(1).map((m) => (m as { text: string }).text)).toEqual([
      "msg-3",
      "msg-4",
      "msg-5",
    ]);
    expect(built.estimate.droppedMessages).toBe(2);
  });

  test("head-truncates oversized tool results with a byte marker within cap", () => {
    const body = "ä".repeat(80); // 2 bytes per char = 160 bytes > 60 cap
    const built = buildContext(
      {
        systemPrompt: "s",
        history: [{ role: "tool", toolCallId: "call-1", text: body }],
      },
      tinyBudget,
    );

    const toolMessage = built.messages[1];
    if (toolMessage?.role !== "tool") {
      throw new Error("expected a tool message");
    }
    expect(utf8Bytes(toolMessage.text)).toBeLessThanOrEqual(60);
    expect(toolMessage.text).toMatch(/…\[\+\d+ bytes truncated\]/u);
    expect(toolMessage.text.startsWith("ää")).toBe(true);
    expect(built.estimate.truncatedFragments).toBe(1);
  });

  test("head-truncates oversized user fragments within cap", () => {
    const built = buildContext(
      { systemPrompt: "s", history: [{ role: "user", text: "u".repeat(500) }] },
      tinyBudget,
    );
    const userMessage = built.messages[1];
    if (userMessage?.role !== "user") {
      throw new Error("expected a user message");
    }
    expect(utf8Bytes(userMessage.text)).toBeLessThanOrEqual(120);
    expect(userMessage.text).toMatch(/…\[\+\d+ bytes truncated\]/u);
  });

  test("counts assistant text and tool argument truncations separately", () => {
    const built = buildContext(
      {
        systemPrompt: "s",
        history: [
          {
            role: "assistant",
            text: "a".repeat(500),
            toolCalls: [
              {
                id: "call-1",
                name: "read_file",
                argumentsJson: `{"blob":"${"x".repeat(400)}"}`,
              },
            ],
          },
        ],
      },
      tinyBudget,
    );
    expect(built.estimate.truncatedFragments).toBe(2);
  });

  test("drops oldest history first under the token cap, keeping the trailing message", () => {
    const history: ModelMessage[] = [1, 2, 3, 4].map((n) => ({
      role: "user" as const,
      text: "payload ".repeat(10) + `#${n}`,
    }));
    const built = buildContext(
      { systemPrompt: "s", history },
      { ...tinyBudget, maxEstimatedTokens: 60 },
    );

    const kept = built.messages.slice(1).map((m) => (m as { text: string }).text);
    const last = kept[kept.length - 1];
    expect(last?.endsWith("#4")).toBe(true);
    expect(built.messages.length).toBeLessThan(history.length + 1);
    expect(built.estimate.estimatedTokens).toBeLessThanOrEqual(60);
    expect(built.estimate.droppedMessages).toBeGreaterThan(0);
  });
});

describe("buildContext failure modes", () => {
  test("rejects system messages inside history", () => {
    expect(() =>
      buildContext({
        systemPrompt: "s",
        history: [{ role: "system", text: "smuggled" }],
      }),
    ).toThrow(InvalidContextError);
  });

  test("rejects a system prompt that alone exceeds the token cap", () => {
    expect(() =>
      buildContext(
        { systemPrompt: "s".repeat(400), history: [] },
        { ...tinyBudget, maxEstimatedTokens: 10 },
      ),
    ).toThrow(/system prompt alone/u);
  });

  test("refuses to drop the trailing message to satisfy the token cap", () => {
    expect(() =>
      buildContext(
        {
          systemPrompt: "s",
          history: [{ role: "user", text: "u".repeat(400) }],
        },
        { ...tinyBudget, maxEstimatedTokens: 20 },
      ),
    ).toThrow(ContextBudgetExceededError);
    expect(() =>
      buildContext(
        {
          systemPrompt: "s",
          history: [{ role: "user", text: "u".repeat(400) }],
        },
        { ...tinyBudget, maxEstimatedTokens: 20 },
      ),
    ).toThrow(/trailing message/u);
  });

  test("rejects non-positive or sub-minimum budgets up front", () => {
    const input = { systemPrompt: "s", history: [] as ModelMessage[] };
    expect(() => buildContext(input, { ...DEFAULT_CONTEXT_BUDGET, maxRecentMessages: 0 })).toThrow(
      InvalidContextBudgetError,
    );
    expect(() => buildContext(input, { ...DEFAULT_CONTEXT_BUDGET, maxFragmentBytes: 10 })).toThrow(
      InvalidContextBudgetError,
    );
    expect(() =>
      buildContext(input, { ...DEFAULT_CONTEXT_BUDGET, maxToolResultBytes: -1 }),
    ).toThrow(InvalidContextBudgetError);
    expect(() =>
      buildContext(input, { ...DEFAULT_CONTEXT_BUDGET, maxEstimatedTokens: 1.5 }),
    ).toThrow(InvalidContextBudgetError);
    expect(() =>
      buildContext(input, { ...DEFAULT_CONTEXT_BUDGET, maxActiveObservations: 0 }),
    ).toThrow(InvalidContextBudgetError);
  });

  test("composes the epistemic brief into the single system fragment", () => {
    const built = buildContext({
      systemPrompt: "You are Praxis.",
      epistemicBrief: "## Goal\nGoal: restore the missing payment record",
      history: [{ role: "user", text: "proceed" }],
    });
    const system = built.messages[0];
    if (system?.role !== "system") {
      throw new Error("expected the system message first");
    }
    expect(system.text).toBe(
      "You are Praxis.\n\n## Goal\nGoal: restore the missing payment record",
    );
    expect(built.messages.filter((message) => message.role === "system")).toHaveLength(1);
  });

  test("omitting the brief keeps the system prompt byte-identical", () => {
    const built = buildContext({
      systemPrompt: "You are Praxis.",
      history: [{ role: "user", text: "proceed" }],
    });
    const system = built.messages[0];
    if (system?.role !== "system") {
      throw new Error("expected the system message first");
    }
    expect(system.text).toBe("You are Praxis.");
  });
});
