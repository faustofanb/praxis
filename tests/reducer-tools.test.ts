import type { DerivedSessionState, ToolExecutionSnapshot } from "@praxis/core";
import { foldSessionEvents, initialSessionState, reduceSession } from "@praxis/core";
import { describe, expect, test } from "vitest";
import {
  sessionCreated,
  sessionPaused,
  sessionResumed,
  toolAuthorized,
  toolFailed,
  toolIndeterminate,
  toolProposed,
  toolReconciled,
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

describe("reconciliation transitions", () => {
  // PROPOSED -> ... -> INDETERMINATE prefix shared by every reconciliation case.
  function indeterminate(execution: number, reason = "response lost after send") {
    return foldSessionEvents([
      sessionCreated(1),
      turnStarted(2, 1),
      toolProposed(3, execution, { effect: "reconcilable_write" }),
      toolAuthorized(4, execution),
      toolStarted(5, execution),
      toolIndeterminate(6, execution, reason),
    ]);
  }

  test("reconciled succeeded settles INDETERMINATE into SUCCEEDED with the proof", () => {
    const state = reduceSession(
      indeterminate(1),
      toolReconciled(7, 1, "succeeded", '{"paymentId":"pay_1"}'),
    );
    const snapshot = snapshotOf(state, 1);
    expect(snapshot.status).toBe("SUCCEEDED");
    expect(snapshot.resultJson).toBe('{"paymentId":"pay_1"}');
    expect(snapshot.reconciliationCount).toBe(1);
    expect(snapshot.indeterminateReason).toBe("response lost after send");
  });

  test("reconciled failed settles INDETERMINATE into FAILED with the provable absence", () => {
    const state = reduceSession(indeterminate(2), toolReconciled(7, 2, "failed", "key never seen"));
    const snapshot = snapshotOf(state, 2);
    expect(snapshot.status).toBe("FAILED");
    expect(snapshot.failureMessage).toBe("key never seen");
    expect(snapshot.reconciliationCount).toBe(1);
  });

  test("reconciled indeterminate stays INDETERMINATE with the new reason", () => {
    const state = reduceSession(
      indeterminate(3),
      toolReconciled(7, 3, "indeterminate", "provider query timed out too"),
    );
    const snapshot = snapshotOf(state, 3);
    expect(snapshot.status).toBe("INDETERMINATE");
    expect(snapshot.indeterminateReason).toBe("provider query timed out too");
    expect(snapshot.reconciliationCount).toBe(1);
  });

  test("INDETERMINATE may reconcile repeatedly until it settles", () => {
    const state = [
      toolReconciled(7, 4, "indeterminate", "still unknown"),
      toolReconciled(8, 4, "indeterminate", "still unknown after escalation"),
      toolReconciled(9, 4, "succeeded", '{"ok":true}'),
    ].reduce(reduceSession, indeterminate(4));
    const snapshot = snapshotOf(state, 4);
    expect(snapshot.status).toBe("SUCCEEDED");
    expect(snapshot.reconciliationCount).toBe(3);
    expect(snapshot.resultJson).toBe('{"ok":true}');
  });

  test("reconciled succeeded settles after the pause closed the turn (post-resume)", () => {
    // Section 17 escalation closes the turn before SessionPaused, so the
    // resumed session has no open turn; the settling fact is still legal.
    const resumed = [turnCompleted(7, 1), sessionPaused(8), sessionResumed(9)].reduce(
      reduceSession,
      indeterminate(1),
    );
    const state = reduceSession(resumed, toolReconciled(10, 1, "succeeded", '{"verified":true}'));
    const snapshot = snapshotOf(state, 1);
    expect(snapshot.status).toBe("SUCCEEDED");
    expect(snapshot.resultJson).toBe('{"verified":true}');
    expect(snapshot.reconciliationCount).toBe(1);
  });

  test("reconciliation count starts at zero for ordinary executions", () => {
    const state = foldSessionEvents([
      sessionCreated(1),
      turnStarted(2, 1),
      toolProposed(3, 1),
      toolAuthorized(4, 1),
      toolStarted(5, 1),
      toolSucceeded(6, 1),
    ]);
    expect(snapshotOf(state, 1).reconciliationCount).toBe(0);
  });
});

describe("illegal reconciliation transitions", () => {
  test("ToolReconciled requires INDETERMINATE, from every other status", () => {
    const base = [
      sessionCreated(1),
      turnStarted(2, 1),
      toolProposed(3, 1, { effect: "reconcilable_write" }),
    ];
    const proposed = { state: foldSessionEvents(base), nextSeq: 4 };
    const authorized = {
      state: foldSessionEvents([...base, toolAuthorized(4, 1)]),
      nextSeq: 5,
    };
    const executing = {
      state: foldSessionEvents([...base, toolAuthorized(4, 1), toolStarted(5, 1)]),
      nextSeq: 6,
    };
    const succeeded = {
      state: foldSessionEvents([
        ...base,
        toolAuthorized(4, 1),
        toolStarted(5, 1),
        toolSucceeded(6, 1),
      ]),
      nextSeq: 7,
    };
    const failed = {
      state: foldSessionEvents([
        ...base,
        toolAuthorized(4, 1),
        toolStarted(5, 1),
        toolFailed(6, 1),
      ]),
      nextSeq: 7,
    };
    const rejected = {
      state: foldSessionEvents([...base, toolRejected(4, 1)]),
      nextSeq: 5,
    };

    for (const { state, nextSeq } of [
      proposed,
      authorized,
      executing,
      succeeded,
      failed,
      rejected,
    ]) {
      expect(() => reduceSession(state, toolReconciled(nextSeq, 1, "succeeded"))).toThrow(
        /requires tool status INDETERMINATE/u,
      );
    }
  });

  test("reconciliation terminals never resurrect", () => {
    const settled = foldSessionEvents([
      sessionCreated(1),
      turnStarted(2, 1),
      toolProposed(3, 1, { effect: "reconcilable_write" }),
      toolAuthorized(4, 1),
      toolStarted(5, 1),
      toolIndeterminate(6, 1, "unknown"),
      toolReconciled(7, 1, "failed", "provably absent"),
    ]);
    const snapshot = snapshotOf(settled, 1);
    expect(snapshot.status).toBe("FAILED");
    expect(snapshot.reconciliationCount).toBe(1);
    expect(() => reduceSession(settled, toolReconciled(8, 1, "succeeded"))).toThrow(
      /requires tool status INDETERMINATE/u,
    );
    expect(() => reduceSession(settled, toolStarted(8, 1))).toThrow(
      /requires tool status AUTHORIZED/u,
    );
  });

  test("reconciliation of an unknown execution is rejected", () => {
    const state = foldSessionEvents([sessionCreated(1), turnStarted(2, 1)]);
    expect(() => reduceSession(state, toolReconciled(3, 99))).toThrow(/unknown tool execution/u);
  });

  test("reconciliation is a historical fact: a closed turn does not block it", () => {
    // Section 17 escalation closes the turn before SessionPaused; a resumed
    // session (no open turn) must still be able to settle its indeterminates,
    // so ToolReconciled must not require the execution's turn to be open.
    const closedTurn = foldSessionEvents([
      sessionCreated(1),
      turnStarted(2, 1),
      toolProposed(3, 1),
      toolAuthorized(4, 1),
      toolStarted(5, 1),
      toolIndeterminate(6, 1, "unknown"),
      turnCompleted(7, 1),
    ]);
    const state = reduceSession(closedTurn, toolReconciled(8, 1, "succeeded", '{"ok":true}'));
    expect(snapshotOf(state, 1).status).toBe("SUCCEEDED");
  });

  test("reconciliation requires an ACTIVE session", () => {
    // INDETERMINATE is not an active execution, so the turn may close and the
    // session may pause with the outcome still unsettled (docs/02 section 17
    // step 7); reconciliation then waits for a resume.
    const paused = foldSessionEvents([
      sessionCreated(1),
      turnStarted(2, 1),
      toolProposed(3, 1),
      toolAuthorized(4, 1),
      toolStarted(5, 1),
      toolIndeterminate(6, 1, "unknown"),
      turnCompleted(7, 1),
      sessionPaused(8),
    ]);
    expect(() => reduceSession(paused, toolReconciled(9, 1))).toThrow(/requires status ACTIVE/u);
  });
});
