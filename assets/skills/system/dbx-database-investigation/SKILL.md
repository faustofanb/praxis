---
name: dbx-database-investigation
description: Investigate database structures through an externally configured DBX MCP using read-only tools. Use for schema investigation, API/DTO comparison, Flyway or SQL migration design, report semantics, SQL errors, execution plans, or an explicitly requested business portrait supplement.
---

# DBX database investigation

1. Check that every `required_tools` entry from `skill.toml` is available. If not, stop and tell the user to install and configure the external DBX MCP.
2. Call `dbx_list_connections`, then match a connection using the selected workspace project facts and portrait. Praxis never configures DBX.
3. If no connection matches, stop with: `未找到匹配 connection；请先在 DBX 中配置目标业务系统连接。`
4. Display the selected connection and environment. Ask for confirmation again before reading a production connection.
5. Prefer `dbx_get_schema_context`; call `dbx_list_tables` or `dbx_describe_table` only for tables involved in the task.
6. If data is necessary, execute one bounded `SELECT`, `WITH ... SELECT`, or `EXPLAIN`. Never broaden the query beyond the stated investigation.
7. Record conclusions in requirement `analysis.md`; save reusable query text under requirement `artifacts/`.

禁止调用 `dbx_add_connection`、`dbx_remove_connection`，禁止写 SQL、危险 SQL、自动连接管理、secret 持久化或绕过用户确认。DBX 的工具可用性和 connection 配置在 Skill 执行时检查，不由 Praxis router 猜测。
