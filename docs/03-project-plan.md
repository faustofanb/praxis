# Praxis Harness v1 项目规划书

**目的：**把“设计正确”转化为“持续可交付”。本文管理工作拆分、阶段依赖、任务规范、验收条件和发布门，不给出虚假的日历承诺。

---

# 1. 规划原则

1. **垂直切片优先**：每个 Milestone 尽量产出可运行链路，而不是先写一堆空接口；
2. **确定性 Core 先于智能特性**；
3. **先恢复/重放，再复杂推理**；
4. **先 read-only，再真实写副作用**；
5. **每个阶段必须有 Exit Criteria**，不以“代码差不多了”判断完成；
6. **风险越高，越晚进入**；
7. **每个阶段都允许推翻后续规划，但必须有测试/实现证据**；
8. **AI 产生的代码不降低 Review/DoD 标准**。

---

# 2. 版本目标

## v0.x 开发期

允许 breaking changes，但任何持久化 schema 变更仍必须显式 migration/fixture 处理；不能以“还没发布”为理由形成无法测试的数据垃圾。

## v1.0 定义

v1.0 不是“所有白皮书功能完成”，而是达到：

- 一个本地 CLI；
- 一个完整可恢复 Agent Loop；
- SQLite Event Store；
- OpenAI provider；
- read/write/bash 本地工具；
- Capability policy；
- UNKNOWN/reconciliation；
- Observation/Hypothesis/Plan/Challenge 基础事件；
- 完整 integration/replay/fault/security CI；
- 文档与 AI 开发规则可持续。

Multi-Agent、Emergency Command、长期 Drift AI 不属于 v1.0。

---

# 3. Work Breakdown Structure

## M0 — Repository Foundation

**目标：**代码出现之前，先让环境、规则和 CI 可复现。

### M0.1 仓库初始化

- [x] Bun workspace 目录；
- [x] `mise.toml` / `mise.lock`；
- [x] `package.json` exact pins；
- [x] `bun.lock`；
- [x] `tsconfig.base.json`；
- [x] Biome；
- [x] Vitest；
- [x] fast-check；
- [x] Knip；
- [x] Lefthook；
- [x] commitlint。

### M0.2 文档治理

- [x] root `AGENTS.md`；
- [x] `CONTRIBUTING.md`；
- [x] architecture/system design；
- [x] ADR template；
- [x] PR template；
- [x] AI skills/rules；
- [x] `docs/subsystems/` skeleton。

### M0.3 CI

最少：

```text
install --frozen
format/lint
typecheck
unit test
knip
commit message/PR checks
```

### Exit Criteria

- 新 clone 执行一条 bootstrap 流程即可得到一致环境；
- `mise run check:all` 通过；
- 所有依赖 exact pin；
- 空 workspace 能构建/测试；
- AI 开发规则已经可用；
- ADR-0001~0008 至少建 skeleton/accepted decision。

---

# 4. M1 — Deterministic Session Kernel

**目标：**先建立“事实和状态不会乱”的内核，不接真实 LLM。

### M1.1 Contracts

- [ ] IDs；
- [ ] Event envelope；
- [ ] session/turn events；
- [ ] Tool execution state union；
- [ ] EventStore port；
- [ ] Zod schema。

### M1.2 Reducer

- [ ] `initialState()`；
- [ ] event reducer；
- [ ] illegal transition checks；
- [ ] deterministic fake clock/ID for tests。

### M1.3 SQLite Event Store

- [ ] schema migration runner；
- [ ] append transaction；
- [ ] monotonic seq；
- [ ] load/replay；
- [ ] SQLite fixtures。

### M1.4 Tests

- [ ] reducer unit tests；
- [ ] state-machine property tests；
- [ ] append concurrency test；
- [ ] replay determinism；
- [ ] old/unknown schema failure test。

### Exit Criteria

给定 event stream，可在内存和 SQLite 两种 store 上得到完全一致 state；随机生成合法 event sequence 不破坏 invariant；非法 transition 必须显式失败。

---

# 5. M2 — Minimal Read-Only Agent Loop

**目标：**第一个真正可运行的 AI 垂直链路，仍避免危险副作用。

### M2.1 Model Port + Scripted Provider

- [ ] `ModelProvider`；
- [ ] streaming normalized events；
- [ ] ScriptedModel test implementation；
- [ ] cancellation。

### M2.2 Context Builder v0

- [ ] system fragment；
- [ ] user message；
- [ ] recent history；
- [ ] tool schema；
- [ ] hard byte/token estimate cap。

### M2.3 Tool Runtime read-only

- [ ] `ToolProposed` -> authorization -> `ToolStarted` -> terminal；
- [ ] `read_file`；
- [ ] `list_dir`（可选）；
- [ ] output truncation。

### M2.4 OpenAI Provider

- [ ] Responses API adapter；
- [ ] tool call mapping；
- [ ] usage/error mapping；
- [ ] real API smoke test（非阻塞 CI）。

### M2.5 CLI

- [ ] create session；
- [ ] send prompt；
- [ ] stream model/tool events；
- [ ] resume session；
- [ ] list session ids（可简单）。

### Exit Criteria

下面链路可重复通过集成测试：

```text
user -> model -> read_file -> model -> final
```

进程退出后 resume，模型可从 Event Store 重建上下文继续，不重执行历史 read tool。

---

# 6. M3 — Safe Side Effects

**目标：**允许写操作，但首先把失败语义做正确。

### M3.1 Effect classes

- [ ] `read_only`；
- [ ] `idempotent_write`；
- [ ] `reconcilable_write`；
- [ ] `non_idempotent_write`。

### M3.2 Capability Policy

- [ ] fs.read/fs.write/shell.exec；
- [ ] workspace scope；
- [ ] allow/deny/requires_approval；
- [ ] lease expiration；
- [ ] model-visible policy projection。

### M3.3 Tools

- [ ] `write_file`：temp + atomic replace/可 reconcile；
- [ ] `bash`：cwd/timeout/output cap/cancel；
- [ ] path escape protection；
- [ ] command telemetry。

### M3.4 UNKNOWN

- [ ] `ToolIndeterminate`；
- [ ] process crash simulation；
- [ ] reconcile API；
- [ ] non-idempotent blind retry prohibition。

### Exit Criteria

故障注入在“side effect 已发生但 result event 未落盘”窗口时，恢复后不会自动重复危险操作；系统能明确停在 `INDETERMINATE` 或通过 reconcile 恢复事实。

---

# 7. M4 — Epistemic Runtime

**目标：**验证 Praxis 与普通 Agent Loop 的真正差异，但保持轻量。

### M4.1 Events/State

- [x] `GoalSet`（M4-T001，ADR-0012——Plan.goalRef 需要它，M4.2 投影读取它）；
- [x] `ObservationRecorded`；
- [x] `HypothesisProposed`；
- [x] `HypothesisStatusChanged`；
- [x] `PlanSet`；
- [x] `PlanInvalidated`；
- [x] `ChallengeRaised/Resolved`；
- [x] `VerificationRecorded`。

### M4.2 Context Projection

模型明确看到（M4-T002，`projectEpistemicBrief` 结构化分节，详见 docs/02 §12.4）：

- [x] current goal/constraints；
- [x] active plan；
- [x] observations 与 hypotheses 分区（inactive hypothesis 不进入；observations 按 cap 取最新）；
- [x] open challenge；
- [x] pending indeterminate action。

### M4.3 Plan semantics

Plan 必须支持（M4-T003，详见 docs/02 §5.4 运行时决定）：

- [x] current hypothesis；
- [x] next action；
- [x] falsification condition；
- [x] invalidation（证伪/取代假设 → 入口 pass 追加 PlanInvalidated 事实，不依赖模型自觉）。

### M4.4 Challenge

- [x] Challenge target/evidence refs；
- [x] unresolved completion blocking（按 policy；v1 policy 即法则本身，见 docs/02 §14）；
- [x] accept -> plan/hypothesis update（M4-T003 入口 pass）；
- [x] reject requires reason event。

### Exit Criteria

至少有三组 scripted scenario 证明：

1. 新 evidence 可以 falsify hypothesis；
2. plan 被 invalidated 后不会继续执行旧 next action；
3. challenge 可以改变 session path，而不是只成为日志。

---

# 8. M5 — Recovery, Bounds & Session Evolution

**目标：**保证系统能长期工作，而非只跑 demo。

### M5.1 Context bounds

- [x] max fragments（M2-T002 起 `maxFragmentBytes`；M5-T001 起 brief 总字节同受此界）；
- [x] max tool output（M2-T002 起 `maxToolResultBytes`）；
- [x] max history（M2-T002 起 `maxRecentMessages` + token 上限最旧先丢）；
- [x] structured non-compactable state（M5-T001：12.2 条目入不可压缩层，永不被字节压力逐出；可压缩分节计数封顶、整节让位、诚实计数；不可压缩层超限 fail closed）；
- [x] deterministic summary/简单 compaction strategy（M5-T002：窗口丢弃触发 `## Compacted history` 确定性按角色计数 recap，计入 fail-closed 组合界；零丢弃逐字节等同 M5-T001 投影；event store 永远全量保留）。

### M5.2 Replay fixtures

- [x] 版本化 session fixtures（M5-T003：envelope `schemaVersion` 版本窗口 fail closed + `tests/fixtures/replay/index.json` 清单为集合唯一权威，加载一律走 `parseReplayStream` 缝隙）；
- [x] migration tests（M5-T003：连续递增步进迁移表 + 管线盖章版本；合成 v1→v2 drill 证明迁移后真实 fixture 折叠到同一 derived state；未来版本流加载即拒）；
- [x] regression session collection（M5-T003：开篇 493 事件混合会话 fixture，由确定性构造器再生并以规范化 JSON 相等 pin）。

### M5.3 Crash matrix

逐边界注入（M5-T004 全部落格并勾选；法则表以 docs/02 §17 崩溃矩阵为唯一权威，`tests/fault/crash-matrix.fault.test.ts` 逐格注入 + `tests/store/crash-recovery.bun.test.ts` 真实 SQLite 关闭/重开证据）：

- [x] before append（ToolProposed 未落盘：零执行、模型重问、无恢复事实）；
- [x] before execute（dangling PROPOSED/AUTHORIZED → 显式 `ToolRejected`，从未执行）；
- [x] after side effect（executor 崩溃 → 当回合诚实 `ToolIndeterminate`，下一入口 reconcile 落定，不重复执行）；
- [x] before result append（结果在手落盘崩溃 → dangling EXECUTING → indeterminate-then-reconciled，绝不采信死进程内存结果）；
- [x] after result append（终态 durable → 恢复零追加，恰好执行一次）；
- [x] 附加格：混合 dangling 插入序、恢复幂等（后续 turn 零恢复事实）、§17 第 9 步人工解锁环（SessionResumed 重试 reconciliation）、持久存储关闭/重开全流程恢复。

### M5.4 Fork（如实现成本合适）

- [ ] fork metadata；
- [ ] copy-on-history semantics；
- [ ] old session immutable history。

M5 里程碑验收时**明确推迟**（证据与复评时点见 `docs/acceptance/M5.md` 推迟记录）：fork 需要新持久事件词汇 → 首次真实 schema 版本升级 + 迁移步 + ADR，成本对 optional 特性不可接受；docs/02 §15 的 "v1 后半段" 时序不因此违反（resume 半已交付）。

### Exit Criteria

长 Session 不无限扩大 model context；所有不可压缩约束仍存在；旧 fixture 可恢复；crash matrix 无重复危险 side effect。

---

# 9. M6 — Extension Seams

**目标：**证明 Core 可扩展，但不实现“大而全插件框架”。

### Tasks

- [x] 六类稳定 hook（M6-T001：八 hook 全落 `packages/contracts/src/extensions.ts` + core host/接缝，ADR-0013）；
- [x] context contributor（M6-T001：`contributeContext` → `## Extension: <name>` 节，走 M5-T001 上限组合法则，host 盖 source 防冒名）；
- [x] tool registration（M6-T003：v1 无注册新工具的 hook——`packages/extension-standing-orders` 经 tool 生命周期 seam 演示 deny（组合于 authorizer 之后）+ context 贡献，fail_closed 格落地，工具由应用持有；见 ADR-0013 拒绝清单）；
- [x] event observer（M6-T001：`onEvent` 经 observing-store 装饰器在每次 append 成功后触发，只读）；
- [x] extension failure semantics（M6-T001：`isolate`/`fail_closed` 每 extension 声明，fail_closed 骑 §17 既有崩溃恢复）；
- [x] sample extension：只读 telemetry（M6-T002：`packages/extension-telemetry` 六观察 hook + 结构化 redaction 快照，core/contracts 零改动；simple plan renderer 归 M6-T003 样例一并考虑）。

### Non-goals

- Multi-Agent production implementation；
- Emergency command；
- self-modifying plugin system；
- arbitrary event interception everywhere。

### Exit Criteria

一个 out-of-core extension 可在不修改 `packages/core` 的情况下注册工具/贡献 context/观察 event；卸载后不残留 mutable global state。

---

# 10. M7 — Quality Hardening

**目标：**把“能跑”提升成“可信”。

### Quality Gates

- [ ] Core branch/statement coverage target；
- [x] fast-check state machine suite（M7-T001：`tests/property/state-machine.property.test.ts` + 独立影子模型 `tests/helpers/full-vocabulary-machine.ts`——全词汇表模型一致性/前缀结构不变量/任意切分点恢复恒等/前置条件违例拒绝/终态吸收）；
- [ ] fault injection suite；
- [ ] security bypass suite；
- [ ] soak 10k+ synthetic turns；
- [ ] Knip zero unexpected findings；
- [ ] memory/context growth report；
- [ ] SQLite corruption/recovery policy documented；
- [ ] dependency license inventory；
- [ ] Bun 1.4 compatibility branch test（不自动升级）。

### Exit Criteria

没有 P0/P1 known correctness bug；`check:all` 稳定；失败可以重放；真实模型 e2e 不影响 Core correctness CI 稳定性。

---

# 11. M8 — v1 Release Candidate

### Deliverables

- [ ] CLI quickstart；
- [ ] architecture current-state docs；
- [ ] subsystem docs；
- [ ] API docs；
- [ ] sample session/replay；
- [ ] threat/limitation document；
- [ ] release checklist；
- [ ] v1 non-goals locked；
- [ ] benchmark/eval baseline；
- [ ] changelog。

### v1 RC Acceptance

能够演示并重放：

1. read-only coding/research style task；
2. safe file write task；
3. simulated indeterminate external effect；
4. hypothesis falsification + replan；
5. challenge blocks/changes completion；
6. process crash + resume。

---

# 12. Task 规范

每个 Issue/Task 使用：

```text
ID: PRA-###
Title: <problem-oriented title>
Milestone: M#
Priority: P0/P1/P2/P3
Type: feature/fix/refactor/test/docs/build
Owner: human/agent
Dependencies: PRA-###
```

正文模板：

```markdown
## Problem
当前哪个真实行为不满足设计？

## Evidence
日志、测试、trace、代码事实。

## Scope
本任务修改哪些模块。

## Non-goals
明确不做什么。

## Acceptance Criteria
可客观验证的结果。

## Required Tests
unit/integration/replay/fault/security 中哪些必须新增。

## Docs / ADR
是否需要更新。
```

禁止以“实现 XXX 类/添加 XXX abstraction”为 Problem；Problem 应描述用户/系统行为缺口。

---

# 13. Priority

- **P0**：可能造成状态失真、重复不可逆副作用、权限绕过、错误成功、数据损坏；
- **P1**：核心 Agent Loop/恢复不可用，严重正确性缺陷；
- **P2**：正常功能/可维护性问题，有 workaround；
- **P3**：优化、体验、未来扩展。

P0/P1 修复优先于新功能。

---

# 14. Definition of Ready

进入实现前：

- Problem 清晰；
- 有 Evidence 或可复现路径；
- Scope/Non-goal 明确；
- 不与当前 architecture 冲突，或已经有 ADR；
- 验收标准可以自动/客观检查；
- 依赖任务完成。

没有这些，AI 不应直接“猜着写”。

---

# 15. Definition of Done

任务只有在以下全部满足时 Done：

- 实现满足 acceptance；
- 必要测试已新增且通过；
- `mise run check:all` 通过；
- 无无关改动；
- event/schema/API 变更有兼容/迁移处理；
- docs 更新到唯一权威位置；
- ADR（若需要）合入；
- commit/PR 可解释；
- 已列出剩余风险，而不是隐藏 TODO。

---

# 16. PR 合并策略

- squash 与否由维护者决定；单个 commit 已清晰时可保留；
- PR 不混入大规模格式化；
- 代码生成/lockfile 变化与原因可审查；
- AI 生成的大 diff 不享有例外；
- Logic diff >500 LOC 优先拆分；>800 LOC 非机械默认拒绝。

---

# 17. 项目进度可视化

建议看板列：

```text
Backlog
Ready
In Progress
Review
Verification
Done
Blocked
```

注意 `Verification` 单独一列：实现完成不等于任务完成。

每个 Milestone 维护：

- planned tasks；
- done/blocked；
- exit criteria status；
- open design decisions；
- new evidence that changes plan。

不要用“完成百分比”掩盖关键 P0 阻塞。

---

# 18. AI 并行开发规则

多 AI 会话同时工作时：

- 每个 session 绑定明确 task ID；
- 尽量按 package/file ownership 切分；
- 不跨 task 清理别人的代码；
- 禁止 `git add .`/stash/reset；
- 遇到他人未提交改动时只修改自己的文件；
- 核心 schema/contract 文件原则上同一时间只给一个 owner；
- 合并顺序由依赖图决定，不依赖“谁先写完”。

---

# 19. 风险登记表（初始）

| 风险 | 等级 | 缓解 |
|---|---|---|
| Bun runtime edge case | P1 | pin 1.3.14；fault/soak；后续兼容矩阵 |
| Event schema 早期频繁变化 | P1 | schemaVersion + fixtures + ADR |
| AI 大规模重构漂移 | P1 | 500/800 LOC 门；task scope；AGENTS rules |
| Tool side effect 重复 | P0 | UNKNOWN + idempotency/reconcile |
| Context 无界增长 | P1 | hard budgets |
| Provider API churn | P2 | adapter isolation |
| Capability policy 被绕过 | P0 | core enforcement + security tests |
| “为了通过测试”降低语义 | P1 | test intent + review + no deleting valid tests |
| 过早 Multi-Agent | P2 | 明确 non-goal；extension only |

---

# 20. 何时允许修改路线图

路线图不是永久计划。只有出现以下 Evidence 时重排：

- 当前 milestone 的技术前提被证伪；
- P0/P1 bug 暴露新基础缺口；
- 实测性能证明当前架构已成主要瓶颈；
- 外部 API/Runtime breaking change 阻断；
- 用户需求改变 v1 Goal。

修改时写 Plan/ADR，不允许因“想试新技术”打断关键路径。
