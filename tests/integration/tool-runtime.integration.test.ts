import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { ModelEvent, SessionEventUnion } from "@praxis/contracts";
import {
  asEventId,
  asSessionId,
  asToolExecutionId,
  ModelRequestSchema,
  SessionEventUnionSchema,
} from "@praxis/contracts";
import {
  buildContext,
  executeToolCall,
  foldSessionEvents,
  projectSessionState,
} from "@praxis/core";
import { ScriptedModelProvider } from "@praxis/testkit";
import { localReadTools } from "@praxis/tools-local";
import { afterEach, beforeEach, describe, expect, test } from "vitest";
import { inMemoryEventStore } from "../helpers/in-memory-event-store";
import { sessionCreated, turnStarted } from "../helpers/session-events";

const SESSION_ID = asSessionId("session-integration");

let root: string;
beforeEach(async () => {
  root = await mkdtemp(join(tmpdir(), "praxis-int-"));
  await writeFile(join(root, "note.txt"), "integration note body");
});
afterEach(async () => {
  await rm(root, { recursive: true, force: true });
});

describe("model tool call through the runtime into durable facts and context", () => {
  test("scripted model proposes read_file; the runtime executes and the fact reaches the next context", async () => {
    const store = inMemoryEventStore();
    await store.append(
      [sessionCreated(1), turnStarted(2, 1)].map((event) => ({
        ...event,
        sessionId: SESSION_ID,
      })),
      0,
    );

    let counter = 100;
    let executions = 0;
    const deps = {
      store,
      sessionId: SESSION_ID,
      tools: localReadTools(root),
      now: () => {
        counter += 1;
        return counter;
      },
      newEventId: () => asEventId(`event-${counter}`),
      newToolExecutionId: () => {
        executions += 1;
        return asToolExecutionId(`tool-exec-${executions}`);
      },
    };

    const provider = new ScriptedModelProvider([
      { kind: "event", event: { type: "textDelta", text: "Checking the note." } },
      {
        kind: "event",
        event: { type: "toolCallStart", toolCallId: "call-1", name: "read_file" },
      },
      {
        kind: "event",
        event: { type: "toolCallDelta", toolCallId: "call-1", argumentsDelta: '{"path":"note.' },
      },
      {
        kind: "event",
        event: { type: "toolCallDelta", toolCallId: "call-1", argumentsDelta: 'txt"}' },
      },
      { kind: "event", event: { type: "toolCallEnd", toolCallId: "call-1" } },
      { kind: "event", event: { type: "completed", finishReason: "toolCalls" } },
    ]);

    const stream = provider.complete(
      ModelRequestSchema.parse({
        model: "scripted-1",
        messages: [{ role: "user", text: "read note.txt" }],
      }),
      new AbortController().signal,
    );
    let toolCall: { id: string; name: string; argumentsJson: string } | undefined;
    let argumentsBuffer = "";
    for await (const event of stream) {
      if (event.type === "toolCallStart") {
        toolCall = { id: event.toolCallId, name: event.name, argumentsJson: "" };
      } else if (event.type === "toolCallDelta" && toolCall !== undefined) {
        argumentsBuffer += event.argumentsDelta;
        toolCall.argumentsJson = argumentsBuffer;
      }
    }
    if (toolCall === undefined) {
      throw new Error("scripted model produced no tool call");
    }

    const summary = await executeToolCall(deps, toolCall, {
      signal: new AbortController().signal,
    });
    expect(summary.status).toBe("SUCCEEDED");

    const state = await projectSessionState(deps);
    const snapshot = [...state.toolExecutions.values()][0];
    expect(snapshot?.name).toBe("read_file");
    expect(snapshot?.resultJson).toContain("integration note body");

    const built = buildContext({
      systemPrompt: "You are Praxis in a read-only session.",
      history: [
        { role: "user", text: "read note.txt" },
        { role: "tool", toolCallId: "call-1", text: snapshot?.resultJson ?? "" },
      ],
      tools: [
        {
          name: "read_file",
          description: "read a file",
          parametersJson: '{"type":"object"}',
        },
      ],
    });
    expect(built.messages[0]?.role).toBe("system");
    const toolMessage = built.messages.find((m) => m.role === "tool");
    expect(toolMessage && toolMessage.role === "tool" && toolMessage.text).toContain(
      "integration note body",
    );
  });
});

describe("tool lifecycle replay fixture", () => {
  test("the fixture loads through the schema and replays to the expected projection", async () => {
    const raw = await readFile(
      join(import.meta.dirname, "../fixtures/replay/session-tool-lifecycle-v1.json"),
      "utf8",
    );
    const events = (JSON.parse(raw) as unknown[]).map((event) =>
      SessionEventUnionSchema.parse(event),
    ) as SessionEventUnion[];

    const state = foldSessionEvents(events);
    expect(state.status).toBe("COMPLETED");
    expect(state.headSeq).toBe(10);
    expect(state.toolExecutions.size).toBe(2);
    const first = [...state.toolExecutions.values()].find((s) => s.toolExecutionId.endsWith("-1"));
    expect(first?.status).toBe("SUCCEEDED");
    const second = [...state.toolExecutions.values()].find((s) => s.toolExecutionId.endsWith("-2"));
    expect(second?.status).toBe("REJECTED");
    expect(second?.rejectionReason).toContain("not permitted");
  });
});
