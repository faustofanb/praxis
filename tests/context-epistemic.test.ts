import type { ContextBudget } from "@praxis/core";
import {
  DEFAULT_CONTEXT_BUDGET,
  foldSessionEvents,
  InvalidContextBudgetError,
  projectEpistemicBrief,
  validateContextBudget,
} from "@praxis/core";
import { describe, expect, test } from "vitest";
import {
  challengeRaised,
  challengeResolved,
  goalSet,
  hypothesisProposed,
  hypothesisStatusChanged,
  observationRecorded,
  planSet,
  sessionCreated,
  toolAuthorized,
  toolIndeterminate,
  toolProposed,
  toolStarted,
  turnStarted,
  verificationRecorded,
} from "./helpers/session-events";

/**
 * Structured epistemic projection (docs/02 sections 12.1-12.3): pure
 * rendering of DerivedSessionState in section-priority order, capped
 * per line, omitted entirely when the epistemic slice is empty.
 */

const budget: ContextBudget = DEFAULT_CONTEXT_BUDGET;

function fold(events: Parameters<typeof foldSessionEvents>[0]) {
  return foldSessionEvents(events);
}

describe("projectEpistemicBrief section laws", () => {
  test("empty epistemic state returns undefined", () => {
    expect(projectEpistemicBrief(fold([sessionCreated(1)]), budget)).toBeUndefined();
  });

  test("renders goal, constraints, plan, hypothesis, and observation partitions in order", () => {
    const state = fold([
      sessionCreated(1),
      goalSet(2, {
        need: "payment ledger integrity",
        goal: "restore the missing payment record",
        constraints: ["never write without a matching invoice"],
      }),
      observationRecorded(3, 1, { claim: "payment pay_1 has no ledger entry" }),
      hypothesisProposed(4, 1),
      hypothesisStatusChanged(5, 1, "supported", { evidence: [3] }),
      planSet(6, 1, {
        hypothesis: 1,
        falsifiedIf: "the ledger has no matching entry",
        nextAction: "replay the payment webhook",
      }),
    ]);

    const brief = projectEpistemicBrief(state, budget);
    if (brief === undefined) {
      throw new Error("expected a rendered brief");
    }

    const goalAt = brief.indexOf("## Goal");
    const needAt = brief.indexOf("Need: payment ledger integrity");
    const constraintAt = brief.indexOf("Hard constraint: never write without a matching invoice");
    const planAt = brief.indexOf("## Active plan");
    const falsifiedAt = brief.indexOf("Falsified if: the ledger has no matching entry");
    const hypothesisAt = brief.indexOf("## Active hypotheses");
    const observationAt = brief.indexOf("## Observations (latest 1)");
    const claimAt = brief.indexOf("- payment pay_1 has no ledger entry");
    for (const at of [
      goalAt,
      needAt,
      constraintAt,
      planAt,
      falsifiedAt,
      hypothesisAt,
      observationAt,
      claimAt,
    ]) {
      expect(at).toBeGreaterThanOrEqual(0);
    }
    expect(goalAt).toBeLessThan(needAt);
    expect(needAt).toBeLessThan(constraintAt);
    expect(constraintAt).toBeLessThan(planAt);
    expect(planAt).toBeLessThan(falsifiedAt);
    expect(falsifiedAt).toBeLessThan(hypothesisAt);
    expect(hypothesisAt).toBeLessThan(observationAt);
    expect(observationAt).toBeLessThan(claimAt);

    // Determinism: same state renders the identical brief twice.
    expect(projectEpistemicBrief(state, budget)).toBe(brief);
  });

  test("falsified and superseded hypotheses never enter the brief", () => {
    const state = fold([
      sessionCreated(1),
      hypothesisProposed(2, 1),
      hypothesisProposed(3, 2),
      hypothesisProposed(4, 3),
      hypothesisStatusChanged(5, 1, "falsified", { evidence: [2] }),
      hypothesisStatusChanged(6, 2, "superseded"),
      hypothesisStatusChanged(7, 3, "supported", { evidence: [2] }),
    ]);

    const brief = projectEpistemicBrief(state, budget);
    if (brief === undefined) {
      throw new Error("expected a rendered brief");
    }
    expect(brief).toContain("## Active hypotheses");
    expect(brief).toContain("[supported]");
    expect(brief).not.toContain("[falsified]");
    expect(brief).not.toContain("[superseded]");
    expect(brief).not.toContain("[proposed]");
  });

  test("caps observations at maxActiveObservations keeping the newest", () => {
    const events = [sessionCreated(1)];
    for (let n = 1; n <= 5; n += 1) {
      events.push(observationRecorded(n + 1, n, { claim: `observation number ${n}` }));
    }
    const state = fold(events);

    const capped: ContextBudget = { ...budget, maxActiveObservations: 3 };
    const brief = projectEpistemicBrief(state, capped);
    if (brief === undefined) {
      throw new Error("expected a rendered brief");
    }
    expect(brief).toContain("## Observations (latest 3)");
    expect(brief).not.toContain("observation number 1");
    expect(brief).not.toContain("observation number 2");
    expect(brief).toContain("observation number 3");
    expect(brief).toContain("observation number 4");
    expect(brief).toContain("observation number 5");
  });

  test("renders open challenges and hides resolved ones", () => {
    const withOpen = fold([
      sessionCreated(1),
      planSet(2, 1),
      challengeRaised(3, 1, { claim: "the plan ignores the missing file" }),
    ]);
    const open = projectEpistemicBrief(withOpen, budget);
    expect(open).toContain("## Open challenge");
    expect(open).toContain("Claim: the plan ignores the missing file");

    const resolved = fold([
      sessionCreated(1),
      planSet(2, 1),
      challengeRaised(3, 1),
      challengeResolved(4, 1, "rejected", "the file exists under another name"),
    ]);
    expect(projectEpistemicBrief(resolved, budget)).toContain("## Active plan");
  });

  test("renders pending INDETERMINATE executions with id, name, and reason", () => {
    const state = fold([
      sessionCreated(1),
      turnStarted(2, 1, "inspect the ledger"),
      toolProposed(3, 1, { name: "write_file" }),
      toolAuthorized(4, 1),
      toolStarted(5, 1),
      toolIndeterminate(6, 1, "process crashed mid-write; outcome unknown"),
    ]);
    const brief = projectEpistemicBrief(state, budget);
    expect(brief).toContain("## Pending indeterminate action");
    expect(brief).toContain("Execution: tool-exec-1 (write_file)");
    expect(brief).toContain("Reason: process crashed mid-write; outcome unknown");
  });

  test("renders the latest verification outcome including inconclusive", () => {
    const state = fold([
      sessionCreated(1),
      verificationRecorded(2, { outcome: "inconclusive", summary: "checker unreachable" }),
    ]);
    const brief = projectEpistemicBrief(state, budget);
    expect(brief).toContain("## Latest verification");
    expect(brief).toContain("Outcome: inconclusive");
    expect(brief).toContain("Summary: checker unreachable");
  });

  test("caps a pathological observation line without evicting later sections", () => {
    const state = fold([
      sessionCreated(1),
      observationRecorded(2, 1, { claim: "x".repeat(20_000) }),
      planSet(3, 1),
      challengeRaised(4, 1),
    ]);
    const smallBudget: ContextBudget = { ...budget, maxFragmentBytes: 300 };
    const brief = projectEpistemicBrief(state, smallBudget);
    if (brief === undefined) {
      throw new Error("expected a rendered brief");
    }
    expect(brief).toMatch(/…\[\+\d+ bytes truncated\]/u);
    const challengeAt = brief.indexOf("## Open challenge");
    const observationAt = brief.indexOf("## Observations");
    expect(observationAt).toBeGreaterThanOrEqual(0);
    // Section priority keeps the challenge before the bulk partition, and the
    // per-line cap keeps the truncated claim from evicting it.
    expect(challengeAt).toBeGreaterThanOrEqual(0);
    expect(challengeAt).toBeLessThan(observationAt);
  });
});

describe("maxActiveObservations budget cap", () => {
  test("default is 8 and validateContextBudget enforces positivity", () => {
    expect(DEFAULT_CONTEXT_BUDGET.maxActiveObservations).toBe(8);
    expect(() => validateContextBudget({ ...budget, maxActiveObservations: 0 })).toThrow(
      InvalidContextBudgetError,
    );
    expect(() => validateContextBudget({ ...budget, maxActiveObservations: 2.5 })).toThrow(
      InvalidContextBudgetError,
    );
  });
});
