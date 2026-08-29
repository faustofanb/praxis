/**
 * Hard caps for the v0 ContextBuilder (docs/02 section 12.3). Context is a
 * bounded working set; every cap is a positive integer enforced up front.
 */

export type ContextBudget = {
  /** Max non-system messages kept in the recent-history window. */
  readonly maxRecentMessages: number;
  /** Max UTF-8 bytes per system/user/assistant text or tool-argument fragment. */
  readonly maxFragmentBytes: number;
  /** Max UTF-8 bytes per tool result fragment. */
  readonly maxToolResultBytes: number;
  /** Max observations entering the epistemic brief (docs/02 section 12.3). */
  readonly maxActiveObservations: number;
  /** Max active hypotheses entering the epistemic brief (docs/02 section 12.3). */
  readonly maxActiveHypotheses: number;
  /** Max estimated tokens for the whole built context (bytes/4, rounded up). */
  readonly maxEstimatedTokens: number;
};

/**
 * Byte caps must leave room for the truncation marker appended in place of
 * cut bytes (marker is at most 35 bytes: ellipsis + 16-digit count + label).
 */
export const MIN_FRAGMENT_CAP_BYTES = 40;

export const DEFAULT_CONTEXT_BUDGET: ContextBudget = {
  maxRecentMessages: 64,
  maxFragmentBytes: 16 * 1024,
  maxToolResultBytes: 8 * 1024,
  maxActiveObservations: 8,
  maxActiveHypotheses: 8,
  maxEstimatedTokens: 32 * 1024,
};

export class InvalidContextBudgetError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "InvalidContextBudgetError";
  }
}

export function validateContextBudget(budget: ContextBudget): void {
  const isPositiveInt = (value: number): boolean => Number.isInteger(value) && value > 0;

  if (!isPositiveInt(budget.maxRecentMessages)) {
    throw new InvalidContextBudgetError("maxRecentMessages must be a positive integer");
  }
  if (!isPositiveInt(budget.maxFragmentBytes) || budget.maxFragmentBytes < MIN_FRAGMENT_CAP_BYTES) {
    throw new InvalidContextBudgetError(
      `maxFragmentBytes must be an integer >= ${MIN_FRAGMENT_CAP_BYTES}`,
    );
  }
  if (
    !isPositiveInt(budget.maxToolResultBytes) ||
    budget.maxToolResultBytes < MIN_FRAGMENT_CAP_BYTES
  ) {
    throw new InvalidContextBudgetError(
      `maxToolResultBytes must be an integer >= ${MIN_FRAGMENT_CAP_BYTES}`,
    );
  }
  if (!isPositiveInt(budget.maxActiveObservations)) {
    throw new InvalidContextBudgetError("maxActiveObservations must be a positive integer");
  }
  if (!isPositiveInt(budget.maxActiveHypotheses)) {
    throw new InvalidContextBudgetError("maxActiveHypotheses must be a positive integer");
  }
  if (!isPositiveInt(budget.maxEstimatedTokens)) {
    throw new InvalidContextBudgetError("maxEstimatedTokens must be a positive integer");
  }
}
