# Praxis Harness 架构符合性规范

> 状态：Baseline / Normative  
> 权威设计：`docs/02-system-design.md`  
> 机器边界：`.praxis/architecture.yaml`

## 1. 目的

系统设计不能只靠 Code Review 记忆。Praxis Harness 将架构要求分成三层：

1. **设计说明**：`docs/02-system-design.md` 解释模块为什么这样划分；
2. **机器边界**：`.praxis/architecture.yaml` 保存可自动检查的依赖/风险规则；
3. **符合性测试**：`ai:guard`、CI 和 architecture tests 证明代码没有偏离设计。

普通开发任务不能通过“代码已经这么写了”反向修改设计文档。若代码必须突破现有边界，先走 ADR。

---

## 2. Core 依赖宪法

核心依赖方向：

```text
contracts
   ↑
 core
   ↑
adapters
   ↑
composition / apps
```

MUST：

- `contracts` 不依赖任何业务 adapter；
- `core` 只依赖 `contracts` 和批准的纯基础依赖；
- `store-sqlite`、`provider-openai`、`tools-local` 实现 contracts 定义的 port；
- CLI/TUI 只负责 composition / UX，不拥有第二套 runtime state；
- 安全/capability enforcement 属于 Core，不允许只靠 optional extension。

MUST NOT：

```text
core -> provider-openai
core -> store-sqlite
core -> tools-local
core -> apps/*
contracts -> core
adapter -> app-specific UI state contract
```

---

## 3. 自动检查项

### 3.1 Import graph

`ai:guard`/CI 必须扫描 TypeScript import graph：

- workspace package import 是否遵守 `.praxis/architecture.yaml`；
- Core 是否出现 adapter import；
- 是否绕过 package public API 直接 deep import 内部文件；
- 是否产生依赖环。

第一版优先使用 TypeScript compiler API / workspace metadata 实现，不为此引入大型架构框架。

### 3.2 Package manifest

检查：

- 每个 package dependency 与 architecture allowlist 一致；
- exact pin；
- Core 新增第三方依赖触发 ADR/human gate；
- 未声明依赖和 phantom dependency 禁止。

### 3.3 Durable contract

变更以下内容自动判定为 Class E：

- SessionEvent；
- persistent IDs/serialization；
- SQLite migration；
- Capability durable state；
- Session schema/version。

必须触发 migration/replay/backward compatibility gates。

### 3.4 Runtime invariants

架构不只是 package 图。以下必须通过测试强制：

- Command != Event；
- required verification 不 fail-open；
- indeterminate != failed；
- replay 不重新执行真实副作用；
- model 不能直接修改 runtime authority；
- Context 不是 durable history；
- single Session core state 采用单写者原则，Worker 通过 Event/Command 协作。

---

## 4. 架构变更协议

出现以下情况时，AI MUST STOP 普通实现：

- 当前 package boundary 无法实现 requirement；
- 现有 Port 缺少不可绕过的必要语义；
- 为满足任务必须修改 durable event vocabulary；
- 需要把 adapter-specific capability 放入 Core；
- 需要突破 v1 non-goal。

然后执行 `.agents/skills/architecture-change/SKILL.md`。

架构变更顺序：

```text
Observed contradiction
→ Evidence
→ Alternatives
→ ADR
→ Approval
→ architecture.yaml
→ system-design.md
→ code/tests
```

禁止：

```text
先改 code
→ 为了匹配 code 再改 architecture doc
```

---

## 5. 架构测试作为 CI 门禁

M0 应建立独立 `test:architecture` 或等价 gate，并把它加入 `check:all`。

至少包含：

1. workspace package dependency rules；
2. forbidden import rules；
3. circular dependency check；
4. Core third-party dependency allowlist；
5. public API/deep import rule；
6. `.praxis/architecture.yaml` schema/consistency check。

之后任何 architecture-related P0/P1 bug 都应转化为新的架构测试，而不只写到文档里。

---

## 6. 设计—实现一致性验收

每个 Milestone Acceptance 额外回答：

- 是否新增 package？为什么？
- 是否新增 Core dependency？ADR？
- 是否新增 durable contract？migration/replay？
- 是否让 optional extension 承担原本 Core invariant？
- 是否产生两个事实源或两个状态管理器？
- 是否有系统设计已过期但本次没有更新？

若任一问题没有明确答案，Milestone 不应推广。

---

## 7. 最终原则

> **架构设计不是建议，而是一组可以被代码和 CI 反证的工程假设。**

系统设计负责定义当前最合理的结构；架构 guard 负责发现实现偏离；ADR 负责在实践证明设计不足时修改结构。三者形成闭环，而不是让 AI 在每个会话里重新决定架构。
