import { SessionEventUnionSchema, TOOL_EFFECTS } from "@praxis/contracts";
import fc from "fast-check";
import { describe, expect, test } from "vitest";
import { toolProposed, toolReconciled, toolSucceeded } from "../helpers/session-events";

const jsonString = fc.string({ minLength: 0, maxLength: 60 }).map((s) => JSON.stringify(s));

describe("tool event schemas properties", () => {
  test("tool events survive a JSON round trip identically", () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...TOOL_EFFECTS),
        jsonString,
        fc.string({ minLength: 1, maxLength: 40 }),
        (effect, argumentsJson, name) => {
          const event = toolProposed(1, 1, { effect, argumentsJson, name });
          const parsed = SessionEventUnionSchema.parse(JSON.parse(JSON.stringify(event)));
          expect(JSON.stringify(parsed)).toBe(JSON.stringify(event));
        },
      ),
    );
  });

  test("result payloads survive a JSON round trip identically", () => {
    fc.assert(
      fc.property(fc.jsonValue(), (result) => {
        const event = toolSucceeded(1, 1, JSON.stringify(result));
        const parsed = SessionEventUnionSchema.parse(JSON.parse(JSON.stringify(event)));
        expect(JSON.stringify(parsed)).toBe(JSON.stringify(event));
      }),
    );
  });

  test("reconciliation payloads survive a JSON round trip identically in every variant", () => {
    fc.assert(
      fc.property(
        fc.constantFrom("succeeded" as const, "failed" as const, "indeterminate" as const),
        fc.string({ minLength: 1, maxLength: 60 }),
        (outcome, detail) => {
          const event = toolReconciled(1, 1, outcome, detail);
          const parsed = SessionEventUnionSchema.parse(JSON.parse(JSON.stringify(event)));
          expect(JSON.stringify(parsed)).toBe(JSON.stringify(event));
        },
      ),
    );
  });
});
