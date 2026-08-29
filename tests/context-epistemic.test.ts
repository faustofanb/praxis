import type { ContextBudget } from "@praxis/core";
import {
  ContextBudgetExceededError,
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

const encoder = new TextEncoder();
const utf8BytesOf = (text: string): number => encoder.encode(text).length;

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
    // A plan-target challenge does not render a completion block.
    expect(open).not.toContain("## Completion blocked");

    const resolved = fold([
      sessionCreated(1),
      planSet(2, 1),
      challengeRaised(3, 1),
      challengeResolved(4, 1, "rejected", "the file exists under another name"),
    ]);
    expect(projectEpistemicBrief(resolved, budget)).toContain("## Active plan");
  });

  test("renders the completion block while a completion-target challenge is open, and stops once resolved", () => {
    const blocked = fold([
      sessionCreated(1),
      challengeRaised(2, 1, {
        targetType: "completion",
        claim: "the restoration was never verified",
      }),
    ]);
    const brief = projectEpistemicBrief(blocked, budget);
    expect(brief).toContain("## Completion blocked");
    expect(brief).toContain("1 completion-target challenge(s) are resolved");
    expect(brief).toContain("Challenge: challenge-1 — the restoration was never verified");

    const unblocked = fold([
      sessionCreated(1),
      challengeRaised(2, 1, { targetType: "completion" }),
      challengeResolved(3, 1, "resolved", "verification recorded"),
    ]);
    expect(projectEpistemicBrief(unblocked, budget)).toBeUndefined();
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

  test("evicts a pathological compactable section honestly instead of evicting fixed sections", () => {
    const state = fold([
      sessionCreated(1),
      observationRecorded(2, 1, { claim: "x".repeat(20_000) }),
      planSet(3, 1),
      challengeRaised(4, 1),
    ]);
    // A line needing per-line truncation occupies ~cap bytes by itself, so it
    // can never coexist with the fixed tier inside one fragment cap: the
    // two-tier law drops the whole compactable section and says so, rather
    // than truncating it into view or evicting plan/challenge lines.
    const smallBudget: ContextBudget = { ...budget, maxFragmentBytes: 300 };
    const brief = projectEpistemicBrief(state, smallBudget);
    if (brief === undefined) {
      throw new Error("expected a rendered brief");
    }
    expect(brief).toContain("## Active plan");
    expect(brief).toContain("## Open challenge");
    expect(brief).not.toContain("## Observations");
    expect(brief).toContain("…[+2 brief lines omitted]");
    expect(utf8BytesOf(brief)).toBeLessThanOrEqual(300);
  });
});

describe("two-tier assembly law (M5-T001)", () => {
  test("caps active hypotheses at maxActiveHypotheses keeping the newest, with an omission marker", () => {
    const events = [sessionCreated(1)];
    for (let n = 1; n <= 10; n += 1) {
      events.push(hypothesisProposed(n + 1, n, { statement: `hypothesis number ${n}` }));
    }
    const state = fold(events);

    const capped: ContextBudget = { ...budget, maxActiveHypotheses: 3 };
    const brief = projectEpistemicBrief(state, capped);
    if (brief === undefined) {
      throw new Error("expected a rendered brief");
    }
    expect(brief).toContain("## Active hypotheses");
    expect(brief).toContain("- [proposed] hypothesis number 8");
    expect(brief).toContain("- [proposed] hypothesis number 9");
    expect(brief).toContain("- [proposed] hypothesis number 10");
    expect(brief).toContain("…[+7 older active hypotheses omitted]");
    for (let n = 1; n <= 7; n += 1) {
      expect(brief).not.toContain(`[proposed] hypothesis number ${n}\n`);
    }
  });

  test("a hypothesis flood never evicts non-compactable sections and stays within the fragment cap", () => {
    const events = [
      sessionCreated(1),
      goalSet(2, { goal: "restore the missing payment record" }),
      planSet(3, 1),
      challengeRaised(4, 1, { claim: "the plan ignores the missing file" }),
      turnStarted(5, 1, "write the ledger"),
      toolProposed(6, 1, { name: "write_file" }),
      toolAuthorized(7, 1),
      toolStarted(8, 1),
      toolIndeterminate(9, 1, "process crashed mid-write; outcome unknown"),
      verificationRecorded(10, { outcome: "inconclusive", summary: "checker unreachable" }),
    ];
    for (let n = 1; n <= 40; n += 1) {
      events.push(
        hypothesisProposed(events.length + 1, n, {
          statement: `${n} the ledger replica may lag behind the primary by a full sync cycle`,
        }),
      );
    }
    for (let n = 1; n <= 5; n += 1) {
      events.push(observationRecorded(events.length + 1, n, { claim: `observation number ${n}` }));
    }
    const state = fold(events);

    const tight: ContextBudget = { ...budget, maxFragmentBytes: 1000 };
    const brief = projectEpistemicBrief(state, tight);
    if (brief === undefined) {
      throw new Error("expected a rendered brief");
    }
    // Every non-compactable section survives the flood.
    expect(brief).toContain("## Goal");
    expect(brief).toContain("## Active plan");
    expect(brief).toContain("## Open challenge");
    expect(brief).toContain("## Pending indeterminate action");
    expect(brief).toContain("## Latest verification");
    // The compactable hypothesis section yields, honestly counted; the small
    // observations section still fits after it.
    expect(brief).not.toContain("## Active hypotheses");
    expect(brief).toContain("…[+10 brief lines omitted]");
    expect(brief).toContain("## Observations");
    expect(utf8BytesOf(brief)).toBeLessThanOrEqual(1000);
  });

  test("fails closed when the non-compactable tier alone cannot fit", () => {
    const state = fold([
      sessionCreated(1),
      goalSet(2, {
        goal: "restore the missing payment record",
        constraints: [
          "never write without a matching invoice and a second operator confirmation",
          "never bypass the ledger reconciliation pass under any operational pressure",
          "never treat an unverified replica as the source of truth for balances",
        ],
      }),
    ]);
    const tiny: ContextBudget = { ...budget, maxFragmentBytes: 300 };
    expect(() => projectEpistemicBrief(state, tiny)).toThrow(ContextBudgetExceededError);
    expect(() => projectEpistemicBrief(state, tiny)).toThrow(/non-compactable/u);
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

describe("maxActiveHypotheses budget cap", () => {
  test("default is 8 and validateContextBudget enforces positivity", () => {
    expect(DEFAULT_CONTEXT_BUDGET.maxActiveHypotheses).toBe(8);
    expect(() => validateContextBudget({ ...budget, maxActiveHypotheses: 0 })).toThrow(
      InvalidContextBudgetError,
    );
    expect(() => validateContextBudget({ ...budget, maxActiveHypotheses: 1.5 })).toThrow(
      InvalidContextBudgetError,
    );
  });
});
