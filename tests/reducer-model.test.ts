import type { SessionEventUnion } from "@praxis/contracts";
import {
  type DerivedSessionState,
  foldSessionEvents,
  initialSessionState,
  reduceSession,
} from "@praxis/core";
import { describe, expect, test } from "vitest";
import {
  modelRequestFailed,
  modelRequestStarted,
  modelResponseCompleted,
  sessionCompleted,
  sessionCreated,
  toolProposed,
  turnCompleted,
  turnStarted,
} from "./helpers/session-events";

function active(): DerivedSessionState {
  return foldSessionEvents([sessionCreated(1)]);
}

function openTurnWithRequest(): { state: DerivedSessionState; events: SessionEventUnion[] } {
  const events = [sessionCreated(1), turnStarted(2, 1), modelRequestStarted(3)];
  return { state: foldSessionEvents(events), events };
}

describe("reducer model-call transitions", () => {
  test("ModelRequestStarted sets pendingModelRequest inside an open turn", () => {
    const state = foldSessionEvents([sessionCreated(1), turnStarted(2, 1), modelRequestStarted(3)]);
    expect(state.pendingModelRequest).toEqual({ model: "test-model" });
    expect(state.headSeq).toBe(3);
  });

  test("ModelRequestStarted requires an open turn", () => {
    expect(() => reduceSession(active(), modelRequestStarted(2, "test-model"))).toThrow(
      /requires an open turn/u,
    );
  });

  test("a second concurrent model request is rejected", () => {
    const { state } = openTurnWithRequest();
    expect(() => reduceSession(state, modelRequestStarted(4))).toThrow(/still pending/u);
  });

  test("ModelResponseCompleted clears the pending request", () => {
    const { state } = openTurnWithRequest();
    const next = reduceSession(state, modelResponseCompleted(4, { text: "hello" }));
    expect(next.pendingModelRequest).toBeUndefined();
  });

  test("ModelRequestFailed clears the pending request", () => {
    const { state } = openTurnWithRequest();
    const next = reduceSession(
      state,
      modelRequestFailed(4, { kind: "rateLimit", retryable: true }),
    );
    expect(next.pendingModelRequest).toBeUndefined();
  });

  test("a response without a pending request is rejected", () => {
    const state = foldSessionEvents([sessionCreated(1), turnStarted(2, 1)]);
    expect(() => reduceSession(state, modelResponseCompleted(3))).toThrow(/no pending/u);
    expect(() => reduceSession(state, modelRequestFailed(3))).toThrow(/no pending/u);
  });

  test("model request-response pairs alternate within one turn", () => {
    const state = foldSessionEvents([
      sessionCreated(1),
      turnStarted(2, 1),
      modelRequestStarted(3),
      modelResponseCompleted(4, { text: "first" }),
      modelRequestStarted(5),
      modelRequestFailed(6, { kind: "network", retryable: true }),
      modelRequestStarted(7),
      modelResponseCompleted(8, { toolCalls: [] }),
      turnCompleted(9, 1),
      sessionCompleted(10),
    ]);
    expect(state.status).toBe("COMPLETED");
    expect(state.pendingModelRequest).toBeUndefined();
  });

  test("TurnCompleted is rejected while a model request is pending", () => {
    const { state } = openTurnWithRequest();
    expect(() => reduceSession(state, turnCompleted(4, 1))).toThrow(
      /model request to test-model is still pending/u,
    );
  });

  test("ToolProposed is rejected while a model request is pending", () => {
    const { state } = openTurnWithRequest();
    expect(() => reduceSession(state, toolProposed(4, 1))).toThrow(/still pending/u);
  });

  test("model events in a non-ACTIVE session are rejected", () => {
    const paused = foldSessionEvents([sessionCreated(1), sessionCompleted(2)]);
    expect(() => reduceSession(paused, { ...modelRequestStarted(3), seq: 3 })).toThrow(
      /requires status ACTIVE/u,
    );
  });

  test("folding the full happy path yields the expected derived state", () => {
    const state = foldSessionEvents([
      sessionCreated(1),
      turnStarted(2, 1, "list the workspace"),
      modelRequestStarted(3),
      modelResponseCompleted(4, {
        toolCalls: [{ id: "call-1", name: "list_dir", argumentsJson: '{"path":"."}' }],
      }),
      toolProposed(5, 1, { name: "list_dir", argumentsJson: '{"path":"."}', toolCallId: "call-1" }),
    ]);
    expect(state.pendingModelRequest).toBeUndefined();
    expect(state.currentTurnId).toBeDefined();
    expect([...state.toolExecutions.keys()].length).toBe(1);
  });

  test("reduceSession stays pure across repeated folds of the same stream", () => {
    const events: SessionEventUnion[] = [
      sessionCreated(1),
      turnStarted(2, 1, "hi"),
      modelRequestStarted(3),
      modelResponseCompleted(4, { text: "hello" }),
      turnCompleted(5, 1),
    ];
    const first = foldSessionEvents(events);
    const second = foldSessionEvents(events);
    expect(first).toEqual(second);
    expect(initialSessionState().pendingModelRequest).toBeUndefined();
  });
});
