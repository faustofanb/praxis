import {
  MODEL_EVENT_TYPES,
  MODEL_PROVIDER_ERROR_KINDS,
  ModelRequestFailedEventSchema,
  ModelResponseCompletedEventSchema,
  SessionEventUnionSchema,
  ToolProposedEventSchema,
  TurnStartedEventSchema,
} from "@praxis/contracts";
import { describe, expect, test } from "vitest";
import {
  modelRequestFailed,
  modelRequestStarted,
  modelResponseCompleted,
  toolProposed,
  turnStarted,
} from "./helpers/session-events";

describe("model lifecycle event schemas", () => {
  test("every model event type parses through the session union", () => {
    const samples = [
      modelRequestStarted(1),
      modelResponseCompleted(2, { text: "hello" }),
      modelResponseCompleted(2, {
        toolCalls: [{ id: "call-1", name: "read_file", argumentsJson: "{}" }],
      }),
      modelRequestFailed(2),
    ];
    for (const sample of samples) {
      expect(SessionEventUnionSchema.parse(sample)).toBeTruthy();
    }
  });

  test("the vocabulary covers exactly the three model events", () => {
    expect(MODEL_EVENT_TYPES).toEqual([
      "ModelRequestStarted",
      "ModelResponseCompleted",
      "ModelRequestFailed",
    ]);
  });

  test("ModelRequestStarted requires a non-empty model id", () => {
    expect(() =>
      SessionEventUnionSchema.parse({
        ...modelRequestStarted(1),
        payload: { model: "" },
      }),
    ).toThrow();
  });

  test("ModelResponseCompleted defaults toolCalls to an empty array", () => {
    const parsed = ModelResponseCompletedEventSchema.parse(modelResponseCompleted(1));
    expect(parsed.payload.toolCalls).toEqual([]);
    expect(parsed.payload.text).toBeUndefined();
  });

  test("ModelResponseCompleted tool calls carry id, name, and argumentsJson", () => {
    const valid = ModelResponseCompletedEventSchema.parse(
      modelResponseCompleted(1, {
        toolCalls: [{ id: "call-1", name: "read_file", argumentsJson: "{}" }],
      }),
    );
    expect(valid.payload.toolCalls?.[0]?.name).toBe("read_file");
    expect(() =>
      ModelResponseCompletedEventSchema.parse({
        ...modelResponseCompleted(1),
        payload: {
          toolCalls: [{ id: "", name: "read_file", argumentsJson: "{}" }],
        },
      }),
    ).toThrow();
    expect(() =>
      ModelResponseCompletedEventSchema.parse({
        ...modelResponseCompleted(1),
        payload: {
          toolCalls: [{ id: "call-1", name: "", argumentsJson: "{}" }],
        },
      }),
    ).toThrow();
  });

  test("ModelRequestFailed carries a normalized kind, retryability, and a message", () => {
    for (const kind of MODEL_PROVIDER_ERROR_KINDS) {
      const parsed = ModelRequestFailedEventSchema.parse(
        modelRequestFailed(1, { kind, retryable: true, message: `boom: ${kind}` }),
      );
      expect(parsed.payload.kind).toBe(kind);
      expect(parsed.payload.retryable).toBe(true);
    }
    expect(() =>
      SessionEventUnionSchema.parse({
        ...modelRequestFailed(1),
        payload: { kind: "cosmic", retryable: false, message: "nope" },
      }),
    ).toThrow();
    expect(() =>
      SessionEventUnionSchema.parse({
        ...modelRequestFailed(1),
        payload: { kind: "network", retryable: false, message: "" },
      }),
    ).toThrow();
  });

  test("TurnStarted carries the user input as an optional fact", () => {
    expect(TurnStartedEventSchema.parse(turnStarted(1, 1)).payload.input).toBeUndefined();
    expect(TurnStartedEventSchema.parse(turnStarted(1, 1, "hello")).payload.input).toBe("hello");
  });

  test("ToolProposed optionally correlates with the model tool call id", () => {
    expect(ToolProposedEventSchema.parse(toolProposed(1, 1)).payload.toolCallId).toBeUndefined();
    const correlated = ToolProposedEventSchema.parse(toolProposed(1, 1, { toolCallId: "call-1" }));
    expect(correlated.payload.toolCallId).toBe("call-1");
    expect(() =>
      SessionEventUnionSchema.parse({
        ...toolProposed(1, 1),
        payload: {
          toolExecutionId: "tool-exec-1",
          name: "read_file",
          argumentsJson: "{}",
          effect: "read_only",
          toolCallId: "",
        },
      }),
    ).toThrow();
  });

  test("rejects model-adjacent types outside the vocabulary", () => {
    expect(() =>
      SessionEventUnionSchema.parse({
        ...modelRequestStarted(1),
        type: "ModelStreamChunk",
      }),
    ).toThrow();
  });
});
