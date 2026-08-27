import { asSessionId } from "@praxis/contracts";
import {
  foldSessionEvents,
  IllegalTransitionError,
  initialSessionState,
  reduceSession,
} from "@praxis/core";
import { describe, expect, test } from "vitest";
import {
  sessionCompleted,
  sessionCreated,
  sessionPaused,
  sessionResumed,
  turnCompleted,
  turnStarted,
} from "./helpers/session-events";

describe("initial state", () => {
  test("starts empty with headSeq 0 and no session identity", () => {
    const state = initialSessionState();
    expect(state.status).toBe("EMPTY");
    expect(state.headSeq).toBe(0);
    expect(state.sessionId).toBeUndefined();
    expect(state.currentTurnId).toBeUndefined();
    expect(state.turnIds.size).toBe(0);
  });
});

describe("legal lifecycle", () => {
  test("full lifecycle with two turns and a pause/resume cycle", () => {
    const state = foldSessionEvents([
      sessionCreated(1, "user request"),
      turnStarted(2, 1),
      turnCompleted(3, 1),
      sessionPaused(4),
      sessionResumed(5),
      turnStarted(6, 2),
      turnCompleted(7, 2),
      sessionCompleted(8),
    ]);
    expect(state.status).toBe("COMPLETED");
    expect(state.headSeq).toBe(8);
    expect(state.currentTurnId).toBeUndefined();
    expect(state.sessionId?.valueOf()).toBe("session-test");
    expect([...state.turnIds].map((id) => id.valueOf())).toEqual(["turn-1", "turn-2"]);
  });

  test("currentTurnId tracks the open turn", () => {
    const state = foldSessionEvents([sessionCreated(1), turnStarted(2, 7)]);
    expect(state.currentTurnId?.valueOf()).toBe("turn-7");
    expect(state.status).toBe("ACTIVE");
  });

  test("session id is bound by SessionCreated", () => {
    const state = foldSessionEvents([sessionCreated(1)]);
    expect(state.sessionId?.valueOf()).toBe("session-test");
    expect(state.status).toBe("ACTIVE");
  });
});

describe("illegal first events", () => {
  test.each([
    ["SessionResumed", sessionResumed(1)],
    ["SessionPaused", sessionPaused(1)],
    ["SessionCompleted", sessionCompleted(1)],
    ["TurnStarted", turnStarted(1, 1)],
    ["TurnCompleted", turnCompleted(1, 1)],
  ])("%s on an EMPTY stream is rejected", (_label, event) => {
    expect(() => reduceSession(initialSessionState(), event)).toThrow(IllegalTransitionError);
  });
});

describe("illegal session transitions", () => {
  test("duplicate SessionCreated", () => {
    const state = foldSessionEvents([sessionCreated(1)]);
    expect(() => reduceSession(state, sessionCreated(2))).toThrow(/session already created/);
  });

  test("resume an ACTIVE session", () => {
    const state = foldSessionEvents([sessionCreated(1)]);
    expect(() => reduceSession(state, sessionResumed(2))).toThrow(/requires status PAUSED/);
  });

  test("resume a COMPLETED session", () => {
    const state = foldSessionEvents([sessionCreated(1), sessionCompleted(2)]);
    expect(() => reduceSession(state, sessionResumed(3))).toThrow(IllegalTransitionError);
  });

  test("pause with an open turn", () => {
    const state = foldSessionEvents([sessionCreated(1), turnStarted(2, 1)]);
    expect(() => reduceSession(state, sessionPaused(3))).toThrow(/still open/);
  });

  test("complete with an open turn", () => {
    const state = foldSessionEvents([sessionCreated(1), turnStarted(2, 1)]);
    expect(() => reduceSession(state, sessionCompleted(3))).toThrow(/still open/);
  });

  test("pause a PAUSED session", () => {
    const state = foldSessionEvents([sessionCreated(1), sessionPaused(2)]);
    expect(() => reduceSession(state, sessionPaused(3))).toThrow(IllegalTransitionError);
  });
});

describe("illegal turn transitions", () => {
  test("start a turn while another is open", () => {
    const state = foldSessionEvents([sessionCreated(1), turnStarted(2, 1)]);
    expect(() => reduceSession(state, turnStarted(3, 2))).toThrow(/still open/);
  });

  test("reuse a completed turn id", () => {
    const state = foldSessionEvents([sessionCreated(1), turnStarted(2, 1), turnCompleted(3, 1)]);
    expect(() => reduceSession(state, turnStarted(4, 1))).toThrow(/already used/);
  });

  test("start a turn on a PAUSED session", () => {
    const state = foldSessionEvents([sessionCreated(1), sessionPaused(2)]);
    expect(() => reduceSession(state, turnStarted(3, 1))).toThrow(/requires status ACTIVE/);
  });

  test("complete a foreign turn id", () => {
    const state = foldSessionEvents([sessionCreated(1), turnStarted(2, 1)]);
    expect(() => reduceSession(state, turnCompleted(3, 2))).toThrow(/event completes/);
  });

  test("complete a turn with none open", () => {
    const state = foldSessionEvents([sessionCreated(1)]);
    expect(() => reduceSession(state, turnCompleted(2, 1))).toThrow(/no open turn/);
  });
});

describe("stream continuity", () => {
  test("gap in seq is rejected", () => {
    const state = foldSessionEvents([sessionCreated(1)]);
    expect(() => reduceSession(state, sessionPaused(3))).toThrow(/expected seq 2, got 3/);
  });

  test("replayed old seq is rejected", () => {
    const state = foldSessionEvents([sessionCreated(1)]);
    expect(() => reduceSession(state, sessionCreated(1))).toThrow(/expected seq 2, got 1/);
  });

  test("event from another session is rejected", () => {
    const state = foldSessionEvents([sessionCreated(1)]);
    const foreign = {
      ...sessionPaused(2),
      sessionId: asSessionId("session-other"),
    };
    expect(() => reduceSession(state, foreign)).toThrow(/belongs to session/);
  });
});

describe("purity", () => {
  test("reduce does not mutate the input state", () => {
    const before = foldSessionEvents([sessionCreated(1), turnStarted(2, 1)]);
    const snapshot = {
      status: before.status,
      headSeq: before.headSeq,
      currentTurnId: before.currentTurnId,
      turnIds: [...before.turnIds],
    };
    const after = reduceSession(before, turnCompleted(3, 1));
    expect(after.currentTurnId).toBeUndefined();
    // If that reduce had mutated `before` (cleared its open turn), this
    // TurnStarted would succeed instead of being rejected.
    expect(() => reduceSession(before, turnStarted(3, 2))).toThrow(/still open/);
    expect(before.status).toBe(snapshot.status);
    expect(before.headSeq).toBe(snapshot.headSeq);
    expect(before.currentTurnId).toBe(snapshot.currentTurnId);
    expect([...before.turnIds]).toEqual(snapshot.turnIds);
  });

  test("folding the same events twice yields identical states", () => {
    const events = [sessionCreated(1), turnStarted(2, 1), turnCompleted(3, 1), sessionPaused(4)];
    expect(foldSessionEvents(events)).toEqual(foldSessionEvents(events));
  });
});
