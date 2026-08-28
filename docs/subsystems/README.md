# Subsystem Docs

各 subsystem 的**当前实现行为**文档，随对应 package 的实现逐步建立（M1+）。

规则（见 `docs/02-system-design.md` 与 `.agents/rules/documentation.md`）：

- 模块边界、依赖方向等架构事实的唯一权威是 `docs/02-system-design.md`；本目录只描述实现层细节，并链接到它，不复制它。
- 每个 subsystem 文档描述"现在是什么"，不写变更历史；决策原因归 `docs/decisions/*`。

## 索引

| 文档 | Package | 状态 |
| --- | --- | --- |
| `contracts.md` | `packages/contracts` | 进行中（M2：ids/信封/Session-Turn 与工具事件词汇/EventStore/Tool/Model 边界已落地） |
| `core.md` | `packages/core` | 进行中（M2：StateReducer（含工具/模型投影）、ContextBuilder v0、只读工具执行器、可恢复 Agent Loop 已落地） |
| `store-sqlite.md` | `packages/store-sqlite` | 进行中（M1：SQLite EventStore 适配器已落地） |
| `provider-openai.md` | `packages/provider-openai` | 未开始（M2.4） |
| `tools-local.md` | `packages/tools-local` | 进行中（M2：read_file/list_dir 已落地） |
| `testkit.md` | `packages/testkit` | 进行中（M2：ScriptedModelProvider 已落地） |
| `cli.md` | `apps/cli` | 进行中（M2：run/sessions 命令 + 脚本文件 provider 已落地） |
