---
name: add-mom-magic-api
description: Add or review a MOM Magic-API through an idempotent Flyway migration, including Magic metadata, menu, permission URI, built-in tenant grant, tenant isolation, and focused contract validation. Use for MOM Magic-API and PDA-menu migrations; do not use for ordinary Java Spring Controller endpoints.
---

# Add MOM Magic-API

Create the smallest migration that adds one bounded Magic-API capability. Never execute it against a database without separate approval.

## Resolve local conventions

1. Locate the active MOM repository, module migration root, nearest dated migrations, and bound requirement worktree.
2. Read [Magic script conventions](references/magic-script-conventions.md) and [menu/permission conventions](references/menu-permission-conventions.md).
3. Find the existing `magic_api_file` group by stable group metadata. Reuse it; do not replace or delete the whole group to add one API.
4. Resolve the menu parent by stable `def_resource.code`, not an environment-specific ID.

## Build the migration

- Store a parseable `$magic$` metadata JSON followed by exactly 32 `=` characters and the Magic script.
- Keep tenant identity internal with `ifc.getTenantId()`. Do not expose `tenantId`, `tenant_id`, or `tenant` as a request parameter.
- Return Snowflake identifiers as strings. Bind every `#{placeholder}` explicitly in the script.
- Make `magic_api_file`, menu, `def_resource_api`, and built-in tenant relationship changes idempotent.
- Register the permission with `controller = MagicController`, `spring_application_name = lamp-system-server`, and URI `/magic/api/<group-path>/<api-path>`.
- Keep Magic metadata method/path, permission method/URI, PDA menu route, and tenant relation on the same resource consistent.

Start from `assets/magic-api-migration.sql.template`, then adapt columns and ID generation to the nearest migration. The asset is a checklist-shaped scaffold, not repository evidence.

## Validate

Run the deterministic validator with the real group and route:

```bash
python scripts/validate_magic_migration.py <migration.sql> \
  --expected-group-id <group-id> \
  --expected-group-path <group-path> \
  --expected-menu-route <pda-route>
```

Also add a focused migration contract test using the repository's existing test style. Verify the validator detects broken `$magic$` JSON, delimiter damage, wrong group, exposed tenant parameters, permission mismatch, wrong menu route, non-string IDs, and missing tenant grants.

Report the migration path, reused group, resource code, effective API URI, menu route, tenant boundary, validator result, and any checks not run.
