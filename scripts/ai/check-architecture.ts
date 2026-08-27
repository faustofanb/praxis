/**
 * M0 implementation target for architecture conformance.
 *
 * Required behavior after M0:
 * - load .praxis/architecture.yaml with Bun.YAML
 * - discover workspace package manifests
 * - validate package dependency direction
 * - scan TS imports for forbidden workspace/deep imports and cycles
 * - report machine-readable violations
 * - exit non-zero on any MUST violation
 *
 * Keep this checker deterministic and model-free.
 */
export const architectureCheckerBootstrap = true as const;
