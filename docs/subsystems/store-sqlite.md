# store-sqlite

`@praxis/store-sqlite` 当前实现行为。架构事实与 schema 权威见 `docs/02-system-design.md` §4.3/§6.3；持久化决策见 ADR-0003。

## 当前内容（M1-T003 起）

入口唯一：`src/index.ts`，唯一构造路径 `openSessionStore(path): SessionStore`（先 migrate 再返回）。`bun:sqlite` 是唯一 SQLite 通道（随 Bun 1.3.14，无新依赖）。`bun:sqlite` 在 `db.ts` 中惰性 require——Node 运行时下仅导入包入口（如 smoke 测试）不会失败，真正开库才需要 Bun。

- **db.ts**：`openDatabase` 打开连接并设置 `strict`（绑定类型检查）、`foreign_keys = ON`、`journal_mode = WAL`。
- **migrations.ts**：显式 SQL migration，单调版本号；`schema_migrations` 表记录已应用版本，版本分歧（降级/未知版本）fail-closed。v1 = docs/02 §6.3 的 sessions/events 两表 + `UNIQUE(session_id, seq)` + `events_session_seq` 索引。
- **session-store.ts**：`SqliteEventStore` 实现 contracts 的 EventStore port：
  - `append(events, expectedHeadSeq)` 单事务：head 检查（乐观并发，冲突抛 `EventStoreConflictError` 回滚）、seq 无间隙递增、事件插入、sessions 元数据（head_seq/status）同事务更新。新流先插入临时 sessions 行满足 FK，事务内不可观察。
  - `readStream(sessionId, afterSeq)`：按 seq 升序读 `seq > afterSeq`，每行经 `SessionEventUnionSchema.parse` 重校验（持久化字节是不可信边界）。
  - append-only：公共面只有 `append/readStream/listSessions/close`，无事件 UPDATE/DELETE 路径。
  - `listSessions()`（M2-T005 起）：sessions 元数据的只读投影（`SessionSummary {sessionId, status, headSeq, updatedAt}`，按 updatedAt/id 稳定排序），供 CLI `sessions` 命令使用；不读事件表。
  - sessions 行是元数据缓存（status 由 Session 生命周期事件类型映射 ACTIVE/PAUSED/COMPLETED），不是事实的替代。

## 测试与运行时

store 套件使用 Bun 原生 test runner（`bun:sqlite` 需要 Bun 运行时；Node vitest 全量切 Bun 存在 zod CJS interop 缺陷，故双运行时分工）：`tests/store/store-sqlite.bun.test.ts`，`*.bun.test.ts` 已从 vitest 收集范围排除。门：`mise run test:store`。

覆盖：分批 append+回读恒等、过期 head 冲突且零写入、间隙批次原子拒绝、重开库 migration 幂等+重放一致、全生命周期经 core reducer 折叠、afterSeq 检查点、损坏行（坏 JSON/未知类型）读取时校验失败、公共面仅四方法（含 listSessions）。
