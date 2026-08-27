# contracts

`@praxis/contracts` 当前实现行为。模块定位、依赖方向等架构事实的唯一权威是 `docs/02-system-design.md` §4.1；决策原因见 `docs/decisions/ADR-0009-session-event-contracts-v1.md`。

## 当前内容（M1-T001 起）

入口唯一：`src/index.ts`（深导入被 `test:architecture` 禁止）。运行时依赖只有精确锁定的 zod 4.4.3。无 I/O、无环境变量、无 ID 生成——只做校验与品牌化；生成属于 adapters/CLI（真实随机）与 testkit（确定性）。

- **Branded IDs**（`src/ids.ts`）：`SessionId` / `EventId` / `TurnId` / `StepId` / `ToolExecutionId`，均为非空字符串品牌类型，配 `asXxx(value)` 校验包装函数。
- **EventActor**（`src/actor.ts`）：`user | system | model{provider,model} | tool{toolExecutionId}` 判别联合。actor 是记录事实，不是授权决策。
- **事件信封**（`src/envelope.ts`）：`EVENT_SCHEMA_VERSION = 1`；`sessionEventSchema(type, payloadSchema)` 构造具体事件的 envelope schema（`type` 为 literal，支撑判别联合收窄）。字段：`id, sessionId, seq(正整数), schemaVersion, occurredAt(非负整数毫秒), actor, causationId?, correlationId?`。(sessionId,seq) 唯一、seq 从 1 无空洞等不变量由 EventStore 实现承担，单事件解析不负责。
- **v1 事件词汇**（`src/events/session-events.ts`）：仅 Session/Turn 生命周期切片——`SessionCreated(reason?)`, `SessionResumed`, `SessionPaused`, `SessionCompleted`, `TurnStarted(turnId)`, `TurnCompleted(turnId)`。判别联合 `SessionEventUnionSchema` 拒绝词汇外类型。模型调用/证据/工具执行事件在 M2–M4 以带 schemaVersion 的成员加入。
- **工具执行状态**（`src/tool-state.ts`）：`PROPOSED | AUTHORIZED | REJECTED | EXECUTING | SUCCEEDED | FAILED | INDETERMINATE`。迁移合法性归 Core reducer；timeout ≠ 自动 FAILED、INDETERMINATE 不盲目重试的硬规则见 docs/02 §8.2。
- **EventStore port**（`src/ports/event-store.ts`）：`append(events, expectedHeadSeq)` + `readStream(sessionId, afterSeq?)`，附 `EventStoreConflictError` 与 `EMPTY_STREAM_HEAD_SEQ = 0`。原子性、(sessionId,seq) 唯一、乐观并发、按 seq 排序等适配器契约写在接口 JSDoc。

## 测试

- 单元：`tests/contracts-events.test.ts`（信封字段校验、词汇覆盖、判别收窄、port 契约的最小内存实现）。
- 属性：`tests/property/contracts-events.property.test.ts`（fast-check：JSON 往返恒等、seq 恰为正整数时接受、词汇外类型拒绝、turnId 保真）。门：`mise run test:property`。
