import type { SessionEventUnion } from "@praxis/contracts";
import { asEventId } from "@praxis/contracts";
import {
  challengeRaised,
  challengeResolved,
  goalSet,
  hypothesisProposed,
  hypothesisStatusChanged,
  modelRequestStarted,
  modelResponseCompleted,
  observationRecorded,
  planSet,
  sessionCompleted,
  sessionCreated,
  toolAuthorized,
  toolFailed,
  toolIndeterminate,
  toolProposed,
  toolReconciled,
  toolStarted,
  toolSucceeded,
  turnCompleted,
  turnStarted,
  verificationRecorded,
} from "../helpers/session-events";

/**
 * Deterministic builder for the regression session collection
 * (tests/fixtures/replay/regression-long-session-v1.json, M5-T003).
 * Everything derives from the turn number through fixed testkit factories —
 * no clock, randomness, or environment. The factories stamp event identity
 * from a per-process call counter, so the builder normalizes every event to
 * seq-derived identity (`event-${seq}`, occurredAt = seq): the output is
 * call-order independent, and rebuilding must reproduce the committed
 * fixture (pinned canonically by tests/replay/replay.test.ts).
 *
 * Shape: 50 completed turns over one goal; read-only tool calls on every
 * turn except text-only turns (turn % 7 === 0); failures every 10th,
 * indeterminate-then-reconciled every 5th, plain successes otherwise;
 * epistemic facts land between turns (observations every 4th, hypotheses
 * every 7th offset by 3, plans every 9th, one raised-and-resolved plan
 * challenge, one falsified hypothesis); the session closes with a passing
 * verification and SessionCompleted.
 */

export function buildRegressionLongSession(): SessionEventUnion[] {
  const events: SessionEventUnion[] = [];
  const seq = (): number => events.length + 1;
  const push = (event: SessionEventUnion): void => {
    const at = seq();
    events.push({ ...event, id: asEventId(`event-${String(at)}`), occurredAt: at });
  };

  push(sessionCreated(seq(), "regression collection"));
  push(
    goalSet(seq(), {
      goal: "restore the quarterly ledger",
      constraints: ["never write without a matching invoice", "keep every tool effect reconciled"],
    }),
  );

  let execution = 0;
  let observation = 0;
  let hypothesis = 0;
  let plan = 0;

  for (let turn = 1; turn <= 50; turn += 1) {
    push(turnStarted(seq(), turn, `step ${turn} of the ledger restoration`));
    if (turn % 7 !== 0) {
      execution += 1;
      const callId = `call-${String(execution)}`;
      const argumentsJson = JSON.stringify({ path: `entry-${String(turn)}.json` });
      push(modelRequestStarted(seq(), "regression-model"));
      push(
        modelResponseCompleted(seq(), {
          toolCalls: [{ id: callId, name: "read_file", argumentsJson }],
        }),
      );
      push(
        toolProposed(seq(), execution, {
          name: "read_file",
          argumentsJson,
          effect: "read_only",
          toolCallId: callId,
        }),
      );
      push(toolAuthorized(seq(), execution));
      push(toolStarted(seq(), execution));
      if (turn % 10 === 0) {
        push(toolFailed(seq(), execution, `entry ${String(turn)} unreadable`));
      } else if (turn % 5 === 0) {
        push(toolIndeterminate(seq(), execution, "process died mid-read"));
        push(
          toolReconciled(
            seq(),
            execution,
            "succeeded",
            `{"content":"entry-${String(turn)} recovered"}`,
          ),
        );
      } else {
        push(toolSucceeded(seq(), execution, `{"content":"entry-${String(turn)} ok"}`));
      }
    }
    push(modelRequestStarted(seq(), "regression-model"));
    push(modelResponseCompleted(seq(), { text: `step ${String(turn)} done` }));
    push(turnCompleted(seq(), turn));

    if (turn % 4 === 0) {
      observation += 1;
      push(
        observationRecorded(seq(), observation, {
          claim: `ledger entry ${String(turn)} has a matching invoice`,
        }),
      );
    }
    if (turn % 7 === 3) {
      hypothesis += 1;
      push(
        hypothesisProposed(seq(), hypothesis, {
          statement: `entry ${String(turn)} was dropped by the importer`,
        }),
      );
    }
    if (turn === 21) {
      push(
        hypothesisStatusChanged(seq(), 1, "falsified", { reason: "importer log shows no drop" }),
      );
    }
    if (turn % 9 === 0) {
      plan += 1;
      push(planSet(seq(), plan, { nextAction: `replay importer for entry ${String(turn)}` }));
    }
    if (turn === 30) {
      push(
        challengeRaised(seq(), 1, {
          targetType: "plan",
          target: `plan-${String(plan)}`,
          claim: "the replay assumes the importer is idempotent",
        }),
      );
    }
    if (turn === 33) {
      push(challengeResolved(seq(), 1, "resolved", "importer deduplicates by invoice id"));
    }
  }

  push(
    verificationRecorded(seq(), {
      outcome: "passed",
      summary: "all 50 ledger entries reconciled",
    }),
  );
  push(sessionCompleted(seq()));
  return events;
}
