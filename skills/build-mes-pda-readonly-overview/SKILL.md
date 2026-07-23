---
name: build-mes-pda-readonly-overview
description: Build or review a MES PDA read-only statistics, inventory, or report page from an approved prototype, with typed APIs, custom navigation, filter semantics, request safety, display formatting, and route consistency. Use for MES PDA read-only overview pages, not editable forms or ordinary Web pages.
---

# Build MES PDA Read-only Overview

Implement one prototype faithfully while preserving the repository's established components and generated-file ownership.

## Establish the page contract

1. Confirm the active repository is the requirement-bound MES PDA worktree. If root route files are dirty, fingerprint them and make route changes only in the bound worktree.
2. Read the prototype, neighboring `customNav` pages, API conventions, and [page behavior contract](references/page-behavior-contract.md).
3. Freeze the route, visible fields, filter options, default selection, number units, empty-state wording, and retry behavior before editing.

## Implement

- Use the repository's `customNav` structure and Vue route block.
- Prefer existing cards, filters, loading indicators, error panels, empty states, and formatting helpers.
- If the endpoint belongs to a configured OpenAPI service, use generated Alova APIs. If a Magic-API is absent from generator configuration, add a typed handwritten wrapper outside generated directories and record the migration/metadata as its contract source.
- Never hand-edit `apiDefinitions.ts`, `globals.d.ts`, or another generated declaration for a single Magic endpoint.
- Multi-select filters cannot confirm an empty selection. Single-select filters provide an explicit “全部” option. Confirmation queries immediately.
- Prevent stale responses from replacing newer results. Define first-load defaults only after option data is available and avoid duplicate initial requests.
- Render loading, failure with retry, empty, and success states. Format money, weight, quantity, and Snowflake IDs without precision loss.

Use the neutral assets under `assets/readonly-overview/` only as structural prompts. Do not copy their names as business fields or impose shared colors.

## Route and review

Keep the Vue route block, `pages.json`, `uni-pages.d.ts`, and physical page path consistent. Prefer the repository's safe generator/checker when present; otherwise make the smallest bound-worktree edit and compare all four values.

Add focused tests for selection rules, first-load behavior, stale-request protection, retry, and route consistency when the repository supports them. Report the page/API paths, route evidence, handwritten-versus-generated decision, dirty-root fingerprint result, and checks not run.
