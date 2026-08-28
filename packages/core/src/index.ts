import { packageName as contractsPackageName } from "@praxis/contracts";

/**
 * Public API of @praxis/core. Deterministic agent runtime; implementation
 * modules live under src/ and are reachable only through this entry.
 */

export type { ContextBudget } from "./context/budget";
export {
  DEFAULT_CONTEXT_BUDGET,
  InvalidContextBudgetError,
  MIN_FRAGMENT_CAP_BYTES,
  validateContextBudget,
} from "./context/budget";
export type {
  BuiltContext,
  ContextBuildInput,
  ContextEstimate,
} from "./context/builder";
export {
  buildContext,
  ContextBudgetExceededError,
  InvalidContextError,
} from "./context/builder";
export type {
  DerivedSessionState,
  SessionStatus,
} from "./state/reducer";
export {
  foldSessionEvents,
  IllegalTransitionError,
  initialSessionState,
  reduceSession,
} from "./state/reducer";

export const packageName = "@praxis/core";
export const workspaceDependencies = [contractsPackageName] as const;
