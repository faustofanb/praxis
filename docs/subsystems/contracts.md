# contracts

`@praxis/contracts` 当前实现行为。模块定位、依赖方向等架构事实的唯一权威是 `docs/02-system-design.md` §4.1；决策原因见 `docs/decisions/ADR-0009-session-event-contracts-v1.md`。

## 当前内容（M1-T001 起）

入口唯一：`src/index.ts`（深导入被 `test:architecture` 禁止）。运行时依赖只有精确锁定的 zod 4.4.3。无 I/O、无环境变量、无 ID 生成——只做校验与品牌化；生成属于 adapters/CLI（真实随机）与 testkit（确定性）。

- **Branded IDs**（`src/ids.ts`）：`SessionId` / `EventId` / `TurnId` / `StepId` / `ToolExecutionId`，均为非空字符串品牌类型，配 `asXxx(value)` 校验包装函数。
- **EventActor**（`src/actor.ts`）：`user | system | model{provider,model} | tool{toolExecutionId}` 判别联合。actor 是记录事实，不是授权决策。
- **事件信封**（`src/envelope.ts`）：`EVENT_SCHEMA_VERSION = 1`；`sessionEventSchema(type, payloadSchema)` 构造具体事件的 envelope schema（`type` 为 literal，支撑判别联合收窄）。字段：`id, sessionId, seq(正整数), schemaVersion, occurredAt(非负整数毫秒), actor, causationId?, correlationId?`。(sessionId,seq) 唯一、seq 从 1 无空洞等不变量由 EventStore 实现承担，单事件解析不负责。
- **v1 事件词汇**（`src/events/session-events.ts` + `src/events/tool-events.ts`）：Session/Turn 生命周期切片（`SessionCreated(reason?)`, `SessionResumed`, `SessionPaused`, `SessionCompleted`, `TurnStarted(turnId, input?)`, `TurnCompleted(turnId)`；`input` 自 M2-T004 起把打开 turn 的用户输入记为事实）+ 工具执行生命周期切片（M2-T003 起：`ToolProposed(toolExecutionId, name, argumentsJson, effect, toolCallId?)`, `ToolAuthorized`, `ToolRejected(reason)`, `ToolStarted`, `ToolSucceeded(resultJson)`, `ToolFailed(message)`, `ToolIndeterminate(reason)`；`toolCallId` 自 M2-T004 起关联引发它的模型工具调用；M3-T001 起加入 `ToolReconciled(toolExecutionId, outcome: succeeded+resultJson | failed+message | indeterminate+reason)`——reconcile 的结论事实，仅可从 INDETERMINATE 追加，payload 按 `outcome` 判别，见 ADR-0011）。判别联合 `SessionEventUnionSchema` 拒绝词汇外类型。证据事件在 M3–M4 以带 schemaVersion 的成员加入。
- **模型调用事件**（`src/events/model-events.ts`，M2-T004 起；docs/02 §6.2）：`ModelRequestStarted{model}` / `ModelResponseCompleted{text?, toolCalls[]}` / `ModelRequestFailed{kind, retryable, message}`。`toolCalls` 复用 `ToolCallRequest`（id/name/argumentsJson）形状；`kind` 取 `MODEL_PROVIDER_ERROR_KINDS` 规范化枚举。流式 delta 不是 durable 事件；每次 complete 尝试以 Completed 或 Failed 收口。
- **工具词汇与 port**（`src/tools/tool-effect.ts` + `src/ports/tool.ts`，M2-T003 起）：`ToolEffect = read_only | idempotent_write | reconcilable_write | non_idempotent_write`，作为提案事实记录。`ToolDefinition` port：name/description/effect/inputSchema（从 `unknown` 解析）/`parametersJson`（M2-T004 起，面向模型的 JSON Schema 字符串，即 `ModelToolDefinition.parametersJson` 的来源；Core 只要求合法 JSON、原样透传）/`execute(ctx, input)` 返回 `succeeded(resultJson) | failed(error) | indeterminate(reason)`——结果是不透明 JSON 事实，运行时不解析；`failed` 仅当效果确证未发生，未知结果必须 `indeterminate`（docs/02 §8.2 硬规则）。M3-T001 起增加可选 `reconcile(ctx, input)`，返回 `ReconciliationOutcome`（与 `ToolExecutionOutcome` 同一认知规则；只做验证、不得产生新外部效果；`reconcilable_write` 注册时必须定义，`non_idempotent_write` 定义它只为澄清事实、不解锁重试）——ADR-0011。
- **EventStore port**（`src/ports/event-store.ts`）：`append(events, expectedHeadSeq)` + `readStream(sessionId, afterSeq?)`，附 `EventStoreConflictError` 与 `EMPTY_STREAM_HEAD_SEQ = 0`。原子性、(sessionId,seq) 唯一、乐观并发、按 seq 排序等适配器契约写在接口 JSDoc。
- **Model 边界**（`src/model/`，M2-T001 起；决策见 `ADR-0010-model-provider-contract-v1.md`）：
  - `request.ts`：`ModelRequest`（model id、非空 `ModelMessage[]`、tools?、maxOutputTokens?、`providerOptions: Record<string, unknown>` escape hatch、correlationId?）。消息角色 `system | user | assistant | tool` 判别联合；工具参数以 `argumentsJson` 字符串过界，解析归工具运行时。
  - `events.ts`：流式事件 `textDelta | toolCallStart | toolCallDelta | toolCallEnd | usage | completed(finishReason: stop|toolCalls|length) | providerError`，camelCase 判别联合，刻意区别于 PascalCase 持久事件词汇。`providerError` 携带规范化 `kind`（network/rateLimit/invalidRequest/auth/overloaded/timeout/unknown）与 `retryable`，是每次 complete 尝试的终态事实之一。
  - `provider.ts`：`ModelProvider` port——`complete(request, signal): AsyncIterable<ModelEvent>`。取消为协作式静默结束（无 completed、无 providerError、不抛异常）；adapter 归一化 AbortError 并自持 provider 侧重试，Core 只消费规范化失败。

## 测试

- 单元：`tests/contracts-events.test.ts`（信封字段校验、词汇覆盖、判别收窄、port 契约的最小内存实现）。
- 单元：`tests/tool-events.test.ts`（工具事件 schema 校验、effect 枚举、必填 reason/message、词汇外拒绝、M3-T001 起 ToolReconciled payload 判别与变体-字段一致性）。
- 单元：`tests/model-provider.test.ts`（ModelRequest/ModelEvent/providerError 规范化 schema 校验、词汇外类型拒绝、port 形状满足性）。
- 单元：`tests/model-events.test.ts`（M2-T004：模型 durable 事件 schema 校验、toolCalls 默认值、kind 枚举、TurnStarted.input / ToolProposed.toolCallId 可选字段、词汇外拒绝）。
- 属性：`tests/property/contracts-events.property.test.ts`（fast-check：JSON 往返恒等、seq 恰为正整数时接受、词汇外类型拒绝、turnId 保真）。
- 属性：`tests/property/tool-events.property.test.ts`（工具事件 JSON 往返恒等、result payload 往返保真、M3-T001 起三种 reconcile 变体往返恒等）。门：`mise run test:property`。
