# core

`@praxis/core` 当前实现行为。模块定位、依赖方向等架构事实的唯一权威是 `docs/02-system-design.md` §4.2；事件契约形状见 ADR-0009。

## 当前内容（M1-T002 起）

入口唯一：`src/index.ts`。只依赖 `@praxis/contracts`；无 I/O、无时钟、无随机、无环境变量。

- **StateReducer**（`src/state/reducer.ts`）：`reduceSession(state, event) -> nextState` 纯函数，覆盖 Session/Turn 与工具执行事件切片。docs/02 §7 中 DerivedSessionState 的其余投影（goal/hypotheses/plan/challenge/lastVerification）随 M2–M4 事件词汇落地。
  - `SessionStatus`：`EMPTY | ACTIVE | PAUSED | COMPLETED`；`initialSessionState()` 给出 EMPTY 初态（headSeq 0）。
  - 派生态字段：`sessionId`（由 SessionCreated 绑定）、`headSeq`、`currentTurnId`、`turnIds`（全部出现过的 turn，防复用）、`toolExecutions`（M2-T003 起，`ReadonlyMap<ToolExecutionId, ToolExecutionSnapshot>`，快照含 turnId/name/argumentsJson/effect/status 及终态事实字段 resultJson/rejectionReason/failureMessage/indeterminateReason）。
  - 迁移合法性（fail-closed，抛 `IllegalTransitionError`）：EMPTY 只接受 SessionCreated；Resumed 仅自 PAUSED；Paused/Completed 仅自 ACTIVE 且无未闭合 turn；TurnStarted 仅自 ACTIVE、无未闭合 turn、turnId 未用过；TurnCompleted 必须闭合当前 turn、turnId 一致、且当前 turn 无 PROPOSED/AUTHORIZED/EXECUTING 中的工具执行。
  - 工具生命周期（docs/02 §8.2）：ToolProposed 需 ACTIVE+open turn，toolExecutionId 单用并归属当前 turn；Authorized/Rejected 仅自 PROPOSED；Started 仅自 AUTHORIZED；三个终态仅自 EXECUTING，终态不可复活；跨 turn 的工具事件拒绝。
  - 流连续性兜底：事件 seq 必须恰为 headSeq+1（防间隙/重放），事件 sessionId 必须与流一致。这是对 store 契约的廉价防御性复核。
  - `foldSessionEvents(events)`：全流重放辅助，recovery/projection 共用。
- **Tool Runtime 执行器**（`src/tools/tool-runtime.ts`，M2-T003 起）：`executeToolCall(deps, proposal, {signal, authorizer?})`——先经 port 折叠当前状态（要求 ACTIVE + open turn，否则拒绝执行），再按序追加 ToolProposed →（校验/授权）→ ToolAuthorized|ToolRejected → ToolStarted → 终态事件。时钟与 ID 源注入（Core 无环境时间/随机）；未注册工具按最保守 effect 类提案后显式拒绝；参数不合 schema 在授权前拒绝；`readOnlyAuthorizer` 为 v1 默认 deny-by-default 策略（M3 capability 的接缝）。执行器崩溃分支遵守 §8.2：read_only → FAILED，否则 INDETERMINATE（绝不把未知强转为失败）。`projectSessionState(deps)` 经 port 折叠派生态。
- **ContextBuilder v0**（`src/context/`，M2-T002 起；设计见 docs/02 §12、docs/03 M2.2）：
  - `budget.ts`：`ContextBudget` 四项硬上限（maxRecentMessages / maxFragmentBytes / maxToolResultBytes / maxEstimatedTokens）+ `DEFAULT_CONTEXT_BUDGET`；`validateContextBudget` fail-closed（正整数、字节上限 ≥ 40 以容纳截断标记）。
  - `builder.ts`：`buildContext(input, budget?)` 纯投影——system 片段恒为第一条（history 内出现 system 消息即 `InvalidContextError`），history 取最新窗口、按片段截断（保头 + `…[+N bytes truncated]` 标记，UTF-8 字节感知），超出 token 估计上限（全部字符串字段的字节和 / 4 向上取整）时自最旧丢弃；尾消息不可丢弃，system+尾消息仍超限则抛 `ContextBudgetExceededError`。返回带 estimate（totalBytes/estimatedTokens/droppedMessages/truncatedFragments）。
  - 截断后的 assistant 工具参数仅作上下文展示——可执行工具状态在事件库中，绝不从 context 反解。v1 无检索、无摘要（§12.3 明确后置）。

## 测试

- 单元：`tests/reducer.test.ts`（合法生命周期、每个非法迁移、流连续性、纯度/确定性）。
- 单元：`tests/reducer-tools.test.ts`（工具生命周期合法路径、REJECTED/FAILED/INDETERMINATE 终态、TurnCompleted 阻塞、全部非法迁移）。
- 单元：`tests/context-builder.test.ts`（组成顺序、窗口、字节感知截断、最旧优先丢弃、预算校验、确定性、输出 schema 合法性）。
- 故障：`tests/fault/tool-runtime.fault.test.ts`（store 崩溃后重放见真实 EXECUTING 态、read_only 崩溃→FAILED、write 崩溃→INDETERMINATE、未知外部效果一等公民）。门：`mise run test:fault`。
- 属性：`tests/property/reducer.property.test.ts`（影子模型一致性、fold 确定性、单点 seq 扰动拒绝、相邻交换拒绝）。
- 属性：`tests/property/context-builder.property.test.ts`（成功构建必不超任何上限、保留历史是输入的保序后缀且以尾消息收尾、确定性）。门：`mise run test:property`。
- 集成：`tests/integration/session-reducer.integration.test.ts`（reducer × EventStore port：乐观并发 append、readStream 检查点、增量折叠与全量重放一致）。
- 集成：`tests/integration/context-builder.integration.test.ts`（构建结果 → ModelRequestSchema → ScriptedModelProvider 端到端消费）。门：`mise run test:integration`。
