# MOM Magic script conventions

## `$magic$` payload

Each `magic_api_file.file_content` payload has:

1. `$magic$`
2. one JSON metadata object
3. a newline, exactly `================================`, and another newline
4. the Magic script
5. closing `$magic$`

The metadata source of truth is the nearest migration in the same MOM module. Preserve its supported fields and JSON encoding. `groupId`, `method`, and `path` must agree with the reused group and registered permission.

## Tenant isolation

- Obtain the active tenant only through `ifc.getTenantId()`.
- Do not accept tenant identity in query, path, body, header, or Magic parameter metadata.
- Apply the tenant restriction to every query branch, including aggregate totals and option queries.

## SQL contract

- Bind each `#{name}` before use according to the repository's Magic script style.
- Preserve the database dialect and placeholder conventions of adjacent scripts.
- Convert Snowflake IDs to character data before returning them to JavaScript clients.
- Make optional filters explicit; do not weaken the tenant predicate while composing conditions.

## File identity

Reuse the existing group and add only the target API file. Match the neighboring file path and storage columns. Idempotence may use a narrowly scoped delete-and-insert or `NOT EXISTS`; it must not erase sibling APIs.
