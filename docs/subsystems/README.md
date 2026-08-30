# Subsystem Docs

各 subsystem 的**当前实现行为**文档（M8 起全部落地并随任务维护）。

规则（见 `docs/02-system-design.md` 与 `docs/07-architecture-conformance.md`）：

- 模块边界、依赖方向等架构事实的唯一权威是 `docs/02-system-design.md`；本目录只描述实现层细节，并链接到它，不复制它。
- 每个 subsystem 文档描述"现在是什么"，不写变更历史；决策原因归 `docs/decisions/*`。
- as-built 全景（包图 / port→实现 / API 面 / 机器执法清单）见 `docs/12-architecture-current-state.md`。

## 索引

| 文档 | Package | 一句话 |
| --- | --- | --- |
| `contracts.md` | `packages/contracts` | durable 事件词汇 + EventStore/Model/Tool ports（唯一 zod 依赖） |
| `core.md` | `packages/core` | reducer、可恢复 agent loop、context 组装、capability、extension host |
| `store-sqlite.md` | `packages/store-sqlite` | SQLite EventStore（WAL、乐观并发、逐行重校验、单调 migration） |
| `provider-openai.md` | `packages/provider-openai` | Chat Completions 流式 adapter（逃逸法则、providerOptions 透传） |
| `tools-local.md` | `packages/tools-local` | 本地 read/write/bash 工具（capability 强制、reconciliation 钩子） |
| `extension-telemetry.md` | `packages/extension-telemetry` | 只读 telemetry observer 扩展 |
| `extension-standing-orders.md` | `packages/extension-standing-orders` | fail-closed 操作员命令扩展 |
| `testkit.md` | `packages/testkit` | ScriptedModelProvider + 事件工厂 + 内存 store（dev 测试底座） |
| `cli.md` | `apps/cli` | run/sessions 命令、脚本文件 provider、`--model` 真实端点 |
