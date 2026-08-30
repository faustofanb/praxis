import type {
  ContextFragment,
  PraxisExtension,
  ToolHookContext,
  ToolHookDecision,
} from "@praxis/contracts";

/**
 * Operator standing orders over the ADR-0013 seams (docs/02 section 19):
 * the second shipped extension and the first embodying the POLICY cell of
 * the section-19 failure table — failurePolicy 'fail_closed'. Standing
 * orders are load-bearing operator policy: if a hook crashes, the turn must
 * crash into the existing recovery machinery (docs/02 section 17) rather
 * than silently run without them.
 *
 * Two contributions, both optional by configuration:
 *
 * - contributeContext: one fragment carrying the configured instructions.
 *   The host stamps `source` and the M5-T001 composition law caps the
 *   rendered `## Extension: standing-orders` section — this package adds
 *   zero composition logic of its own.
 * - beforeTool: a name deny-list. Deny is the only expressible decision
 *   (ADR-0013): this extension RESTRICTS on top of the capability
 *   authorizer's grant; it can never grant anything.
 *
 * Zero configuration is inert: both hooks return undefined so a
 * registered-but-unconfigured extension costs no prompt byte and vetoes
 * nothing (byte identity with a bare run).
 *
 * Configuration errors are loud at construction — a policy extension must
 * never discover a typo mid-turn.
 */

export type StandingOrdersOptions = {
  /** Standing instructions rendered into every turn's system fragment. */
  readonly instructions?: string;
  /** Tool names this policy denies (matched exactly, case-sensitively). */
  readonly deniedTools?: readonly string[];
};

export const STANDING_ORDERS_EXTENSION_NAME = "standing-orders";

export class InvalidStandingOrdersError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "InvalidStandingOrdersError";
  }
}

function validateOptions(options: StandingOrdersOptions): void {
  if (options.instructions !== undefined) {
    if (typeof options.instructions !== "string" || options.instructions.trim() === "") {
      throw new InvalidStandingOrdersError(
        "standing-orders: instructions must be a non-empty string (whitespace-only instructions are a configuration bug; omit the field instead)",
      );
    }
  }
  if (options.deniedTools !== undefined) {
    if (!Array.isArray(options.deniedTools)) {
      throw new InvalidStandingOrdersError(
        "standing-orders: deniedTools must be an array of tool names",
      );
    }
    for (const name of options.deniedTools) {
      if (typeof name !== "string" || name.trim() === "") {
        throw new InvalidStandingOrdersError(
          "standing-orders: deniedTools entries must be non-empty strings",
        );
      }
    }
  }
}

export function createStandingOrdersExtension(options?: StandingOrdersOptions): PraxisExtension {
  const resolved: StandingOrdersOptions = options ?? {};
  validateOptions(resolved);

  // Freeze the policy inputs: a mid-session mutation of the caller's arrays
  // must not change what an already-registered extension enforces.
  const instructions = resolved.instructions;
  const deniedTools =
    resolved.deniedTools === undefined ? [] : Object.freeze([...resolved.deniedTools]);

  return {
    name: STANDING_ORDERS_EXTENSION_NAME,
    failurePolicy: "fail_closed",

    contributeContext(): readonly ContextFragment[] | undefined {
      if (instructions === undefined) {
        return undefined;
      }
      // The host stamps `source` with the registered name regardless; this
      // field merely satisfies the fragment type with the same honest value.
      return [{ source: STANDING_ORDERS_EXTENSION_NAME, text: instructions }];
    },

    beforeTool(context: ToolHookContext): ToolHookDecision | undefined {
      if (deniedTools.includes(context.name)) {
        return {
          decision: "deny",
          reason: `standing orders forbid tool '${context.name}'`,
        };
      }
      return undefined;
    },
  };
}
