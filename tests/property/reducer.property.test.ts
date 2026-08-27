import type { SessionEventUnion } from "@praxis/contracts";
import { foldSessionEvents, IllegalTransitionError } from "@praxis/core";
import fc from "fast-check";
import { expect, test } from "vitest";
import {
  sessionCompleted,
  sessionCreated,
  sessionPaused,
  sessionResumed,
  turnCompleted,
  turnStarted,
} from "../helpers/session-events";

type ShadowStatus = "ACTIVE" | "PAUSED" | "COMPLETED";

type ShadowModel = {
  status: ShadowStatus;
  openTurn: number | null;
  usedTurns: Set<number>;
};

type Command =
  | { kind: "startTurn"; turn: number }
  | { kind: "completeTurn" }
  | { kind: "pause" }
  | { kind: "resume" }
  | { kind: "completeSession" };

const commandArbitrary: fc.Arbitrary<Command> = fc.oneof(
  fc.record({ kind: fc.constant("startTurn"), turn: fc.nat() }),
  fc.constant({ kind: "completeTurn" } as const),
  fc.constant({ kind: "pause" } as const),
  fc.constant({ kind: "resume" } as const),
  fc.constant({ kind: "completeSession" } as const),
);

/**
 * Translate arbitrary commands into a legal event stream by filtering them
 * through a shadow model of the documented transition table. Illegal
 * commands are skipped, so any surviving stream must fold cleanly.
 */
function translate(commands: readonly Command[]): SessionEventUnion[] {
  const events: SessionEventUnion[] = [sessionCreated(1)];
  const model: ShadowModel = {
    status: "ACTIVE",
    openTurn: null,
    usedTurns: new Set<number>(),
  };
  const push = (event: SessionEventUnion) => {
    events.push(event);
  };
  for (const command of commands) {
    const seq = events.length + 1;
    switch (command.kind) {
      case "startTurn":
        if (
          model.status === "ACTIVE" &&
          model.openTurn === null &&
          !model.usedTurns.has(command.turn)
        ) {
          push(turnStarted(seq, command.turn));
          model.openTurn = command.turn;
          model.usedTurns.add(command.turn);
        }
        break;
      case "completeTurn":
        if (model.openTurn !== null) {
          push(turnCompleted(seq, model.openTurn));
          model.openTurn = null;
        }
        break;
      case "pause":
        if (model.status === "ACTIVE" && model.openTurn === null) {
          push(sessionPaused(seq));
          model.status = "PAUSED";
        }
        break;
      case "resume":
        if (model.status === "PAUSED") {
          push(sessionResumed(seq));
          model.status = "ACTIVE";
        }
        break;
      case "completeSession":
        if (model.status === "ACTIVE" && model.openTurn === null) {
          push(sessionCompleted(seq));
          model.status = "COMPLETED";
        }
        break;
    }
  }
  return events;
}

/** Re-derive the expected terminal model without building events. */
function replayModel(commands: readonly Command[]): ShadowModel {
  const model: ShadowModel = {
    status: "ACTIVE",
    openTurn: null,
    usedTurns: new Set<number>(),
  };
  for (const command of commands) {
    switch (command.kind) {
      case "startTurn":
        if (
          model.status === "ACTIVE" &&
          model.openTurn === null &&
          !model.usedTurns.has(command.turn)
        ) {
          model.openTurn = command.turn;
          model.usedTurns.add(command.turn);
        }
        break;
      case "completeTurn":
        model.openTurn = null;
        break;
      case "pause":
        if (model.status === "ACTIVE" && model.openTurn === null) {
          model.status = "PAUSED";
        }
        break;
      case "resume":
        if (model.status === "PAUSED") {
          model.status = "ACTIVE";
        }
        break;
      case "completeSession":
        if (model.status === "ACTIVE" && model.openTurn === null) {
          model.status = "COMPLETED";
        }
        break;
    }
  }
  return model;
}

test("reducer agrees with an independent model of the transition table", () => {
  fc.assert(
    fc.property(fc.array(commandArbitrary, { maxLength: 40 }), (commands) => {
      const events = translate(commands);
      const state = foldSessionEvents(events);
      const model = replayModel(commands);
      expect(state.status).toBe(model.status);
      expect(state.headSeq).toBe(events.length);
      expect(state.currentTurnId?.valueOf() ?? null).toBe(
        model.openTurn === null ? null : `turn-${model.openTurn}`,
      );
      expect(state.turnIds.size).toBe(model.usedTurns.size);
    }),
  );
});

test("folding is deterministic and independent of prior folds", () => {
  fc.assert(
    fc.property(fc.array(commandArbitrary, { maxLength: 40 }), (commands) => {
      const events = translate(commands);
      expect(foldSessionEvents(events)).toEqual(foldSessionEvents(events));
    }),
  );
});

test("any single-seq perturbation of a valid stream is rejected", () => {
  fc.assert(
    fc.property(
      fc.array(commandArbitrary, { minLength: 1, maxLength: 40 }),
      fc.nat(),
      (commands, index) => {
        const events = translate(commands);
        const target = index % events.length;
        const corrupted = events.map((event, position) =>
          position === target ? { ...event, seq: event.seq + 1 } : event,
        );
        expect(() => foldSessionEvents(corrupted)).toThrow(IllegalTransitionError);
      },
    ),
  );
});

test("any non-identity adjacent swap of a valid stream is rejected", () => {
  fc.assert(
    fc.property(
      fc.array(commandArbitrary, { minLength: 2, maxLength: 40 }),
      fc.nat(),
      (commands, index) => {
        const events = translate(commands);
        if (events.length < 2) {
          return;
        }
        const target = index % (events.length - 1);
        const swapped = [...events];
        const left = swapped[target];
        const right = swapped[target + 1];
        if (left === undefined || right === undefined || left.type === right.type) {
          return;
        }
        swapped[target] = right;
        swapped[target + 1] = left;
        expect(() => foldSessionEvents(swapped)).toThrow(IllegalTransitionError);
      },
    ),
  );
});
