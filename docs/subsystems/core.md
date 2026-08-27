# core

`@praxis/core` 当前实现行为。模块定位、依赖方向等架构事实的唯一权威是 `docs/02-system-design.md` §4.2；事件契约形状见 ADR-0009。

## 当前内容（M1-T002 起）

入口唯一：`src/index.ts`。只依赖 `@praxis/contracts`；无 I/O、无时钟、无随机、无环境变量。

- **StateReducer**（`src/state/reducer.ts`）：`reduceSession(state, event) -> nextState` 纯函数，覆盖 v1 Session/Turn 事件切片。docs/02 §7 中 DerivedSessionState 的其余投影（goal/hypotheses/plan/challenge/toolExecutions/lastVerification）随 M2–M4 事件词汇落地。
  - `SessionStatus`：`EMPTY | ACTIVE | PAUSED | COMPLETED`；`initialSessionState()` 给出 EMPTY 初态（headSeq 0）。
  - 派生态字段：`sessionId`（由 SessionCreated 绑定）、`headSeq`、`currentTurnId`、`turnIds`（全部出现过的 turn，防复用）。
  - 迁移合法性（fail-closed，抛 `IllegalTransitionError`）：EMPTY 只接受 SessionCreated；Resumed 仅自 PAUSED；Paused/Completed 仅自 ACTIVE 且无未闭合 turn；TurnStarted 仅自 ACTIVE、无未闭合 turn、turnId 未用过；TurnCompleted 必须闭合当前 turn 且 turnId 一致。
  - 流连续性兜底：事件 seq 必须恰为 headSeq+1（防间隙/重放），事件 sessionId 必须与流一致。这是对 store 契约的廉价防御性复核。
  - `foldSessionEvents(events)`：全流重放辅助，recovery/projection 共用。

## 测试

- 单元：`tests/reducer.test.ts`（合法生命周期、每个非法迁移、流连续性、纯度/确定性）。
- 属性：`tests/property/reducer.property.test.ts`（影子模型一致性、fold 确定性、单点 seq 扰动拒绝、相邻交换拒绝）。
- 集成：`tests/integration/session-reducer.integration.test.ts`（reducer × EventStore port：乐观并发 append、readStream 检查点、增量折叠与全量重放一致）。门：`mise run test:integration`。
