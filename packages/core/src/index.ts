import { packageName as contractsPackageName } from "@praxis/contracts";

/**
 * Public API of @praxis/core. Deterministic agent runtime; implementation
 * modules live under src/ and are reachable only through this entry.
 */

export { projectConversation } from "./agent-loop/conversation";
export type { ReconciliationReport, RecoveryDeps } from "./agent-loop/recovery";
export {
  pauseForUnresolvedIndeterminates,
  reconcileIndeterminateExecutions,
} from "./agent-loop/recovery";
export type {
  AgentLoopDeps,
  RunTurnOptions,
  TurnGuards,
  TurnOutcome,
} from "./agent-loop/run-turn";
export {
  DEFAULT_TURN_GUARDS,
  InvalidTurnGuardsError,
  runTurn,
  validateTurnGuards,
} from "./agent-loop/run-turn";
export { capabilityAuthorizer } from "./capability/authorizer";
export type { CapabilityPolicyConfig } from "./capability/policy";
export { capabilityDecision, capabilityPolicySummary } from "./capability/policy";
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
  ToolExecutionSnapshot,
} from "./state/reducer";
export {
  foldSessionEvents,
  IllegalTransitionError,
  initialSessionState,
  reduceSession,
} from "./state/reducer";
export type { EffectRetryPolicy } from "./tools/effect-policy";
export { retryPolicyForEffect, validateToolDefinitions } from "./tools/effect-policy";
export type {
  ExecutedToolSummary,
  ToolAuthorizationDecision,
  ToolAuthorizer,
  ToolRuntimeDeps,
} from "./tools/tool-runtime";
export {
  executeToolCall,
  projectSessionState,
  readOnlyAuthorizer,
} from "./tools/tool-runtime";

export const packageName = "@praxis/core";
export const workspaceDependencies = [contractsPackageName] as const;
