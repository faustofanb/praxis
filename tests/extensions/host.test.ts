import type { PraxisExtension, SessionEventUnion } from "@praxis/contracts";
import { asSessionId, asTurnId, ModelRequestSchema } from "@praxis/contracts";
import { createExtensionHost, DuplicateExtensionError, observeEventStore } from "@praxis/core";
import { describe, expect, test } from "vitest";
import { inMemoryEventStore } from "../helpers/in-memory-event-store";
import {
  sessionCreated,
  sessionResumed,
  turnCompleted,
  turnStarted,
} from "../helpers/session-events";

/**
 * Extension host unit laws (docs/02 section 19, ADR-0013): registration
 * order is invocation order on every hook, unload stops invocation
 * immediately, duplicate names are rejected, 'isolate' swallows hook errors
 * while 'fail_closed' propagates, deny-only beforeTool cannot express
 * "allow", and the host stamps fragment sources itself.
 */

const SESSION_ID = asSessionId("session-ext-host");
const TURN = asTurnId("turn-1");
const TURN_CONTEXT = { sessionId: SESSION_ID, turnId: TURN } as const;

function recorder(name: string, log: string[]): PraxisExtension {
  return {
    name,
    onTurnStart: () => {
      log.push(`${name}:onTurnStart`);
    },
    contributeContext: () => {
      log.push(`${name}:contributeContext`);
      return [];
    },
    beforeModel: () => {
      log.push(`${name}:beforeModel`);
    },
    afterModel: () => {
      log.push(`${name}:afterModel`);
    },
    beforeTool: () => {
      log.push(`${name}:beforeTool`);
      return undefined;
    },
    afterTool: () => {
      log.push(`${name}:afterTool`);
    },
    onEvent: () => {
      log.push(`${name}:onEvent`);
    },
    onTurnEnd: () => {
      log.push(`${name}:onTurnEnd`);
    },
  };
}

describe("registration and unload", () => {
  test("registration order is preserved on every hook", async () => {
    const host = createExtensionHost();
    const log: string[] = [];
    host.register(recorder("alpha", log));
    host.register(recorder("beta", log));
    expect(host.names).toEqual(["alpha", "beta"]);

    await host.hooks.onTurnStart({ ...TURN_CONTEXT, input: "hi" });
    expect(log).toEqual(["alpha:onTurnStart", "beta:onTurnStart"]);

    log.length = 0;
    await host.hooks.beforeModel({ ...TURN_CONTEXT, request: minimalRequest() });
    expect(log).toEqual(["alpha:beforeModel", "beta:beforeModel"]);
  });

  test("unload stops invocation immediately and reports unknown names", async () => {
    const host = createExtensionHost();
    const log: string[] = [];
    host.register(recorder("alpha", log));
    host.register(recorder("beta", log));

    expect(host.unload("alpha")).toBe(true);
    expect(host.unload("alpha")).toBe(false);
    expect(host.unload("ghost")).toBe(false);
    expect(host.names).toEqual(["beta"]);

    await host.hooks.onTurnEnd({
      sessionId: SESSION_ID,
      turnId: TURN,
      outcome: { kind: "cancelled" },
    });
    expect(log).toEqual(["beta:onTurnEnd"]);
  });

  test("duplicate names are rejected at registration", () => {
    const host = createExtensionHost();
    host.register(recorder("alpha", []));
    expect(() => host.register(recorder("alpha", []))).toThrow(DuplicateExtensionError);
  });
});

describe("failure policy", () => {
  test("isolate (the default) swallows a throwing hook; the next extension still runs", async () => {
    const host = createExtensionHost();
    const log: string[] = [];
    host.register({
      name: "thrower",
      beforeModel: () => {
        throw new Error("telemetry sink unavailable");
      },
    });
    host.register(recorder("healthy", log));

    await expect(
      host.hooks.beforeModel({ ...TURN_CONTEXT, request: minimalRequest() }),
    ).resolves.toBeUndefined();
    expect(log).toEqual(["healthy:beforeModel"]);
  });

  test("fail_closed propagates wrapped with extension and hook names", async () => {
    const host = createExtensionHost();
    host.register({
      name: "policy-ext",
      failurePolicy: "fail_closed",
      beforeModel: () => {
        throw new Error("invariant broken");
      },
    });

    await expect(
      host.hooks.beforeModel({ ...TURN_CONTEXT, request: minimalRequest() }),
    ).rejects.toThrow(
      "extension 'policy-ext' hook beforeModel failed (fail_closed): invariant broken",
    );
  });

  test("a throwing hook from an isolated extension does not stop a fail_closed one from being consulted", async () => {
    const host = createExtensionHost();
    const order: string[] = [];
    host.register({
      name: "isolate-thrower",
      beforeTool: () => {
        order.push("isolate-thrower");
        throw new Error("boom");
      },
    });
    host.register({
      name: "denier",
      beforeTool: () => {
        order.push("denier");
        return { decision: "deny", reason: "blocked" };
      },
    });

    const denial = await host.hooks.beforeTool({
      ...TURN_CONTEXT,
      name: "read_file",
      effect: "read_only",
      argumentsJson: "{}",
    });
    expect(order).toEqual(["isolate-thrower", "denier"]);
    expect(denial).toEqual({
      extensionName: "denier",
      decision: { decision: "deny", reason: "blocked" },
    });
  });
});

describe("deny-only beforeTool", () => {
  test("first deny in registration order wins; no deny yields undefined", async () => {
    const host = createExtensionHost();
    host.register({
      name: "first",
      beforeTool: () => ({ decision: "deny", reason: "first says no" }),
    });
    host.register({
      name: "second",
      beforeTool: () => ({ decision: "deny", reason: "second says no" }),
    });

    const denial = await host.hooks.beforeTool({
      ...TURN_CONTEXT,
      name: "write_file",
      effect: "non_idempotent_write",
      argumentsJson: "{}",
    });
    expect(denial?.extensionName).toBe("first");
    expect(denial?.decision.reason).toBe("first says no");
  });

  test("a non-deny return is a contract violation and throws regardless of policy", async () => {
    const host = createExtensionHost();
    host.register({
      name: "forger",
      beforeTool: () => ({ decision: "allow" }) as never,
    });

    await expect(
      host.hooks.beforeTool({
        ...TURN_CONTEXT,
        name: "read_file",
        effect: "read_only",
        argumentsJson: "{}",
      }),
    ).rejects.toThrow(/only a deny is representable/);
  });
});

describe("context fragments", () => {
  test("the host stamps source with the extension's own name; spoofing is impossible", async () => {
    const host = createExtensionHost();
    host.register({
      name: "fragmenter",
      contributeContext: () => [{ source: "somebody-else", text: "spoofed section" }],
    });

    const fragments = await host.hooks.contributeContext({ ...TURN_CONTEXT });
    expect(fragments).toEqual([{ source: "fragmenter", text: "spoofed section" }]);
  });

  test("a non-array return is a contract violation and throws", async () => {
    const host = createExtensionHost();
    host.register({
      name: "garbage",
      contributeContext: () => "not fragments" as never,
    });

    await expect(host.hooks.contributeContext({ ...TURN_CONTEXT })).rejects.toThrow(
      /contributeContext returned a non-array/,
    );
  });
});

describe("observeEventStore", () => {
  test("onEvent fires once per appended event, after the append, tracking the open turn", async () => {
    const store = inMemoryEventStore();
    const host = createExtensionHost();
    const seen: { type: string; turnId: string | undefined }[] = [];
    host.register({
      name: "watcher",
      onEvent: (context) => {
        seen.push({ type: context.event.type, turnId: context.turnId?.valueOf() });
      },
    });

    const observed = observeEventStore(store, host);
    const events: SessionEventUnion[] = [
      { ...sessionCreated(1), sessionId: SESSION_ID },
      { ...turnStarted(2, 1, "go"), sessionId: SESSION_ID },
      { ...turnCompleted(3, 1), sessionId: SESSION_ID },
    ];
    await observed.append(events, 0);

    expect(seen).toEqual([
      { type: "SessionCreated", turnId: undefined },
      { type: "TurnStarted", turnId: "turn-1" },
      { type: "TurnCompleted", turnId: "turn-1" },
    ]);
    // TurnCompleted closes the tracked turn; later events see no open turn.
    await observed.append([{ ...sessionResumed(4), sessionId: SESSION_ID }], 3);
    expect(seen[3]).toEqual({ type: "SessionResumed", turnId: undefined });
    expect(await observed.readStream(SESSION_ID)).toHaveLength(4);
  });

  test("an isolate onEvent failure never breaks the append; fail_closed rethrows", async () => {
    const base = inMemoryEventStore();
    const isolated = createExtensionHost();
    isolated.register({
      name: "flaky",
      onEvent: () => {
        throw new Error("observer down");
      },
    });
    const observedIsolated = observeEventStore(base, isolated);
    await expect(
      observedIsolated.append([{ ...sessionCreated(1), sessionId: SESSION_ID }], 0),
    ).resolves.toBeUndefined();

    const strict = createExtensionHost();
    strict.register({
      name: "strict",
      failurePolicy: "fail_closed",
      onEvent: () => {
        throw new Error("observer down");
      },
    });
    const observedStrict = observeEventStore(base, strict);
    await expect(
      observedStrict.append([{ ...turnStarted(2, 1, "go"), sessionId: SESSION_ID }], 1),
    ).rejects.toThrow("extension 'strict' hook onEvent failed (fail_closed): observer down");
    // The append itself persisted; only the observation failed — the
    // observer crash never rolls back or blocks durability.
    const persisted = await base.readStream(SESSION_ID);
    expect(persisted.map((event) => event.type)).toEqual(["SessionCreated", "TurnStarted"]);
  });
});

function minimalRequest() {
  return ModelRequestSchema.parse({
    model: "scripted",
    messages: [{ role: "user", text: "hi" }],
    correlationId: SESSION_ID.valueOf(),
  });
}
