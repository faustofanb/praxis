import type { ModelMessage, ToolCallRequest } from "@praxis/contracts";
import type { BuiltContext, ContextBudget } from "@praxis/core";
import { buildContext, ContextBudgetExceededError, MIN_FRAGMENT_CAP_BYTES } from "@praxis/core";
import fc from "fast-check";
import { describe, expect, test } from "vitest";

const encoder = new TextEncoder();
const utf8Bytes = (text: string): number => encoder.encode(text).length;

const toolCallArb: fc.Arbitrary<ToolCallRequest> = fc.record({
  id: fc.string({ minLength: 1, maxLength: 12 }),
  name: fc.string({ minLength: 1, maxLength: 12 }),
  argumentsJson: fc.string({ maxLength: 200 }),
});

const messageArb: fc.Arbitrary<ModelMessage> = fc.oneof(
  fc.record({ role: fc.constant("user" as const), text: fc.string({ maxLength: 300 }) }),
  fc.record({
    role: fc.constant("assistant" as const),
    text: fc.string({ maxLength: 300 }),
    toolCalls: fc.array(toolCallArb, { maxLength: 2 }),
  }),
  fc.record({
    role: fc.constant("tool" as const),
    toolCallId: fc.string({ minLength: 1, maxLength: 12 }),
    text: fc.string({ maxLength: 300 }),
  }),
);

const budgetArb: fc.Arbitrary<ContextBudget> = fc.record({
  maxRecentMessages: fc.integer({ min: 1, max: 8 }),
  maxFragmentBytes: fc.integer({ min: MIN_FRAGMENT_CAP_BYTES, max: 600 }),
  maxToolResultBytes: fc.integer({ min: MIN_FRAGMENT_CAP_BYTES, max: 600 }),
  maxEstimatedTokens: fc.integer({ min: 1, max: 100_000 }),
});

const inputArb = fc.record({
  systemPrompt: fc.string({ maxLength: 300 }),
  history: fc.array(messageArb, { maxLength: 20 }),
});

function tryBuild(
  input: { systemPrompt: string; history: ModelMessage[] },
  budget: ContextBudget,
): BuiltContext | "budget-exceeded" {
  try {
    return buildContext(input, budget);
  } catch (error) {
    if (error instanceof ContextBudgetExceededError) {
      return "budget-exceeded";
    }
    throw error;
  }
}

describe("buildContext properties", () => {
  test("a successful build never exceeds any declared cap", () => {
    fc.assert(
      fc.property(inputArb, budgetArb, (input, budget) => {
        const built = tryBuild(input, budget);
        if (built === "budget-exceeded") {
          return true;
        }
        const history = built.messages.slice(1);

        if (history.length > budget.maxRecentMessages) {
          throw new Error("history window exceeded maxRecentMessages");
        }
        if (built.estimate.estimatedTokens > budget.maxEstimatedTokens) {
          throw new Error("estimate exceeded maxEstimatedTokens");
        }
        for (const message of built.messages) {
          if (message.role === "system" || message.role === "user") {
            if (utf8Bytes(message.text) > budget.maxFragmentBytes) {
              throw new Error(`${message.role} fragment exceeded cap`);
            }
          }
          if (message.role === "assistant") {
            for (const text of [
              message.text ?? "",
              ...(message.toolCalls?.map((c) => c.argumentsJson) ?? []),
            ]) {
              if (utf8Bytes(text) > budget.maxFragmentBytes) {
                throw new Error("assistant fragment exceeded cap");
              }
            }
          }
          if (message.role === "tool") {
            if (utf8Bytes(message.text) > budget.maxToolResultBytes) {
              throw new Error("tool result exceeded cap");
            }
          }
        }
        return true;
      }),
    );
  });

  test("kept history is an order-preserving suffix of the input, ending at the trailing message", () => {
    fc.assert(
      fc.property(inputArb, budgetArb, (input, budget) => {
        const built = tryBuild(input, budget);
        if (built === "budget-exceeded") {
          return true;
        }
        const history = built.messages.slice(1);
        if (input.history.length === 0) {
          if (history.length !== 0) {
            throw new Error("built history from empty input");
          }
          return true;
        }

        const tail = input.history.slice(input.history.length - history.length);
        if (history.length !== tail.length) {
          throw new Error("suffix length mismatch");
        }
        for (let i = 0; i < history.length; i += 1) {
          const kept = history[i];
          const source = tail[i];
          if (kept === undefined || source === undefined) {
            throw new Error("indexing mismatch");
          }
          if (kept.role !== source.role) {
            throw new Error("order not preserved");
          }
          if (kept.role === "tool" && source.role === "tool") {
            if (kept.toolCallId !== source.toolCallId) {
              throw new Error("tool identity not preserved");
            }
          }
        }

        const lastKept = history[history.length - 1];
        const lastInput = input.history[input.history.length - 1];
        if (lastKept === undefined || lastInput === undefined || lastKept.role !== lastInput.role) {
          throw new Error("trailing message was dropped");
        }
        return true;
      }),
    );
  });

  test("building is deterministic for identical input and budget", () => {
    fc.assert(
      fc.property(inputArb, budgetArb, (input, budget) => {
        const first = tryBuild(input, budget);
        const second = tryBuild(input, budget);
        if (first === "budget-exceeded" || second === "budget-exceeded") {
          expect(first).toBe(second);
          return true;
        }
        expect(JSON.stringify(first)).toBe(JSON.stringify(second));
        return true;
      }),
    );
  });
});
