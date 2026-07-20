---
name: dbx-database-investigation
description: 通过 DBX CLI（必要时回退 MCP）调查数据库结构。适用于表结构、DTO、迁移、报表口径、SQL 错误和执行计划调查。
---

# DBX 数据库调查

## 一、技能用途

在不保存数据库凭据的前提下调查连接、Schema、表结构和有界只读数据。

## 二、适用业务域

适用于当前需求已经登记的业务系统和业务域。

## 三、适用场景

Schema 调查、API/DTO 对照、迁移设计、报表口径、SQL 错误和执行计划。

## 四、不适用场景

连接管理、生产写入、部署或与当前需求无关的全库浏览。

## 五、所需输入

需求编号、目标仓库、已登记的 `dbx://` 连接引用和调查目的。

## 六、提供能力

优先调用 DBX CLI 的 JSON 契约（`connections`、`schema`、`query`、`context`），只读取任务涉及的表；必要时执行一个有界 `SELECT`、`WITH … SELECT` 或 `EXPLAIN`。仅当连接引用显式指定数据库而 CLI 无法选择该数据库，或 CLI 不可用时，回退 DBX MCP。

## 七、依赖工具

先检查 `dbx` CLI；CLI 不可用时再检查 `skill.toml` 中的 MCP `required_tools`。两者都不可用时停止并说明如何安装 `@dbx-app/cli` 或配置外部 DBX MCP。

## 八、业务约束

先通过系统画像匹配连接。未找到时返回：`未找到匹配 connection；请先在 DBX 中配置目标业务系统连接。`

## 九、数据约束

不扩大查询范围，不输出凭据，不把秘密写入需求文档、画像、技能或日志。

## 十、风险

禁止调用 `dbx_add_connection`、`dbx_remove_connection`；禁止写 SQL、危险 SQL、自动连接管理和绕过 Praxis 门禁。

## 十一、验证方法

记录连接引用、Schema 证据、查询边界和调查结论；可复用 SQL 必须登记为需求产出物。

## 十二、知识来源

DBX 工具可用性和连接配置在执行时核对，Praxis 路由器不猜测外部状态。
