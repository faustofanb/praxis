# Praxis Harness AI 开发指南

**目的：**让长期 AI 编码在多人/多会话/长周期条件下仍然高效、高质、不漂移、可交付。本指南本身也是 Praxis 理论的一次工程先验：把“实践—证据—计划—验证—纠错”应用到 Praxis Harness 自己的开发过程。

---

# 1. AI 在项目中的定位

AI 是**受约束的工程协作者**，不是仓库自治所有者。

AI 可以：

- 调查代码；
- 建立 bug/需求的 Evidence；
- 提出实现 Plan；
- 在 task scope 内修改代码；
- 增加测试；
- 更新当前事实文档；
- 提出 ADR；
- 做 review；
- 运行质量门并解释失败。

AI 不得自行：

- 改变 v1 Goal / Non-goals；
- 为了“更先进”引入新的一级架构；
- 绕过测试/Hook/权限；
- 删除看似有意的功能以消除错误；
- 大面积修改当前 task 以外代码；
- 把猜测当成 repository fact；
- 以“应该兼容”猜第三方 API，不查看真实类型/文档；
- 发现已有未提交工作后使用 destructive Git 清理。

---

# 2. 指令层级

AI 每次工作按：

1. 用户当前任务；
2. root `AGENTS.md`；
3. 当前目录最近的 subtree rules（未来可增加）；
4. `docs/02-system-design.md`；
5. `.agents/rules/*`；
6. 对应 `.agents/skills/*`；
7. ADR 当前 accepted decisions；
8. 代码事实/测试事实。

白皮书提供理论背景，但如果和当前系统设计冲突，以实施级 system design 为准。

---

# 3. 标准开发循环

AI 不直接从 prompt 跳到 edit。默认循环：

```text
Task
 ↓
Inspect
 ↓
Evidence
 ↓
Scope
 ↓
Plan
 ↓
Small Change
 ↓
Relevant Tests
 ↓
Full Required Gates
 ↓
Review Diff
 ↓
Report Result / Remaining Risk
```

## 3.1 Inspect

对广泛变更：

- 完整读取目标文件，不只看 grep snippet；
- 读取 package contracts；
- 读取已有 tests；
- 查 dependency types/source，禁止猜 API；
- 查看 git status 防止覆盖其他工作。

## 3.2 Evidence

至少能回答：

```text
当前行为是什么？
设计要求是什么？
差异在哪里？
哪个测试/trace/代码事实证明？
```

如果只是“感觉架构不够优雅”，默认不改。

## 3.3 Scope

在修改前明确：

- 修改包/文件；
- 不修改什么；
- 是否触及 Event schema / Agent Loop / Tool / Capability；
- 需要的测试层级。

## 3.4 Plan

Plan 以可证伪形式写：

```text
Hypothesis: 缺陷来自 X
Evidence: A/B
Change: 最小修改 Y
Expected result: Z
Falsified if: 测试/事实表明 X 不成立
```

而不是列十个“可能顺便做”的 TODO。

---

# 4. AI 修改规模

- 非机械改动建议 <500 changed LOC；
- >800 changed LOC 默认停止并拆分；
- 一次只做一个 Task；
- 不顺手 dependency upgrade；
- 不顺手大格式化；
- 不顺手“清理附近代码”；
- 若为了正确实现必须扩大 scope，先说明新 Evidence。

目的不是限制 AI 速度，而是提高 review、回滚、定位和并行能力。

---

# 5. “不漂移”规则

## 5.1 Architecture Drift

AI 发现新需求时先问：

> 是否能用现有 Port/Event/Extension seam 解决？

只有不能，才考虑 Core API。禁止每个 feature 加新 hook、新 manager、新 service。

## 5.2 Goal Drift

测试/指标只是手段。

禁止：

- 删除有效测试让 suite 变绿；
- 降低 verification 只为了 benchmark；
- 改 Goal/constraint 适配实现；
- 把“模型更容易做”当成用户需求。

## 5.3 Dependency Drift

新包必须先走第三方准入。AI 不得因为“这个库更方便”直接 `bun add`。

## 5.4 Documentation Drift

一条事实一个家。不要在 AGENTS、README、architecture、skill 中复制完整相同规则；短规则链接到详细归属。

---

# 6. 高风险文件分级

## Tier 0 — Core Constitution

- `packages/contracts/src/events*`
- `packages/contracts/src/capability*`
- `packages/core/src/reducer*`
- `packages/core/src/agent-loop*`
- store migration

修改要求：

- 完整读取；
- ADR/设计一致性检查；
- integration test；
- property/replay（适用时）；
- 小 diff；
- 不并行让多个 AI 同时改同一文件。

## Tier 1 — Adapters

- provider；
- tool；
- store implementation。

修改要求：contract + failure semantics test。

## Tier 2 — Product/Docs

- CLI；
- examples；
- docs。

风险较低，但不能绕过上层 contract。

---

# 7. Event 变更规则

AI 要增加 Event 前必须执行 `add-event` Skill。

问题：

1. 这是已经发生的事实，还是 Command/telemetry？
2. 是否需要 durable？
3. replay 时改变哪些 state？
4. schema 版本如何处理？
5. 是否可由现有 event 表达？

Event type 不是 debug log vocabulary。错误加 event 会形成永久兼容负担。

---

# 8. Tool 变更规则

每个 Tool 必须定义：

```text
effect class
required capability
timeout semantics
cancel semantics
idempotency
reconciliation
output bound
secret/redaction
verification/postcondition
```

如果回答不出 `timeout` 后“可能已经执行”怎么办，Tool 设计不完整。

---

# 9. Agent Loop 变更规则

任何 Agent Loop 修改必须：

- 说明现有 trace 为什么不足；
- 不把 provider-specific 逻辑塞 Core；
- 有 scripted model integration test；
- 测取消/错误路径；
- 检查 Context 是否新增无界内容；
- 检查 event ordering；
- 如果影响副作用，跑 fault tests。

禁止只用真实模型手工 demo 证明 Loop 正确。

---

# 10. Test 规则

AI 修 bug 时必须尽量先建立 reproducer。测试优先级：

```text
reproducer > implementation change > regression pass
```

不要写：

- 只断言内部实现细节但不覆盖 bug；
- 永远 pass 的 mock；
- 为了覆盖率专门暴露 production helper；
- 依赖真实 LLM 输出字面字符串的 Core test。

Agent 逻辑测试使用 ScriptedModel。

---

# 11. AI Review 模式

Review 不是重新实现。

按严重性：

- P0：状态失真、重复副作用、权限绕过、秘密泄露、错误成功；
- P1：Agent Loop/恢复/contract correctness；
- P2：维护性/性能；
- P3：风格。

Review 优先找：

1. illegal state；
2. crash window；
3. `UNKNOWN` 被压成 bool；
4. unbounded context/queue；
5. Core -> adapter dependency；
6. hidden side effect；
7. missing integration/fault test；
8. docs/schema drift。

只有事实支撑的问题才报告，不为了“显得认真”制造无意义意见。

---

# 12. AI Git 纪律

参考成熟 AI-first repo 的并行工作经验：

- 开始和结束都 `git status`；
- 只 stage 本次修改路径；
- 不动其他 session 文件；
- 不 stash；
- 不 hard reset；
- 不 clean；
- 不 `git add .`；
- 不跳过 hooks；
- 冲突出现在未修改文件时，停止并请求协调。

Commit message 按项目 Conventional Commits。

---

# 13. AI 依赖管理

AI 不能猜 node_modules API。

需要第三方 API 时：

1. 查看当前锁定版本；
2. 查看 package 类型/官方文档/源码；
3. 在 adapter 层使用；
4. 不把第三方类型泄露到 contracts；
5. 若现版本确有 bug，开独立 upgrade task；
6. 不通过 `as any` 掩盖版本不匹配。

---

# 14. AI 文档策略

文档分三类：

### Current State

`system-design` / subsystem docs：只写现在系统怎么工作。

### Decision

ADR：为什么选择这个方案、放弃什么。

### Procedure

Skills：如何完成一个高频任务。

AI 不应把一次 PR 的“改了什么”永久写进 architecture；变更故事属于 commit/PR/ADR/postmortem。

---

# 15. AI 上下文策略

每次编码会话不应该加载整个白皮书。

建议最低上下文：

```text
AGENTS.md
当前 Task
目标 package 代码/tests
相关 system-design/subsystem
相关 Skill
相关 ADR
```

白皮书只在架构原则争议时读取。

这样既防 Context 膨胀，也降低 AI 被历史讨论牵着走。

---

# 16. Skill 选择

- 新功能：`implement-feature`
- bug：`fix-bug`
- Tool：`add-tool`
- durable Event：`add-event`
- Agent Loop：`change-core-loop`
- Review：`review-change`
- RC/发布：`release-check`

Skill 是流程模板，不拥有更高架构权力。

---

# 17. AI 交付输出规范

每次实现结束至少报告：

```text
Changed:
- ...

Evidence/Tests:
- ...

Not changed:
- ...

Remaining risk:
- ...
```

如果没完成，明确：

- 已完成到哪；
- 哪个 Evidence 阻断；
- 当前安全状态；
- 不要声称“应该没问题”。

---

# 18. AI 先验实验指标

本项目开发过程本身可以检验 Praxis 理论。建议记录：

- AI PR 平均 changed LOC；
- integration failure escape rate；
- AI 引入未使用依赖次数；
- PR 被要求返工原因；
- “已有 Worker/AI 提醒但被忽略”事故；
- architecture rule violation；
- bug reproducer-first 比率；
- issue -> accepted diff 的 scope expansion 次数；
- replay/fault test 捕获的真实 defect 数。

这些数据以后决定是否需要更复杂治理，而不是先验增加 manager/critic。
