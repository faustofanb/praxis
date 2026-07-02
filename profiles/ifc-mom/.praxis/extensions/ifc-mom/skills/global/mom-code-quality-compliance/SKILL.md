---
name: mom-code-quality-compliance
description: Use when implementing or reviewing IFC MOM backend or Web code and the task must enforce project coding standards, same-domain examples, tests, and quality review evidence.
user-invocable: true
---

# MOM Code Quality Compliance

## Purpose

Keep backend and Web work aligned with project rules before code is written, while code is written, and before delivery. This skill distills useful external practices into local MOM guardrails: surgical changes, same-domain examples, evidence-first debugging, focused tests, and reviewable compliance evidence.

## When To Use

- Any `backend` Java change.
- Any `web` Vue/TypeScript/API/schema/form change.
- Any cross-project backend + Web task.
- Any Quality Agent review of backend or Web changes.

## Development Gate

Before editing code, produce a short compliance plan:

```text
domain_examples:
  - <same-domain file/page/API/class checked>
rules_loaded:
  - <backend/web rule or skill path>
change_boundary:
  - <files/directories allowed to change>
standards_to_prove:
  - <backend layering / web API-schema-permission-i18n / SQL / test requirement>
verification:
  - <minimal command or reason unavailable>
```

If no same-domain example exists, state the search terms and directories checked. Do not invent a new pattern silently.

## Backend Checklist

- Follow Controller -> Service -> Manager -> Mapper boundaries; Controller stays thin.
- Reuse existing parent classes, feature interfaces, DTO/VO/Query naming, validation annotations, Swagger annotations, and package layout.
- Put transactions at the service orchestration boundary; avoid transaction-like behavior scattered across Controller or Mapper helpers.
- Avoid N+1 queries, loop queries, unpaged large queries, and raw SQL without parameter safety.
- Do not expose Entity directly to the frontend.
- For master data, employee, material, warehouse, cost center, dictionary, and tenant-related logic, verify business uniqueness from schema or existing code instead of assuming a single field is unique.
- Prefer focused JUnit tests or workflow gate assertions for shared logic, data口径, transaction behavior, or bug fixes.

## Web Checklist

- Check same-domain page/API/schema/hook/store before implementing.
- Keep page, API, schema, hooks, store, route, permission, and i18n responsibilities separate.
- Use existing Vben/VxeGrid patterns, `#/` imports, project message helpers, permission controls, and i18n conventions.
- Do not hardcode display text, permission decisions, API URLs, export behavior, table layout, or dictionary/status mapping when local conventions exist.
- API files should match backend contract names and comments; generated API changes must not be hand-edited unless the project workflow allows it.
- For forms and grids, preserve existing validation, loading, disabled-state, batch-selection, export, and pagination patterns.
- Run the smallest lint/typecheck/check command feasible; if dependencies are missing, follow the project rule to install in the worktree before declaring blocked.

## Debugging And Tests

- Bug fixes need failure evidence before implementation: reproduction, failing test, log, SQL sample, or strongest available trace.
- Test critical business paths and changed shared logic; avoid exhaustive low-value tests unless requested.
- Tests should assert behavior, not implementation details, and mock external APIs/filesystems/databases unless the task is explicitly integration-level.

## Review Evidence

Execution Agent must return:

```text
compliance:
  domain_examples_checked:
    - <path>
  rules_checked:
    - <path>
  standards_proven:
    - <specific checklist item and evidence>
  deviations:
    - <none or justified exception>
```

Quality Agent must fail the review if backend/Web changes lack same-domain evidence, skip mandatory project rules, or provide only vague compliance claims.
