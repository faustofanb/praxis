import type { DerivedSessionState, ToolExecutionSnapshot } from "@praxis/core";
import { foldSessionEvents, initialSessionState, reduceSession } from "@praxis/core";
import { describe, expect, test } from "vitest";
import {
  sessionCreated,
  toolAuthorized,
  toolFailed,
  toolIndeterminate,
  toolProposed,
  toolRejected,
  toolStarted,
  toolSucceeded,
  turnCompleted,
  turnStarted,
} from "./helpers/session-events";

function snapshotOf(state: DerivedSessionState, execution: number): ToolExecutionSnapshot {
  const snapshot = [...state.toolExecutions.values()].find((s) =>
    s.toolExecutionId.endsWith(`-${execution}`),
  );
  if (snapshot === undefined) {
    throw new Error(`no snapshot for execution ${execution}`);
  }
  return snapshot;
}

describe("tool lifecycle transitions", () => {
  test("happy path: PROPOSED -> AUTHORIZED -> EXECUTING -> SUCCEEDED", () => {
    const state = foldSessionEvents([
      sessionCreated(1),
      turnStarted(2, 1),
      toolProposed(3, 1),
      toolAuthorized(4, 1),
      toolStarted(5, 1),
      toolSucceeded(6, 1, '{"content":"hi"}'),
      turnCompleted(7, 1),
    ]);
    const snapshot = snapshotOf(state, 1);
    expect(snapshot.status).toBe("SUCCEEDED");
    expect(snapshot.name).toBe("read_file");
    expect(snapshot.effect).toBe("read_only");
    expect(snapshot.turnId.endsWith("turn-1")).toBe(true);
    expect(snapshot.resultJson).toBe('{"content":"hi"}');
    expect(state.currentTurnId).toBeUndefined();
  });

  test("denial path: PROPOSED -> REJECTED records the reason", () => {
    const state = foldSessionEvents([
      sessionCreated(1),
      turnStarted(2, 1),
      toolProposed(3, 1),
      toolRejected(4, 1, "write tools are out of scope"),
      turnCompleted(5, 1),
    ]);
    const snapshot = snapshotOf(state, 1);
    expect(snapshot.status).toBe("REJECTED");
    expect(snapshot.rejectionReason).toBe("write tools are out of scope");
  });

  test("failure and indeterminate terminals are distinct first-class outcomes", () => {
    const failed = foldSessionEvents([
      sessionCreated(1),
      turnStarted(2, 1),
      toolProposed(3, 1),
      toolAuthorized(4, 1),
      toolStarted(5, 1),
      toolFailed(6, 1, "no such file"),
    ]);
    expect(snapshotOf(failed, 1).status).toBe("FAILED");
    expect(snapshotOf(failed, 1).failureMessage).toBe("no such file");

    const indeterminate = foldSessionEvents([
      sessionCreated(1),
      turnStarted(2, 1),
      toolProposed(3, 2),
      toolAuthorized(4, 2),
      toolStarted(5, 2),
      toolIndeterminate(6, 2, "request may have arrived"),
    ]);
    expect(snapshotOf(indeterminate, 2).status).toBe("INDETERMINATE");
    expect(snapshotOf(indeterminate, 2).indeterminateReason).toBe("request may have arrived");
  });

  test("TurnCompleted is blocked while the turn's tool execution is still active", () => {
    const base = [
      sessionCreated(1),
      turnStarted(2, 1),
      toolProposed(3, 1),
      toolAuthorized(4, 1),
      toolStarted(5, 1),
    ];
    expect(() => foldSessionEvents([...base, turnCompleted(6, 1)])).toThrow(/still EXECUTING/u);

    const finished = foldSessionEvents([...base, toolSucceeded(6, 1), turnCompleted(7, 1)]);
    expect(finished.status).toBe("ACTIVE");
  });
});

describe("illegal tool lifecycle transitions", () => {
  test("tool events require an ACTIVE session with an open turn", () => {
    expect(() => reduceSession(initialSessionState(), toolProposed(1, 1))).toThrow(
      /requires status ACTIVE/u,
    );
    const activeNoTurn = foldSessionEvents([sessionCreated(1)]);
    expect(() => reduceSession(activeNoTurn, toolProposed(2, 1))).toThrow(/requires an open turn/u);
  });

  test("tool execution ids are single-use", () => {
    const state = foldSessionEvents([sessionCreated(1), turnStarted(2, 1), toolProposed(3, 1)]);
    expect(() => reduceSession(state, toolProposed(4, 1))).toThrow(/already used/u);
  });

  test("authorization cannot be skipped or repeated", () => {
    const proposed = foldSessionEvents([sessionCreated(1), turnStarted(2, 1), toolProposed(3, 1)]);
    expect(() => reduceSession(proposed, toolStarted(4, 1))).toThrow(
      /requires tool status AUTHORIZED/u,
    );
    const authorized = foldSessionEvents([
      sessionCreated(1),
      turnStarted(2, 1),
      toolProposed(3, 1),
      toolAuthorized(4, 1),
    ]);
    expect(() => reduceSession(authorized, toolAuthorized(5, 1))).toThrow(
      /requires tool status PROPOSED/u,
    );
  });

  test("terminals never resurrect", () => {
    const succeeded = foldSessionEvents([
      sessionCreated(1),
      turnStarted(2, 1),
      toolProposed(3, 1),
      toolAuthorized(4, 1),
      toolStarted(5, 1),
      toolSucceeded(6, 1),
    ]);
    expect(() => reduceSession(succeeded, toolStarted(7, 1))).toThrow(
      /requires tool status AUTHORIZED/u,
    );
    expect(() => reduceSession(succeeded, toolFailed(7, 1))).toThrow(
      /requires tool status EXECUTING/u,
    );
    const rejected = foldSessionEvents([
      sessionCreated(1),
      turnStarted(2, 1),
      toolProposed(3, 1),
      toolRejected(4, 1),
    ]);
    expect(() => reduceSession(rejected, toolAuthorized(5, 1))).toThrow(
      /requires tool status PROPOSED/u,
    );
  });

  test("unknown tool executions are rejected", () => {
    const state = foldSessionEvents([sessionCreated(1), turnStarted(2, 1)]);
    expect(() => reduceSession(state, toolAuthorized(3, 99))).toThrow(/unknown tool execution/u);
  });

  test("tool events belonging to a closed turn are rejected", () => {
    const state = foldSessionEvents([
      sessionCreated(1),
      turnStarted(2, 1),
      toolProposed(3, 1),
      toolRejected(4, 1),
      turnCompleted(5, 1),
      turnStarted(6, 2),
    ]);
    expect(() => reduceSession(state, toolAuthorized(7, 1))).toThrow(/belongs to turn/u);
  });
});
