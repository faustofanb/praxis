# core

`@praxis/core` 当前实现行为。模块定位、依赖方向等架构事实的唯一权威是 `docs/02-system-design.md` §4.2；事件契约形状见 ADR-0009。

## 当前内容（M1-T002 起）

入口唯一：`src/index.ts`。只依赖 `@praxis/contracts`；无 I/O、无时钟、无随机、无环境变量。

- **StateReducer**（`src/state/reducer.ts`）：`reduceSession(state, event) -> nextState` 纯函数，覆盖 Session/Turn、工具执行与模型调用事件切片。docs/02 §7 中 DerivedSessionState 的其余投影（goal/hypotheses/plan/challenge/lastVerification）随 M3–M4 事件词汇落地。
  - `SessionStatus`：`EMPTY | ACTIVE | PAUSED | COMPLETED`；`initialSessionState()` 给出 EMPTY 初态（headSeq 0）。
  - 派生态字段：`sessionId`（由 SessionCreated 绑定）、`headSeq`、`currentTurnId`、`turnIds`（全部出现过的 turn，防复用）、`toolExecutions`（M2-T003 起，`ReadonlyMap<ToolExecutionId, ToolExecutionSnapshot>`，快照含 turnId/name/argumentsJson/effect/status 及终态事实字段 resultJson/rejectionReason/failureMessage/indeterminateReason）、`pendingModelRequest`（M2-T004 起，`{model}`，由 ModelRequestStarted 设置、ResponseCompleted/Failed 清除）。
  - 迁移合法性（fail-closed，抛 `IllegalTransitionError`）：EMPTY 只接受 SessionCreated；Resumed 仅自 PAUSED；Paused/Completed 仅自 ACTIVE 且无未闭合 turn；TurnStarted 仅自 ACTIVE、无未闭合 turn、turnId 未用过；TurnCompleted 必须闭合当前 turn、turnId 一致、无 pending 模型请求、且当前 turn 无 PROPOSED/AUTHORIZED/EXECUTING 中的工具执行。
  - 工具生命周期（docs/02 §8.2）：ToolProposed 需 ACTIVE+open turn 且无 pending 模型请求，toolExecutionId 单用并归属当前 turn；Authorized 仅自 PROPOSED；Rejected 自 PROPOSED（或 AUTHORIZED——仅崩溃恢复放弃：授权未开始可证明未执行，是诚实拒绝而非强转失败）；Started 仅自 AUTHORIZED；三个终态仅自 EXECUTING，终态不可复活；跨 turn 的工具事件拒绝。M3-T001 起 ToolReconciled 仅自 INDETERMINATE（ADR-0011）：`succeeded`/`failed` 落为终态（与执行终态同样不可复活）、`indeterminate` 保持 INDETERMINATE 并更新 reason，未定论前可多次 reconcile；快照新增 `reconciliationCount`（ToolProposed 起 0，每次 reconcile +1）。
  - 模型生命周期（M2-T004）：三个模型事件均需 ACTIVE+open turn；Started 要求无 pending，ResponseCompleted/Failed 要求有 pending（请求-响应严格交替，单写者顺序由 reducer 保证）。
  - 流连续性兜底：事件 seq 必须恰为 headSeq+1（防间隙/重放），事件 sessionId 必须与流一致。这是对 store 契约的廉价防御性复核。
  - `foldSessionEvents(events)`：全流重放辅助，recovery/projection 共用。
- **Tool Runtime 执行器**（`src/tools/tool-runtime.ts`，M2-T003 起）：`executeToolCall(deps, proposal, {signal, authorizer?})`——先经 port 折叠当前状态（要求 ACTIVE + open turn，否则拒绝执行），再按序追加 ToolProposed →（校验/授权）→ ToolAuthorized|ToolRejected → ToolStarted → 终态事件。proposal 可带 `toolCallId`（M2-T004 起）写入 ToolProposed 关联模型调用。时钟与 ID 源注入（Core 无环境时间/随机）；未注册工具按最保守 effect 类提案后显式拒绝；参数不合 schema 在授权前拒绝；`ToolAuthorizer` 判别输入自 M3-T002 起含 `requiredCapability`（来自工具注册元数据，模型提案无法影响）；`readOnlyAuthorizer` 为 v1 默认 deny-by-default 策略（M3 capability 的接缝，`capabilityAuthorizer` 为其上替代实现）。执行器崩溃分支遵守 §8.2：read_only → FAILED，否则 INDETERMINATE（绝不把未知强转为失败）。`projectSessionState(deps)` 经 port 折叠派生态。
- **效果类契约执行**（`src/tools/effect-policy.ts`，M3-T001 起；ADR-0006/0011）：`retryPolicyForEffect(effect)` 全函数表——read_only/idempotent_write→`safe_to_repeat`、reconcilable_write→`repeat_only_after_reconciled_absence`、non_idempotent_write→`never_repeat`；`validateToolDefinitions(tools)` 注册校验（reconcilable_write 缺 reconcile、重名、M3-T002 起写效果工具缺 `requiredCapability` 即抛错——ADR-0007），由 `runTurn` 在任何执行前 fail-closed 调用（直接调 `executeToolCall` 的测试不经此校验）。谁在恢复时调用 reconcile、何时升级，归 M3-T004 的恢复编排。
- **Capability 策略**（`src/capability/policy.ts` + `src/capability/authorizer.ts`，M3-T002 起；docs/02 §9、ADR-0007）：`capabilityDecision(requirement, config, now)` 纯决策表——无 I/O、时钟注入、输入只有 host 提供的 grants/leases（模型可从 `capabilityPolicySummary` 得知所拥有能力，但永远无法授予权限）。fail-closed 判序：① 请求 scope 逃逸出全部 `workspaceRoots` → deny（先于一切 grant，全局 grant 也不能带出 workspace）；② 匹配 grant → allow（via grant）；③ 未过期 lease → allow（via lease 并记 leaseId，供拒绝/审批引用证据）；④ 匹配但已过期 lease → 无条件 deny（docs/02 §9.2：过期即拒，`now === expiresAt` 已过期，无宽限）；⑤ approvable 能力 → requires_approval（携 ApprovalRequest）；⑥ 其余 → deny。`capabilityPolicySummary(config, now)` 确定性投影——grants 排序列出、lease 标注 `expires N`/`EXPIRED`、approvable 明示"re-proposing does not grant them"。`capabilityAuthorizer({policy, now})` 把决策表适配到 ToolAuthorizer 接缝（§9.3 第 1 层；第 2 层路径/root 限制在工具实现，M3-T003）：requires_approval 直接 rejected fail-closed（审批 UX 是扩展，缺位不得开门）；写效果工具无 requiredCapability 到达运行时 → rejected（注册校验之外的纵深防御）。
- **Agent Loop**（`src/agent-loop/`，M2-T004 起；docs/02 §10–12、§16–17）：
  - `conversation.ts`：`projectConversation(events)` 纯投影——TurnStarted.input→user 消息、ModelResponseCompleted→assistant 消息、工具终态事件→tool 消息（succeeded 直引 resultJson，rejected/failed/indeterminate 以 `{status, reason|message}` JSON 记述；未关联 toolCallId 的执行回落到 toolExecutionId）。M3-T001 起 ToolReconciled 作为追加的 tool 事实投影（`{status: outcome, reconciled: true, result|message|reason}`）——模型看到定论事实，但早先的 indeterminate 消息保留，历史不被改写。重放安全：不解析参数、不重执行工具、结果作为不透明事实入上下文。
  - `run-turn.ts`：`runTurn(deps, {input?}, {signal, guards?, authorizer?, budget?})`——入口先做诚实崩溃恢复：悬挂 EXECUTING→ToolIndeterminate（"outcome unknown"）、悬挂 PROPOSED/AUTHORIZED→ToolRejected（明确"never executed"）、悬挂 pendingModelRequest→ModelRequestFailed（kind unknown）；绝不假设未执行、绝不重放历史工具。随后循环：projectConversation → buildContext → ModelRequestStarted → 消费流 → ResponseCompleted（工具调用则逐个 executeToolCall 并继续；纯文本则 TurnCompleted 收口）/ providerError 记 ModelRequestFailed（可重试在同 turn 内重试）/ 静默结束（取消）记 ModelRequestFailed 并返回 cancelled。
  - 守卫 `TurnGuards`（maxStepsPerTurn=16、maxConsecutiveModelFailures=3，`validateTurnGuards` fail-closed）：确定性预算按每次 runTurn 计——暂停后重入即恢复（同一 open turn 续跑，无新 TurnStarted）。超限返回 `paused`（turn 保持 open，Session 状态不变——reducer 禁止带 open turn 的 SessionPaused，这是记录在案的 v0 偏差：暂停是进程内结果而非会话状态迁移）。open turn 时传 input 拒绝；无 open turn 时缺 input 拒绝；工具 parametersJson 非合法 JSON 在任何事件追加前拒绝。
- **ContextBuilder v0**（`src/context/`，M2-T002 起；设计见 docs/02 §12、docs/03 M2.2）：
  - `budget.ts`：`ContextBudget` 四项硬上限（maxRecentMessages / maxFragmentBytes / maxToolResultBytes / maxEstimatedTokens）+ `DEFAULT_CONTEXT_BUDGET`；`validateContextBudget` fail-closed（正整数、字节上限 ≥ 40 以容纳截断标记）。
  - `builder.ts`：`buildContext(input, budget?)` 纯投影——system 片段恒为第一条（history 内出现 system 消息即 `InvalidContextError`），history 取最新窗口、按片段截断（保头 + `…[+N bytes truncated]` 标记，UTF-8 字节感知），超出 token 估计上限（全部字符串字段的字节和 / 4 向上取整）时自最旧丢弃；尾消息不可丢弃，system+尾消息仍超限则抛 `ContextBudgetExceededError`。返回带 estimate（totalBytes/estimatedTokens/droppedMessages/truncatedFragments）。
  - 截断后的 assistant 工具参数仅作上下文展示——可执行工具状态在事件库中，绝不从 context 反解。v1 无检索、无摘要（§12.3 明确后置）。

## 测试

- 单元：`tests/reducer.test.ts`（合法生命周期、每个非法迁移、流连续性、纯度/确定性）。
- 单元：`tests/reducer-tools.test.ts`（工具生命周期合法路径、REJECTED/FAILED/INDETERMINATE 终态、TurnCompleted 阻塞、全部非法迁移；M3-T001 起 reconcile 三种落点/未定论重复 reconcile/各非法源状态/终态不可复活/闭 turn 与 PAUSED 拒绝）。
- 单元：`tests/effect-policy.test.ts`（M3-T001：重试策略表全量映射、注册校验——reconcilable_write 缺 reconcile 拒绝、non_idempotent_write 带 reconcile 合法、重名拒绝；M3-T002 起写效果工具缺 requiredCapability 拒绝、read-only 可省略）。
- 单元：`tests/capability-policy.test.ts`（M3-T002：决策表全路径——逃逸 deny/grant allow/lease allow 记 leaseId/过期边界 deny/requires_approval/未授予 deny/错名错 scope lease 不满足；scope 规范化与段前缀包含；authorizer 四路映射；summary 确定性/EXPIRED/空策略）。
- 单元：`tests/reducer-model.test.ts`（M2-T004：模型事件合法迁移、pendingModelRequest 交替、无 pending 响应拒绝、TurnCompleted/ToolProposed 阻塞、纯度）。
- 单元：`tests/agent-loop.test.ts`（M2-T004：runTurn 垂直行为——纯文本收口、工具往返回灌、失败重试、连续失败暂停、open-turn 恢复、取消、步数预算、fail-fast 前置校验、projectConversation 投影）。
- 单元：`tests/context-builder.test.ts`（组成顺序、窗口、字节感知截断、最旧优先丢弃、预算校验、确定性、输出 schema 合法性）。
- 故障：`tests/fault/tool-runtime.fault.test.ts`（store 崩溃后重放见真实 EXECUTING 态、read_only 崩溃→FAILED、write 崩溃→INDETERMINATE、未知外部效果一等公民）。
- 故障：`tests/fault/agent-loop.fault.test.ts`（M2-T004：provider 崩溃留可恢复 pending 请求、store 崩溃留合法流、授权后崩溃恢复为显式拒绝）。门：`mise run test:fault`。
- 属性：`tests/property/reducer.property.test.ts`（影子模型一致性、fold 确定性、单点 seq 扰动拒绝、相邻交换拒绝）。
- 属性：`tests/property/context-builder.property.test.ts`（成功构建必不超任何上限、保留历史是输入的保序后缀且以尾消息收尾、确定性）。门：`mise run test:property`。
- 重放：`tests/fixtures/replay/agent-loop-recovery-v1.json` + `tests/replay/replay.test.ts`（M2-T004：崩溃-恢复全路径 fixture 经公共 schema 加载、中段检查点折叠为可恢复悬挂态、双折叠一致）。门：`mise run test:replay`。
- 重放：`tests/fixtures/replay/tool-reconciliation-v1.json`（M3-T001：INDETERMINATE→两次 reconcile 落 SUCCEEDED、另一次执行经 reconcile 落 FAILED 的全路径 fixture；pre-reconcile 检查点保持诚实 INDETERMINATE）。
- 集成：`tests/integration/session-reducer.integration.test.ts`（reducer × EventStore port：乐观并发 append、readStream 检查点、增量折叠与全量重放一致）。
- 集成：`tests/integration/context-builder.integration.test.ts`（构建结果 → ModelRequestSchema → ScriptedModelProvider 端到端消费）。
- 集成：`tests/integration/tool-runtime.integration.test.ts`（read_file 经执行器成为 durable 事实并进入下一次 context）。
- 集成：`tests/integration/agent-loop-recovery.integration.test.ts`（M2-T004：真实 tools-local × runTurn——悬挂 EXECUTING 恢复为 INDETERMINATE 且不重执行、全新会话完整工具往返）。
- 集成：`tests/integration/capability-runtime.integration.test.ts`（M3-T002：grant→授权执行落 SUCCEEDED；lease 存活执行、过期一拍即 ToolRejected 且 headSeq 停在 4；requires_approval 落 durable ToolRejected 事实；逃逸 scope 在 ToolStarted 之前拒绝）。门：`mise run test:integration`。
- 安全：`tests/security/capability-policy.security.test.ts`（M3-T002 对抗矩阵：`..` 逃逸抛错不 resolve、`/work`≠`/workspace` 段前缀、过期零宽限、错名/错 scope lease、重提案 N 次拒绝理由逐字相同且 execute 计数为 0、argumentsJson 无法影响授权、无 requiredCapability 的写工具纵深防御拒绝）。门：`mise run test:security`。
