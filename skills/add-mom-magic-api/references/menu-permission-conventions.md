# MOM menu and permission conventions

## One permission boundary

The menu resource, API registration, and built-in tenant relationship must resolve to the same `def_resource.id`.

- Resolve the parent using `def_resource.code`.
- Create a new resource only for a genuinely new menu or button boundary.
- Keep the PDA route identical to the frontend route, including leading slash and case.
- Follow adjacent migrations for resource type, sort order, icon, visibility, audit columns, and ID generation.

## Magic permission identity

For a MOM Magic endpoint:

- `controller`: `MagicController`
- `spring_application_name`: `lamp-system-server`
- `request_method`: the upper-case Magic metadata method
- `uri`: `/magic/api/<group-path>/<api-path>`

Do not register only the API-local path. Do not use a Java BFF service name for a Magic endpoint.

## Idempotence

- Guard resource creation by a stable code.
- Guard API registration by the repository's effective uniqueness key, normally method plus URI.
- Grant the resource to built-in tenants with `NOT EXISTS`.
- Never hard-code an environment-specific menu parent ID when a code lookup exists.
