import type { SessionEventUnion } from "@praxis/contracts";
import type { DerivedSessionState } from "@praxis/core";
import {
  buildContext,
  DEFAULT_CONTEXT_BUDGET,
  foldSessionEvents,
  projectConversation,
  projectEpistemicBrief,
} from "@praxis/core";
import { describe, expect, test } from "vitest";
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
  sessionCreated,
  toolAuthorized,
  toolFailed,
  toolProposed,
  toolRejected,
  toolStarted,
  toolSucceeded,
  turnCompleted,
  turnStarted,
  verificationRecorded,
} from "../helpers/session-events";

/**
 * 10k-turn soak (docs/03 M7, backlog M7-T003): the largest prior synthetic
 * session was 1000 turns of bare TurnStarted/Completed pairs. This suite
 * pushes a 10,000-turn session of the FULL working vocabulary through the
 * real reducer and context builder and proves the docs/02 §12 law at scale:
 * the model context is bounded working state (every DEFAULT_CONTEXT_BUDGET
 * cap holds at every checkpoint, recap accounting stays exact), while the
 * derived-state registries grow EXACTLY linearly with the emitted durable
 * facts. The stream is deterministic modular-arithmetic traffic — no RNG,
 * every expected count below is closed-form.
 */

const TURNS = 10_000;
const CHECKPOINTS = [2_000, 4_000, 6_000, 8_000, 10_000] as const;

type SoakCounts = {
  turns: number;
  toolExecutions: number;
  observations: number;
  hypotheses: number;
  plans: number;
  challenges: number;
  verifications: number;
};

/** Closed-form expected registry sizes after the first N turns. */
function expectedCounts(n: number): SoakCounts {
  return {
    turns: n,
    toolExecutions: Math.floor(n / 3) + Math.floor(n / 25) - Math.floor(n / 75),
    observations: Math.floor(n / 7),
    hypotheses: Math.floor(n / 11),
    plans: Math.floor(n / 13),
    challenges: Math.floor(n / 17),
    verifications: Math.floor(n / 23),
  };
}

type SoakStream = {
  readonly events: readonly SessionEventUnion[];
  /** events.length after turn n (inclusive of its between-turn epistemics) */
  readonly lengthsAt: ReadonlyMap<number, number>;
};

let cachedStream: SoakStream | undefined;

function soakStream(): SoakStream {
  if (cachedStream !== undefined) {
    return cachedStream;
  }
  const events: SessionEventUnion[] = [];
  const lengthsAt = new Map<number, number>();
  let seq = 0;
  const next = (): number => {
    seq += 1;
    return seq;
  };
  events.push(
    sessionCreated(next()),
    goalSet(next(), { goal: "restore the missing payment record" }),
  );
  let execution = 0;
  let observation = 0;
  let hypothesis = 0;
  let plan = 0;
  let challenge = 0;
  for (let n = 1; n <= TURNS; n += 1) {
    events.push(turnStarted(next(), n, `soak step ${n} of the long restoration`));
    events.push(modelRequestStarted(next(), "soak-model"));
    const toolTurn = n % 3 === 0 || n % 25 === 0;
    events.push(
      modelResponseCompleted(next(), {
        text: `step ${n}: the record trail continues`,
        ...(toolTurn
          ? {
              toolCalls: [
                { id: `call-${n}`, name: "read_file", argumentsJson: '{"path":"note.txt"}' },
              ],
            }
          : {}),
      }),
    );
    if (n % 25 === 0) {
      execution += 1;
      events.push(toolProposed(next(), execution));
      events.push(toolRejected(next(), execution, `not permitted at step ${n}`));
    } else if (n % 3 === 0) {
      execution += 1;
      events.push(toolProposed(next(), execution));
      events.push(toolAuthorized(next(), execution));
      events.push(toolStarted(next(), execution));
      if (n % 10 === 0) {
        events.push(toolFailed(next(), execution, `io error at step ${n}`));
      } else {
        events.push(toolSucceeded(next(), execution));
      }
    }
    events.push(turnCompleted(next(), n));
    if (n % 7 === 0) {
      observation += 1;
      events.push(
        observationRecorded(next(), observation, { claim: `observation ${n}: the trail advanced` }),
      );
    }
    if (n % 11 === 0) {
      hypothesis += 1;
      events.push(hypothesisProposed(next(), hypothesis));
      events.push(hypothesisStatusChanged(next(), hypothesis, "supported"));
    }
    if (n % 13 === 0) {
      plan += 1;
      events.push(planSet(next(), plan, { nextAction: `continue from step ${n}` }));
    }
    if (n % 17 === 0) {
      challenge += 1;
      const latestPlan = Math.floor(n / 13);
      events.push(
        challengeRaised(next(), challenge, {
          target: `plan-${latestPlan}`,
          claim: `step ${n} doubt`,
        }),
      );
      events.push(challengeResolved(next(), challenge));
    }
    if (n % 23 === 0) {
      events.push(verificationRecorded(next(), { summary: `step ${n} check ran` }));
    }
    lengthsAt.set(n, events.length);
  }
  cachedStream = { events, lengthsAt };
  return cachedStream;
}

type Checkpoint = {
  readonly turns: number;
  readonly events: readonly SessionEventUnion[];
  readonly state: DerivedSessionState;
  readonly foldMs: number;
};

let cachedCheckpoints: readonly Checkpoint[] | undefined;

function checkpoints(): readonly Checkpoint[] {
  if (cachedCheckpoints !== undefined) {
    return cachedCheckpoints;
  }
  const { events, lengthsAt } = soakStream();
  cachedCheckpoints = CHECKPOINTS.map((turns) => {
    const prefix = events.slice(0, lengthsAt.get(turns) ?? 0);
    const started = performance.now();
    const state = foldSessionEvents(prefix);
    return { turns, events: prefix, state, foldMs: performance.now() - started };
  });
  return cachedCheckpoints;
}

describe("10k-turn synthetic soak", () => {
  test("the full-vocabulary stream folds legally at every checkpoint", () => {
    const { events, lengthsAt } = soakStream();
    for (const checkpoint of checkpoints()) {
      const expectedLength = lengthsAt.get(checkpoint.turns);
      if (expectedLength === undefined) {
        throw new Error(`missing length for checkpoint ${checkpoint.turns}`);
      }
      expect(checkpoint.state.headSeq).toBe(expectedLength);
      expect(checkpoint.state.status).toBe("ACTIVE");
      expect(checkpoint.state.currentTurnId).toBeUndefined();
      expect(checkpoint.state.pendingModelRequest).toBeUndefined();
      expect(checkpoint.state.openChallenges).toEqual([]);
    }
    console.info(
      `soak: ${TURNS} turns, ${events.length} events, checkpoints fold in ` +
        `${checkpoints()
          .map((c) => `${c.turns}@${c.foldMs.toFixed(0)}ms`)
          .join(", ")}`,
    );
  }, 120_000);

  test("the model context stays inside every budget cap at every checkpoint", () => {
    for (const checkpoint of checkpoints()) {
      const history = projectConversation(checkpoint.events);
      const brief = projectEpistemicBrief(checkpoint.state, DEFAULT_CONTEXT_BUDGET);
      const built = buildContext(
        {
          systemPrompt: "soak harness",
          history,
          ...(brief === undefined ? {} : { epistemicBrief: brief }),
        },
        DEFAULT_CONTEXT_BUDGET,
      );
      expect(built.messages.length).toBeLessThanOrEqual(
        1 + DEFAULT_CONTEXT_BUDGET.maxRecentMessages,
      );
      expect(built.estimate.estimatedTokens).toBeLessThanOrEqual(
        DEFAULT_CONTEXT_BUDGET.maxEstimatedTokens,
      );
      // Honest recap accounting: conversation messages are either kept in
      // the window or counted as dropped — nothing silently vanishes.
      const kept = built.messages.length - 1;
      expect(kept + built.estimate.droppedMessages).toBe(history.length);
    }
  }, 60_000);

  test("derived-state registries grow exactly linearly with emitted facts", () => {
    for (const checkpoint of checkpoints()) {
      const expected = expectedCounts(checkpoint.turns);
      expect(checkpoint.state.turnIds.size).toBe(expected.turns);
      expect(checkpoint.state.toolExecutions.size).toBe(expected.toolExecutions);
      expect(checkpoint.state.observations.size).toBe(expected.observations);
      expect(checkpoint.state.hypotheses.size).toBe(expected.hypotheses);
      expect(checkpoint.state.plans.size).toBe(expected.plans);
      expect(checkpoint.state.challenges.size).toBe(expected.challenges);
      // Exactly one active plan at every scale; the supersede-on-set law
      // keeps the working set flat while the registry grows linearly.
      expect(checkpoint.state.activePlan).toBeDefined();
    }
    const final = checkpoints()[checkpoints().length - 1];
    if (final === undefined) {
      throw new Error("expected a final checkpoint");
    }
    const expected = expectedCounts(TURNS);
    const analysis = {
      turns: expected.turns,
      toolExecutions: expected.toolExecutions,
      observations: expected.observations,
      hypotheses: expected.hypotheses,
      plans: expected.plans,
      challenges: expected.challenges,
      verifications: expected.verifications,
      contextMessages: 1 + DEFAULT_CONTEXT_BUDGET.maxRecentMessages,
    };
    console.info(`soak bounded-growth analysis: ${JSON.stringify(analysis)}`);
    expect(final.state.turnIds.size).toBe(expected.turns);
  }, 60_000);

  test("per-event fold cost grows slowly enough across checkpoints (tripwire)", () => {
    const folds = checkpoints();
    const first = folds[0];
    const last = folds[folds.length - 1];
    if (first === undefined || last === undefined) {
      throw new Error("expected at least two checkpoints");
    }
    // Structural linear counts carry the real proof; this timing guard is
    // only a tripwire against accidental superlinear folding, in per-event
    // terms: registry copies already cost ~4x per event at 10k turns
    // (immutable Map copy per registry insert), a true quadratic blowup at
    // 5x data would land around 25x — the line sits between them.
    const perEventFirst = first.foldMs / first.events.length;
    const perEventLast = last.foldMs / last.events.length;
    expect(perEventLast).toBeLessThan(perEventFirst * 10);
  }, 60_000);
});
