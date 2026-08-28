import { foldSessionEvents, IllegalTransitionError } from "@praxis/core";
import fc from "fast-check";
import { expect, test } from "vitest";
import {
  commandArbitrary,
  replayModel,
  translateCommands,
} from "../helpers/random-session-streams";

test("reducer agrees with an independent model of the transition table", () => {
  fc.assert(
    fc.property(fc.array(commandArbitrary, { maxLength: 40 }), (commands) => {
      const events = translateCommands(commands);
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
      const events = translateCommands(commands);
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
        const events = translateCommands(commands);
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
        const events = translateCommands(commands);
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
