---
name: dbx-database-investigation
description: 通过 DBX CLI（必要时回退 MCP）调查数据库结构。适用于表结构、DTO、迁移、报表口径、SQL 错误和执行计划调查。
---

# DBX 数据库调查

## 一、技能用途

在不保存数据库凭据的前提下调查连接、Schema、表结构和有界只读数据。

## 二、适用业务域

适用于已登记需求的业务系统和业务域；规划模式禁止正式登记需求时，也可在项目画像范围内
创建不持久化的 `investigation_scope`。

## 三、适用场景

Schema 调查、API/DTO 对照、迁移设计、报表口径、SQL 错误和执行计划。

## 四、不适用场景

连接管理、生产写入、部署或与当前需求无关的全库浏览。

## 五、所需输入

已登记需求编号，或规划模式的临时调查范围；以及目标项目、已登记的 `dbx://` 连接引用和
明确调查目的。

## 六、提供能力

规划模式优先调用
`praxis database investigate --project <项目> --connection <引用> --purpose <目的> --sql <SQL>`；
它会校验项目登记、允许已登记生产连接的只读调查、阻断非只读 SQL、自动执行
`select current_database()`，并返回
`persisted: false` 的临时收据。正式需求内再使用 DBX CLI 的 JSON 契约（`connections`、
`schema`、`query`、`context`），只读取任务涉及的表；必要时执行一个有界 `SELECT`、
`WITH … SELECT` 或 `EXPLAIN`。仅当连接引用显式指定数据库而 CLI 无法选择该数据库，或
CLI 不可用时，回退 DBX MCP。

## 七、依赖工具

先检查 `dbx` CLI；CLI 不可用时再检查 `skill.toml` 中的 MCP `required_tools`。两者都不可用时停止并说明如何安装 `@dbx-app/cli` 或配置外部 DBX MCP。

## 八、业务约束

先读取当前 context 的 `critical_facts.database`，只能从 `registered` 中显式选择连接；
`production` 中的连接必须明确标记为生产环境。禁止依赖 DBX 默认连接或默认 `postgres` 库。
选定连接后，任何 Schema、表结构或数据判断之前都先执行 `select current_database()`，并核对
返回库名与任务目标一致。未找到匹配连接时返回：`未找到匹配 connection；请先在 Praxis 项目配置中登记 DBX 连接。`
规划模式入口允许已登记生产连接的只读调查；禁止生产写入、其他写 SQL、锁定读取、连接管理、
默认库猜测和状态持久化。返回的临时结论不能冒充正式需求证据，需求登记后必须重新确认有效性
并纳入对应需求。

## 九、数据约束

不扩大查询范围，不输出凭据，不把秘密写入需求文档、画像、技能或日志。

## 十、风险

禁止调用 `dbx_add_connection`、`dbx_remove_connection`；禁止写 SQL、危险 SQL、自动连接管理和绕过 Praxis 门禁。

## 十一、验证方法

记录连接引用、Schema 证据、查询边界和调查结论；规划模式结果明确保留
`persisted: false`，进入实施后再关联正式需求。可复用 SQL 必须登记为需求产出物。

## 十二、知识来源

DBX 工具可用性和连接配置在执行时核对，Praxis 路由器不猜测外部状态。
