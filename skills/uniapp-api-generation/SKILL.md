---
name: uniapp-api-generation
description: Choose and safely implement a typed UniApp API client for AOTU or MOM using configured Alova/OpenAPI generation when available, or a handwritten wrapper for unconfigured Magic-API endpoints. Use for mobile/BFF endpoints, alova-gen, generated API names, or Magic endpoints consumed by UniApp.
---

# UniApp API Generation

Resolve the system, repository, endpoint kind, generator entry, and output ownership from evidence before editing client APIs.

## Choose the path

1. Read Praxis context, repository instructions, `package.json`, and `alova.config.ts`.
2. Match the endpoint's deployed OpenAPI group and path to an actual generator entry.
3. Use exactly one route:
   - **Configured OpenAPI service:** use the repository's Alova generation flow.
   - **Magic-API absent from generator configuration:** create a typed handwritten wrapper outside all generated directories.
4. Record the decision and contract source. For handwritten Magic clients, cite the Flyway `$magic$` metadata/migration and effective `/magic/api/...` URI.

Never add a fake generator entry or hand-edit `apiDefinitions.ts`, `globals.d.ts`, or other generated files just for one Magic endpoint.

## Configured OpenAPI workflow

- Confirm the backend OpenAPI document contains the expected method, path, DTOs, group, and `operationId`.
- Read `packageManager` and the declared generation script; run that exact version and script.
- Scope generation to one service when supported. Snapshot already-dirty generated files and reject unexplained collateral rewrites.
- Update call sites to generated names/types. Never copy declarations between `mesApp`, `mesPda`, `mesPad`, `wmsApp`, or similarly named services.
- If the OpenAPI service is stale or unavailable, stop and report it; do not claim generation succeeded.

## Handwritten Magic workflow

- Place the wrapper in the repository's manual API area, outside configured generated output roots.
- Define request/response types from the migration contract and preserve Snowflake IDs as strings.
- Use the effective full Magic URI and metadata HTTP method.
- Keep tenant identity out of the client request; the Magic script owns tenant resolution.
- Do not create generated-looking declarations or mix handwritten files into an Alova service folder.

## Review

Confirm the selected path is supported by repository evidence, URLs and methods match the backend, type names are business-specific, generated ownership is preserved, and unrelated services were untouched. Report the decision, contract source, modified paths, and checks not run. Lint, generation, typecheck, tests, or builds require exact active approval.
