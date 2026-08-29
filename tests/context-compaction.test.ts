import type { ModelMessage } from "@praxis/contracts";
import {
  buildContext,
  DEFAULT_CONTEXT_BUDGET,
  foldSessionEvents,
  projectConversation,
  projectEpistemicBrief,
} from "@praxis/core";
import { describe, expect, test } from "vitest";
import { goalSet, sessionCreated, turnCompleted, turnStarted } from "./helpers/session-events";

/**
 * Deterministic compaction (docs/02 section 12.3, M5-T002): messages that
 * fall out of the recent-history window are replaced by one honest count
 * recap in the system fragment. Zero drops must stay byte-identical to the
 * M5-T001 projection, and a synthetic 1000-turn session must stay inside
 * every cap. The event store keeps full fidelity — compaction bounds the
 * working context only.
 */

const GOAL = "restore the missing payment record";

function longSessionEvents(turns: number) {
  const events = [sessionCreated(1), goalSet(2, { goal: GOAL })];
  for (let n = 1; n <= turns; n += 1) {
    events.push(turnStarted(2 * n + 1, n, `step ${n} of the long restoration`));
    events.push(turnCompleted(2 * n + 2, n));
  }
  return events;
}

describe("deterministic compaction recap", () => {
  test("replaces window-dropped messages with an honest count recap", () => {
    const history: ModelMessage[] = Array.from({ length: 10 }, (_, i) => ({
      role: "user" as const,
      text: `message #${i + 1}`,
    }));

    const built = buildContext(
      { systemPrompt: "s", history },
      { ...DEFAULT_CONTEXT_BUDGET, maxRecentMessages: 3 },
    );

    expect(built.messages).toHaveLength(4);
    expect(built.estimate.droppedMessages).toBe(7);
    const system = built.messages[0];
    if (system?.role !== "system") {
      throw new Error("expected the system fragment first");
    }
    expect(
      system.text.endsWith(
        "## Compacted history\n7 earlier messages compacted: 7 user, 0 assistant, 0 tool results",
      ),
    ).toBe(true);
    const trailing = built.messages[3];
    expect(trailing).toEqual({ role: "user", text: "message #10" });
  });

  test("counts each role from the dropped prefix only", () => {
    const history: ModelMessage[] = [
      { role: "user", text: "u1" },
      {
        role: "assistant",
        text: "a1",
        toolCalls: [{ id: "call-1", name: "read_file", argumentsJson: "{}" }],
      },
      { role: "tool", toolCallId: "call-1", text: '{"status":"succeeded"}' },
      { role: "user", text: "u2" },
      { role: "assistant", text: "a2" },
      { role: "user", text: "u3" },
      { role: "assistant", text: "a3" },
      { role: "user", text: "u4" },
      { role: "tool", toolCallId: "call-9", text: '{"status":"succeeded"}' },
    ];

    const built = buildContext(
      { systemPrompt: "s", history },
      { ...DEFAULT_CONTEXT_BUDGET, maxRecentMessages: 4 },
    );

    expect(built.estimate.droppedMessages).toBe(5);
    const system = built.messages[0];
    if (system?.role !== "system") {
      throw new Error("expected the system fragment first");
    }
    expect(system.text).toContain(
      "## Compacted history\n5 earlier messages compacted: 2 user, 2 assistant, 1 tool results",
    );
  });

  test("keeps the zero-drop build byte-identical to the M5-T001 projection", () => {
    const history: ModelMessage[] = [
      { role: "user", text: "hello" },
      { role: "assistant", text: "hi" },
    ];
    const brief = "## Goal\nGoal: restore the missing payment record";

    const built = buildContext(
      { systemPrompt: "You are Praxis.", epistemicBrief: brief, history },
      DEFAULT_CONTEXT_BUDGET,
    );

    const system = built.messages[0];
    if (system?.role !== "system") {
      throw new Error("expected the system fragment first");
    }
    expect(system.text).toBe(`You are Praxis.\n\n${brief}`);
    expect(built.estimate.droppedMessages).toBe(0);
  });

  test("a 1000-turn projected session stays inside every cap with exact recap counts", () => {
    const events = longSessionEvents(1000);
    const folded = foldSessionEvents(events);
    const history = projectConversation(events);

    expect(history).toHaveLength(1000);
    const brief = projectEpistemicBrief(folded, DEFAULT_CONTEXT_BUDGET);
    if (brief === undefined) {
      throw new Error("expected an epistemic brief for the seeded goal");
    }

    const built = buildContext(
      { systemPrompt: "You are Praxis.", epistemicBrief: brief, history },
      DEFAULT_CONTEXT_BUDGET,
    );

    expect(built.messages).toHaveLength(1 + DEFAULT_CONTEXT_BUDGET.maxRecentMessages);
    expect(built.estimate.estimatedTokens).toBeLessThanOrEqual(
      DEFAULT_CONTEXT_BUDGET.maxEstimatedTokens,
    );
    expect(built.estimate.droppedMessages).toBe(1000 - DEFAULT_CONTEXT_BUDGET.maxRecentMessages);

    const system = built.messages[0];
    if (system?.role !== "system") {
      throw new Error("expected the system fragment first");
    }
    // Non-compactable brief state survives alongside the recap.
    expect(system.text).toContain(`Goal: ${GOAL}`);
    expect(system.text).toContain(
      `## Compacted history\n936 earlier messages compacted: 936 user, 0 assistant, 0 tool results`,
    );

    // The window is the order-preserving suffix ending at the trailing turn.
    expect(built.messages[1]).toEqual({ role: "user", text: "step 937 of the long restoration" });
    const trailing = built.messages[built.messages.length - 1];
    expect(trailing).toEqual({ role: "user", text: "step 1000 of the long restoration" });

    // Pure projection: the same inputs build the identical context.
    const rebuilt = buildContext(
      { systemPrompt: "You are Praxis.", epistemicBrief: brief, history },
      DEFAULT_CONTEXT_BUDGET,
    );
    expect(rebuilt).toEqual(built);
  });
});
