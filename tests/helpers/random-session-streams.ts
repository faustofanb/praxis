import type { SessionEventUnion } from "@praxis/contracts";
import fc from "fast-check";
import {
  sessionCompleted,
  sessionCreated,
  sessionPaused,
  sessionResumed,
  turnCompleted,
  turnStarted,
} from "./session-events";

/**
 * Shared generator for legal v1 Session/Turn event streams: arbitrary
 * commands filtered through a shadow model of the documented transition
 * table, so every surviving stream must fold cleanly. Used by the reducer
 * properties, the replay properties, and the store parity suite.
 */

type ShadowStatus = "ACTIVE" | "PAUSED" | "COMPLETED";

export type ShadowModel = {
  status: ShadowStatus;
  openTurn: number | null;
  usedTurns: Set<number>;
};

export type Command =
  | { kind: "startTurn"; turn: number }
  | { kind: "completeTurn" }
  | { kind: "pause" }
  | { kind: "resume" }
  | { kind: "completeSession" };

export const commandArbitrary: fc.Arbitrary<Command> = fc.oneof(
  fc.record({ kind: fc.constant("startTurn"), turn: fc.nat() }),
  fc.constant({ kind: "completeTurn" } as const),
  fc.constant({ kind: "pause" } as const),
  fc.constant({ kind: "resume" } as const),
  fc.constant({ kind: "completeSession" } as const),
);

function applyCommand(model: ShadowModel, command: Command): void {
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

export function translateCommands(commands: readonly Command[]): SessionEventUnion[] {
  const events: SessionEventUnion[] = [sessionCreated(1)];
  const model: ShadowModel = {
    status: "ACTIVE",
    openTurn: null,
    usedTurns: new Set<number>(),
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
          events.push(turnStarted(seq, command.turn));
        }
        break;
      case "completeTurn":
        if (model.openTurn !== null) {
          events.push(turnCompleted(seq, model.openTurn));
        }
        break;
      case "pause":
        if (model.status === "ACTIVE" && model.openTurn === null) {
          events.push(sessionPaused(seq));
        }
        break;
      case "resume":
        if (model.status === "PAUSED") {
          events.push(sessionResumed(seq));
        }
        break;
      case "completeSession":
        if (model.status === "ACTIVE" && model.openTurn === null) {
          events.push(sessionCompleted(seq));
        }
        break;
    }
    applyCommand(model, command);
  }
  return events;
}

/** Re-derive the expected terminal model without building events. */
export function replayModel(commands: readonly Command[]): ShadowModel {
  const model: ShadowModel = {
    status: "ACTIVE",
    openTurn: null,
    usedTurns: new Set<number>(),
  };
  for (const command of commands) {
    applyCommand(model, command);
  }
  return model;
}
