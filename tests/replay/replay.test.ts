import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import type { SessionEventUnion } from "@praxis/contracts";
import {
  asChallengeId,
  asHypothesisId,
  asObservationId,
  asPlanId,
  asToolExecutionId,
  parseReplayStream,
  SessionEventUnionSchema,
} from "@praxis/contracts";
import { foldSessionEvents, reduceSession } from "@praxis/core";
import fc from "fast-check";
import { describe, expect, test } from "vitest";
import { z } from "zod";
import { inMemoryEventStore } from "../helpers/in-memory-event-store";
import { commandArbitrary, translateCommands } from "../helpers/random-session-streams";
import { sessionCreated, TEST_SESSION_ID } from "../helpers/session-events";
import { buildRegressionLongSession } from "./regression-session-builder";

/**
 * Replay laws (ADR-0003 verification): historical fixtures stay loadable,
 * persisted streams fold identically on every read, and any checkpoint
 * state continued with the remaining suffix equals a single full fold.
 * Since M5-T003 every fixture loads through the versioned replay seam
 * (parseReplayStream: envelope-first, version-window fail-closed) and the
 * fixture manifest is the single home of the replay collection.
 */

const fixturePath = fileURLToPath(
  new URL("../fixtures/replay/session-lifecycle-v1.json", import.meta.url),
);
const loopFixturePath = fileURLToPath(
  new URL("../fixtures/replay/agent-loop-recovery-v1.json", import.meta.url),
);
const reconcileFixturePath = fileURLToPath(
  new URL("../fixtures/replay/tool-reconciliation-v1.json", import.meta.url),
);
const epistemicFixturePath = fileURLToPath(
  new URL("../fixtures/replay/epistemic-v1.json", import.meta.url),
);
const fixturesDir = fileURLToPath(new URL("../fixtures/replay/", import.meta.url));

function loadFixture(): SessionEventUnion[] {
  return parseReplayStream(JSON.parse(readFileSync(fixturePath, "utf8")));
}

function loadLoopFixture(): SessionEventUnion[] {
  return parseReplayStream(JSON.parse(readFileSync(loopFixturePath, "utf8")));
}

function loadReconcileFixture(): SessionEventUnion[] {
  return parseReplayStream(JSON.parse(readFileSync(reconcileFixturePath, "utf8")));
}

function loadEpistemicFixture(): SessionEventUnion[] {
  return parseReplayStream(JSON.parse(readFileSync(epistemicFixturePath, "utf8")));
}

describe("historical fixture replay", () => {
  test("the v1 fixture stream loads through the public schema and folds to its recorded terminal state", () => {
    const events = loadFixture();
    expect(events).toHaveLength(12);
    const state = foldSessionEvents(events);
    expect(state.status).toBe("COMPLETED");
    expect(state.headSeq).toBe(12);
    expect(state.sessionId?.valueOf()).toBe("session-fixture");
    expect(state.currentTurnId).toBeUndefined();
    expect([...state.turnIds].map((id) => id.valueOf())).toEqual(["turn-1", "turn-2", "turn-3"]);
  });

  test("folding the fixture twice yields identical states", () => {
    const events = loadFixture();
    expect(foldSessionEvents(events)).toEqual(foldSessionEvents(events));
  });
});

describe("agent-loop recovery fixture replay", () => {
  test("the crashed-and-recovered loop stream loads through the public schema", () => {
    const events = loadLoopFixture();
    expect(events).toHaveLength(28);
    const state = foldSessionEvents(events);
    expect(state.status).toBe("COMPLETED");
    expect(state.headSeq).toBe(28);
    expect(state.pendingModelRequest).toBeUndefined();
    expect(state.currentTurnId).toBeUndefined();
  });

  test("the mid-stream crash checkpoint folds to a recoverable dangling state", () => {
    const events = loadLoopFixture();
    // seq 17: ToolStarted appended, process crashed before a terminal event.
    const atCrash = foldSessionEvents(events.slice(0, 17));
    expect(atCrash.currentTurnId?.valueOf()).toBe("turn-2");
    const started = events[16];
    if (started?.type !== "ToolStarted") {
      throw new Error("fixture shape changed: seq 17 must be ToolStarted");
    }
    const dangling = atCrash.toolExecutions.get(started.payload.toolExecutionId);
    expect(dangling?.status).toBe("EXECUTING");
    // The pending model request checkpoint (seq 23) also stays recoverable.
    const atRequestCrash = foldSessionEvents(events.slice(0, 23));
    expect(atRequestCrash.pendingModelRequest).toEqual({ model: "fixture-model" });
  });

  test("folding the loop fixture twice yields identical states", () => {
    const events = loadLoopFixture();
    expect(foldSessionEvents(events)).toEqual(foldSessionEvents(events));
  });
});

describe("tool reconciliation fixture replay", () => {
  test("the reconciliation stream loads through the public schema and folds to its recorded state", () => {
    const events = loadReconcileFixture();
    expect(events).toHaveLength(18);
    const state = foldSessionEvents(events);
    expect(state.status).toBe("ACTIVE");
    expect(state.headSeq).toBe(18);
    expect(state.currentTurnId).toBeUndefined();

    const first = state.toolExecutions.get(asToolExecutionId("tool-exec-1"));
    expect(first?.status).toBe("SUCCEEDED");
    expect(first?.reconciliationCount).toBe(2);
    expect(first?.resultJson).toBe('{"invoiceId":"inv-1","status":"paid"}');

    const second = state.toolExecutions.get(asToolExecutionId("tool-exec-2"));
    expect(second?.status).toBe("FAILED");
    expect(second?.reconciliationCount).toBe(1);
    expect(second?.failureMessage).toBe("idempotency key inv-2 never seen by provider");
  });

  test("the pre-reconciliation checkpoint stays honestly INDETERMINATE, never auto-FAILED", () => {
    const events = loadReconcileFixture();
    // seq 8: ToolIndeterminate appended, reconciliation has not run yet.
    const atIndeterminate = foldSessionEvents(events.slice(0, 8));
    const dangling = atIndeterminate.toolExecutions.get(asToolExecutionId("tool-exec-1"));
    expect(dangling?.status).toBe("INDETERMINATE");
    expect(dangling?.reconciliationCount).toBe(0);
    // seq 9: first attempt stays unknown; only the second settles.
    const afterFirstAttempt = foldSessionEvents(events.slice(0, 9));
    const stillUnknown = afterFirstAttempt.toolExecutions.get(asToolExecutionId("tool-exec-1"));
    expect(stillUnknown?.status).toBe("INDETERMINATE");
    expect(stillUnknown?.reconciliationCount).toBe(1);
  });

  test("folding the reconciliation fixture twice yields identical states", () => {
    const events = loadReconcileFixture();
    expect(foldSessionEvents(events)).toEqual(foldSessionEvents(events));
  });
});

describe("epistemic fixture replay", () => {
  test("the epistemic stream loads through the public schema and folds to its recorded state", () => {
    const events = loadEpistemicFixture();
    expect(events).toHaveLength(23);
    const state = foldSessionEvents(events);
    expect(state.status).toBe("ACTIVE");
    expect(state.headSeq).toBe(23);
    expect(state.currentTurnId).toBeUndefined();

    expect(state.goal?.goal).toBe("restore the missing payment record");
    expect(state.observations.size).toBe(2);
    expect(state.observations.get(asObservationId("obs-1"))?.observedAt).toBe(3013);

    const hypothesis = state.hypotheses.get(asHypothesisId("hyp-1"));
    expect(hypothesis?.status).toBe("falsified");
    // support: proposed-with-evidence (seq 13) + supported-change evidence (seq 9).
    expect(hypothesis?.support).toHaveLength(2);
    expect(hypothesis?.conflicts).toHaveLength(1);

    expect(state.plans.get(asPlanId("plan-1"))?.status).toBe("superseded");
    expect(state.plans.get(asPlanId("plan-2"))?.status).toBe("invalidated");
    expect(state.activePlan).toBeUndefined();

    expect(state.challenges.get(asChallengeId("challenge-1"))?.status).toBe("rejected");
    expect(state.openChallenges).toHaveLength(0);
    expect(state.lastVerification?.outcome).toBe("inconclusive");
  });

  test("falsification is a fact, not an invalidation: the plan stays active until superseded", () => {
    const events = loadEpistemicFixture();
    // seq 20 falsifies hyp-1; the runtime (not the reducer) decides what
    // happens to plan-1 — here PlanSet at seq 21 supersedes it. The reducer
    // must not auto-invalidate on the fact alone (M4-T003 owns that policy).
    const afterFalsification = foldSessionEvents(events.slice(0, 20));
    expect(afterFalsification.hypotheses.get(asHypothesisId("hyp-1"))?.status).toBe("falsified");
    expect(afterFalsification.activePlan?.planId).toEqual(asPlanId("plan-1"));
    expect(afterFalsification.activePlan?.status).toBe("active");
    const afterReplan = reduceSession(
      afterFalsification,
      events[20] as Extract<SessionEventUnion, { type: "PlanSet" }>,
    );
    expect(afterReplan.plans.get(asPlanId("plan-1"))?.status).toBe("superseded");
    expect(afterReplan.activePlan?.planId).toEqual(asPlanId("plan-2"));
  });

  test("the mid-stream challenge checkpoint keeps the challenge open", () => {
    const events = loadEpistemicFixture();
    const atChallenge = foldSessionEvents(events.slice(0, 17));
    expect(atChallenge.openChallenges).toHaveLength(1);
    expect(atChallenge.openChallenges[0]?.claim).toBe("the plan trusts an unverified alias entry");
    const resolved = foldSessionEvents(events.slice(0, 18));
    expect(resolved.openChallenges).toHaveLength(0);
  });

  test("folding the epistemic fixture twice yields identical states", () => {
    const events = loadEpistemicFixture();
    expect(foldSessionEvents(events)).toEqual(foldSessionEvents(events));
  });
});

describe("fixture manifest law (M5-T003)", () => {
  const ManifestSchema = z.object({
    schema_version: z.literal(1),
    fixtures: z.array(
      z.object({
        file: z.string().min(1),
        schemaVersion: z.number().int().positive(),
        description: z.string().min(1),
        events: z.number().int().positive(),
        terminalStatus: z.enum(["ACTIVE", "PAUSED", "COMPLETED"]),
      }),
    ),
  });
  type Manifest = z.infer<typeof ManifestSchema>;

  function loadManifest(): Manifest {
    return ManifestSchema.parse(JSON.parse(readFileSync(`${fixturesDir}index.json`, "utf8")));
  }

  test("every manifest fixture loads through the versioned seam, folds to its recorded terminal status, and double-folds identically", () => {
    const manifest = loadManifest();
    expect(manifest.fixtures.length).toBeGreaterThanOrEqual(6);
    for (const entry of manifest.fixtures) {
      const events = parseReplayStream(
        JSON.parse(readFileSync(`${fixturesDir}${entry.file}`, "utf8")),
      );
      expect(events).toHaveLength(entry.events);
      const state = foldSessionEvents(events);
      expect(state.status).toBe(entry.terminalStatus);
      expect(state.headSeq).toBe(entry.events);
      expect(foldSessionEvents(events)).toEqual(state);
    }
  });

  test("the manifest and the fixture directory stay complete in both directions", () => {
    const manifest = loadManifest();
    const manifestFiles = manifest.fixtures.map((entry) => entry.file).sort();
    const directoryFiles = readdirSync(fixturesDir)
      .filter((name) => name.endsWith(".json") && name !== "index.json")
      .sort();
    expect(manifestFiles).toEqual(directoryFiles);
    expect(new Set(manifestFiles).size).toBe(manifestFiles.length);
  });

  test("the regression session regenerates identically from its deterministic builder", () => {
    const built = buildRegressionLongSession();
    const committed = readFileSync(`${fixturesDir}regression-long-session-v1.json`, "utf8");
    // The fixture file is biome-formatted on disk, so the pin compares
    // canonical JSON: any drift in any committed field breaks equality.
    expect(JSON.stringify(built)).toBe(JSON.stringify(JSON.parse(committed)));
    expect(buildRegressionLongSession()).toEqual(built);
    // Regenerated events are schema-valid and fold to the manifest state.
    const parsed = built.map((event) => SessionEventUnionSchema.parse(event));
    const state = foldSessionEvents(parsed);
    expect(state.status).toBe("COMPLETED");
    expect(state.goal?.goal).toBe("restore the quarterly ledger");
    expect(state.toolExecutions.size).toBe(43);
    expect(state.observations.size).toBe(12);
    expect(state.hypotheses.size).toBe(7);
    expect(state.plans.size).toBe(5);
    expect(state.openChallenges).toHaveLength(0);
    expect(state.lastVerification?.outcome).toBe("passed");
  });
});

describe("replay properties", () => {
  test("a persisted stream read twice through the EventStore port folds identically", () => {
    fc.assert(
      fc.asyncProperty(fc.array(commandArbitrary, { maxLength: 40 }), async (commands) => {
        const events = translateCommands(commands);
        const store = inMemoryEventStore();
        await store.append(events, 0);
        const first = await store.readStream(TEST_SESSION_ID);
        const second = await store.readStream(TEST_SESSION_ID);
        expect(foldSessionEvents(first)).toEqual(foldSessionEvents(second));
        expect(first).toEqual(events);
      }),
    );
  });

  test("any checkpoint state continued with the suffix equals a single full fold", () => {
    fc.assert(
      fc.property(
        fc.array(commandArbitrary, { minLength: 1, maxLength: 40 }),
        fc.nat(),
        (commands, index) => {
          const events = translateCommands(commands);
          const cut = index % events.length;
          let checkpoint = foldSessionEvents(events.slice(0, cut));
          for (const event of events.slice(cut)) {
            checkpoint = reduceSession(checkpoint, event);
          }
          expect(checkpoint).toEqual(foldSessionEvents(events));
        },
      ),
    );
  });

  test("replaying the whole stream from the initial state recovers every intermediate state", () => {
    fc.assert(
      fc.property(fc.array(commandArbitrary, { maxLength: 40 }), (commands) => {
        const events = translateCommands(commands);
        const live = [foldSessionEvents(events.slice(0, 1))];
        for (const event of events.slice(1)) {
          live.push(reduceSession(live.at(-1) ?? foldSessionEvents([]), event));
        }
        const replayed = [foldSessionEvents(events.slice(0, 1))];
        for (let cut = 2; cut <= events.length; cut += 1) {
          replayed.push(foldSessionEvents(events.slice(0, cut)));
        }
        expect(replayed).toEqual(live);
      }),
    );
  });

  test("a single-event stream still round-trips through the port", async () => {
    const store = inMemoryEventStore();
    await store.append([sessionCreated(1)], 0);
    const stream = await store.readStream(TEST_SESSION_ID);
    expect(stream).toHaveLength(1);
    expect(foldSessionEvents(stream).status).toBe("ACTIVE");
  });
});
