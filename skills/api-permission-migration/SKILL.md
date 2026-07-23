---
name: api-permission-migration
description: Generate or review idempotent AOTU or MOM Flyway migrations that bind Java Controller or Magic-API endpoints to def_resource_api. Use for new Web/PDA/PAD APIs, Sa-Token 11051 or “无此权限”, menu/button permission binding, and Magic permission consistency.
---

# API Permission Migration

Generate the smallest permission migration that follows the active repository. Never write directly to a live database.

## Resolve the endpoint kind and project profile

Read the nearest migrations and actual table columns. Record the module, migration root, resource-code convention, stored URI convention, service name, and ID strategy.

Classify the endpoint:

- **Java Controller:** expand class/method mappings and copy `controller`, application name, method, and gateway URI conventions from the same service.
- **MOM Magic-API:** use `controller = MagicController`, `spring_application_name = lamp-system-server`, metadata method, and `/magic/api/<group-path>/<api-path>`.

Do not transfer AOTU prefixes to MOM or Java BFF conventions to Magic without repository evidence.

## Build the endpoint inventory

1. List every effective `(method, stored URI)` introduced or changed.
2. Search existing registrations by resource code, controller, application, URI, and method.
3. Reuse the page/menu resource for page queries and the established button resource for governed actions.
4. Resolve parent and target resources by stable `def_resource.code`; avoid environment IDs.

## Create an idempotent migration

- Add a new Flyway migration; never edit an applied one.
- Guard API rows by the repository's uniqueness identity, normally method plus URI.
- When creating a resource, make menu and built-in tenant grants idempotent.
- For Magic, ensure the API registration, menu, and tenant relationship all use the same resource.
- For Magic, make method/path agree with `$magic$` metadata and use the full `/magic/api/...` URI.
- Follow adjacent migrations for sequences, Snowflake values, audit columns, schema qualification, and deletes versus `NOT EXISTS`.

When schema inspection is needed, select an explicit non-production DBX connection and run `select current_database()` first.

## Review

- Every effective mapping has exactly one intended registration.
- Method, case-sensitive URI, controller, and application are consistent.
- Resource codes resolve without placeholder environment IDs.
- Magic metadata, permission URI, menu path, built-in tenant grant, and resource identity agree.
- No credentials, direct database execution, unrelated schema work, or applied-migration edits are present.

Report project evidence, migration path, endpoint inventory, resources, and checks not executed. Run lint, tests, database checks, or migration execution only with exact active approval.
