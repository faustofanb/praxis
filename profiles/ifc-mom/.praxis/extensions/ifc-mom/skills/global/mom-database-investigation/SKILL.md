---
name: mom-database-investigation
description: '用于 IFC MOM 真实库只读调查、生产库边界、大表查询约束、字段口径、主数据唯一性、字典/枚举证据、SQL 证据落盘和数据库调查结果复核。适用于涉及真实数据、表关系、字段来源、报表口径、SQL、迁移、字典、主数据或数据修复的任务。默认使用 dbx MCP 进行只读查询。'
user-invocable: true
---

# MOM Database Investigation

## 适用场景

- 用户提到真实数据、表关系、字段来源、样例数据、数据口径、数据修复。
- 涉及 SQL、DDL、Flyway、迁移、MagicAPI、报表、驾驶舱、字典、主数据。
- 需要判断字段含义、状态枚举、唯一性、关联关系、时间口径或单位口径。

## 核心约束

- 数据库 MCP 调查默认使用 dbx MCP 只读查询；禁止写入、修数、DDL 或执行高风险函数。
- 使用 dbx 前先读取当前 workspace 的 `praxis.projects.toml`，按 `[database.local]` 确认本地 `connection`、`database` 和 `schema`；同一个 `LOCAL` 连接可能包含多个项目数据库，禁止只凭连接名推断库名。
- 使用 dbx 前先 `dbx_list_connections` 确认连接名、库名和环境；本地查询必须命中 `[database.local].database`，默认只查 `LOCAL` / `DEV`，`PRO` 或疑似生产库必须先获得用户明确许可。
- 每次业务查询前先用只读 SQL 确认会话库，例如 `select current_database(), current_schema();`；元数据查询必须按配置限定 `table_catalog` 和 `table_schema`。
- 可用只读工具优先级：`dbx_list_connections`、`dbx_list_tables`、`dbx_execute_query`；`dbx_execute_and_show` 只用于需要用户在 DBX UI 查看结果时。
- 字段、索引、约束、注释或视图定义细节通过 `dbx_execute_query` 查询 `information_schema`、`pg_catalog` 或 PostgreSQL 元数据函数确认；不要调用当前运行时未暴露的 dbx 工具名。
- 生产库或疑似生产数据必须先确认环境、范围、条件和风险。
- 生产数采、日志、流水、历史明细、大表禁止无条件查询和全表扫描。
- 大表查询必须带时间、租户、产线、设备、主键、业务单号或合理 `limit`。
- 字段口径结论必须有证据来源：表结构、注释、索引/约束、字典、样例数据、源码或业务文档。
- Code Graph、源码、历史文档只能辅助定位；数据口径最终要回到真实库或明确标注待确认。

## 调查顺序

1. 通过 dbx MCP 确认连接与风险级别：开发库、测试库、生产库或未知。
2. 查元数据：表注释、字段注释、类型、索引、约束、外键或唯一键。
3. 查字典和主数据：编码、中文名、启停状态、租户范围、唯一性。
4. 查小样本：必须条件化，记录参数和样本规模。
5. 对账口径：固定同一数据源、同一统计时刻、同一参数范围。
6. 证据落盘：写入需求 `01-需求分析拆解/` 或 `04-产出物/关联信息调查/`。

## 输出证据

- 数据库环境和权限边界。
- dbx 连接名、`praxis.projects.toml [database.local]` 数据库名、schema 和查询工具。
- 查询目标、过滤条件、样本规模和未查原因。
- 表字段/字典/主数据证据。
- 已确认口径、待确认口径和风险。
- 可复用 SQL 只放需求产出物，不直接进入正式迁移目录。

## 关联规则

- `.praxis/extensions/ifc-mom/rules/global/praxis-workflow/03-调查门禁.md`
- `.praxis/extensions/ifc-mom/rules/global/00-工作流精简索引.md -> 调查与证据`
- `.praxis/extensions/ifc-mom/skills/global/mom-lightweight-etl-report/SKILL.md`
