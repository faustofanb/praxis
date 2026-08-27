import { packageName as contractsPackageName } from "@praxis/contracts";

/**
 * Public API of @praxis/core. Deterministic agent runtime; implementation
 * modules live under src/ and are reachable only through this entry.
 */

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
