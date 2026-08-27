# Praxis Harness AI 开发控制面

> 文档状态：Baseline / Normative  
> 适用范围：Praxis Harness v0.x → v1.0  
> 目的：把“AI 应该怎样开发”从被动文档要求升级为机器可读、脚本可检查、CI 可阻断、阶段可验收的主动开发制度。

---

# 1. 为什么需要开发控制面

仅靠 `AGENTS.md`、系统设计和项目规划书还不够。

它们解决的是：

- 人和 AI **应该知道什么**；
- 人和 AI **应该遵守什么**。

但长期 AI 开发真正容易失败在：

- AI 忘记当前 Milestone，只凭当前对话继续扩功能；
- 计划与系统设计脱节；
- 修改超出任务 scope 但没有被发现；
- 应运行的测试没有运行；
- 阶段 Exit Criteria 只是文字，没有实际验收证据；
- 一个会话完成后，下一个 AI 不知道“真实状态到哪里”；
- AI 自己宣布“完成”，但项目事实上不具备进入下一阶段的条件。

因此本项目增加 **AI Development Control Plane（AI 开发控制面）**：

> 文档负责解释原则；`.praxis/` 目录负责保存机器可读项目事实；脚本负责执行规划、守界、验证、验收和交接；CI 负责阻止绕过。

开发控制面不是新的产品 Runtime，也不进入 Praxis Harness 最终用户功能。它只服务于**开发 Praxis Harness 本身**。

---

# 2. 控制面的五个权威对象

## 2.1 Project Charter — 项目宪章

文件：`.praxis/project.yaml`

定义不可由普通开发任务自行修改的内容：

- 项目 Goal；
- v1 目标；
- Non-goals；
- Core invariants；
- 架构权威文档；
- 当前发布线。

AI 可以提出修改建议，但不得在普通任务中直接改变这些值。

---

## 2.2 Architecture Boundary — 架构边界

文件：`.praxis/architecture.yaml`

机器可读地描述：

- package 职责；
- 合法依赖方向；
- Core 禁止依赖；
- 哪些路径属于 Tier 0 / Tier 1；
- 哪些变更必须 ADR；
- 哪些模块明确不进入 v1 Core。

系统设计文档解释“为什么”；该文件让脚本可以检查“有没有越界”。

---

## 2.3 Milestone Contract — 里程碑合同

文件：`.praxis/milestones/M0.yaml` … `M8.yaml`

每个 Milestone 不是一段介绍，而是一份可验收合同：

- 目标；
- 前置条件；
- Required deliverables；
- Forbidden work；
- Machine gates；
- Scenario acceptance；
- Failure acceptance；
- Human demo；
- Real-model eval 要求；
- Exit Criteria；
- 哪些 evidence artifact 必须存在。

AI 不得自行跳过 Milestone。

---

## 2.4 Task Contract — 任务合同

目录：`.praxis/tasks/`

任何非微小修改必须先存在一个 Task Contract。任务至少包含：

```yaml
id: M1-T003
title: implement deterministic event reducer
milestone: M1
status: planned
objective: ...
evidence: ...
hypothesis: ...
scope:
  allowed_paths: [...]
  forbidden_paths: [...]
architecture_refs: [...]
required_gates: [...]
acceptance: ...
falsified_if: ...
```

任务的作用不是增加文书，而是限制 AI 只能做**当前已经明确允许的工作**。

---

## 2.5 Project State — 当前项目状态

文件：`.praxis/state.yaml`

这是跨 AI 会话必须共享的最小真实状态：

- 当前 Milestone；
- 已通过的最后一个 Milestone；
- Active task；
- Blockers；
- Open ADR；
- 当前已知风险；
- 最近一次验收结果；
- 下一合法动作。

AI 每次开始开发先读取它，而不是依赖聊天记忆。

---

# 3. AI 开发状态机

项目开发采用显式状态机：

```text
IDLE
 ↓
DISCOVERING
 ↓
PLAN_READY
 ↓
IMPLEMENTING
 ↓
VERIFYING
 ↓
ACCEPTANCE_READY
 ├─→ REWORK ───────────┐
 │                     │
 └─→ ACCEPTED          │
        ↓               │
      IDLE ←────────────┘
```

含义：

## IDLE

当前没有 Active Task。

## DISCOVERING

AI 只能读取、调查、建立 Evidence，不应进行广泛代码修改。

## PLAN_READY

Task Contract 已通过静态验证，Scope 和 required gates 已明确。

## IMPLEMENTING

只允许修改 Task Contract `allowed_paths` 中的文件；若需要扩大 scope，必须先修改任务合同并说明 Evidence。

## VERIFYING

实现完成但不得宣称任务完成。必须执行任务要求的测试与质量门。

## ACCEPTANCE_READY

全部任务门禁 PASS，验收证据齐全，等待自动/人工 acceptance policy 决定是否放行。

## REWORK

验收失败，必须保留失败 Evidence，回到同一任务修正，不得隐藏失败后建立新任务规避。

## ACCEPTED

Task Contract 完成。之后才能生成 handoff 或进入下一任务。

---

# 4. 谁能宣布“完成”

AI 模型本身没有完成主权。

```text
LLM says done
      ≠
Task accepted
```

任务完成由三层决定：

1. **Guard**：Scope / architecture / dependency 规则没有被破坏；
2. **Verify**：required gates 与测试全部真实 PASS；
3. **Acceptance policy**：满足任务/里程碑验收合同。

低风险普通 Task 可以机器自动 ACCEPT。

以下情况 MUST NOT 由编码 AI 自行最终接受：

- Milestone promotion；
- Core Constitution / Event schema / Capability semantics 改动；
- Security boundary；
- 真实不可逆外部副作用设计；
- v1 Goal / Non-goal 变化；
- 架构依赖方向变化。

这些只能进入 `ACCEPTANCE_READY`，由人类或独立 review 流程最终放行。

---

# 5. 一次 AI 开发任务的强制流程

## Step 0 — Brief

执行：

```text
mise run ai:brief
```

输出当前：

- Milestone；
- Active task；
- Project Goal / Non-goals；
- 当前架构边界；
- 任务 Allowed paths；
- Required gates；
- 当前 blockers；
- 相关 ADR / docs；
- Git status 摘要。

AI 不应自己临时拼 Context；控制面生成一个有限、权威的 task briefing。

---

## Step 1 — Discover

AI 调查代码、测试、系统设计与依赖事实。

不得先写大量代码再解释原因。

Evidence 要写进 Task Contract 或 task notes：

```text
Observed behavior
Expected design
Difference
Evidence references
```

---

## Step 2 — Plan

执行：

```text
mise run ai:plan -- .praxis/tasks/M1-T003.yaml
```

脚本验证：

- milestone 合法；
- prerequisite 满足；
- allowed_paths 与 architecture 不冲突；
- required gates 是否覆盖变更风险；
- 是否需要 ADR；
- 是否违反 v1 non-goals。

只有 PASS 后 task 状态才能进入 `PLAN_READY`。

---

## Step 3 — Implement

AI 进行最小实现。

开发过程随时可运行：

```text
mise run ai:guard
```

Guard 检查：

- Git diff 是否越出 allowed scope；
- 是否新增未授权依赖；
- 是否触及 Tier 0 但缺少相应测试/ADR；
- 是否出现 forbidden patterns；
- 是否修改冻结文件。

Guard FAIL 必须先解决，不能继续扩大实现。

---

## Step 4 — Verify

执行：

```text
mise run ai:verify
```

根据实际 diff 自动分类变化：

```text
contracts/event
core/agent-loop
tool lifecycle
capability
store/migration
provider
CLI/docs
```

再从 `.praxis/quality-gates.yaml` 计算 MUST 运行的门禁。

这避免 AI 自己挑“比较容易通过的测试”。

---

## Step 5 — Acceptance

执行：

```text
mise run ai:accept
```

脚本核对：

- required gates 结果；
- fixed scenario evidence；
- failure acceptance；
- acceptance artifacts；
- diff / scope；
- unresolved blockers；
- milestone-specific requirements。

结果只有：

```text
ACCEPTED
ACCEPTANCE_READY
REWORK
```

禁止输出模糊的“基本完成”。

---

## Step 6 — Handoff

任务结束执行：

```text
mise run ai:handoff
```

生成 `.praxis/handoffs/<task-id>.md`：

- 做了什么；
- 没做什么；
- 关键 Evidence；
- 测试命令与结果；
- 新增风险；
- ADR 状态；
- 下一合法任务；
- 工作区是否 clean。

下一个 AI 先读取 machine state 与 handoff，不依赖上一次聊天。

---

# 6. 自动规划不是让 AI 自己重写 Roadmap

“自动规划”分三层：

## Level 1 — Task Planning

AI 可以自主把一个已批准 Task 拆成 implementation steps。

## Level 2 — Milestone Task Selection

AI 可以根据 `.praxis/milestones/M#.yaml` 和当前 state，选择**当前 Milestone 中尚未完成且 prerequisite 已满足的下一任务**。

## Level 3 — Roadmap / Architecture Planning

AI 不得自行修改。

涉及：

- 新 Milestone；
- 删除 Milestone；
- v1 scope；
- Core package；
- 架构依赖方向；
- Event semantics；

必须 ADR / 人类批准。

因此：

> AI 可以自动决定“下一块砖怎么砌”，不能自行决定“房子改造成另一种建筑”。

---

# 7. 系统设计的机器强制

`docs/02-system-design.md` 是权威设计说明；`.praxis/architecture.yaml` 是可检查版本。

例如 v1 基础依赖规则：

```text
contracts
   ↑
 core
   ↑
adapters
   ↑
apps/composition
```

禁止：

```text
core → provider-openai
core → store-sqlite
core → tools-local
core → CLI/TUI
```

Guard 应通过 import graph / package metadata 检查这些规则。

如果 AI 认为 Core 必须依赖某 Adapter：

> 这不是“实现细节”，而是 architecture contradiction，必须停止并提出 ADR。

---

# 8. Change Classification — 变更自动分类

控制面按 diff 分类风险。

## Class A — Low Risk

- 文档；
- 测试 fixture；
- CLI 文案；
- 无语义格式调整。

门禁较轻。

## Class B — Functional

- Adapter 功能；
- CLI 行为；
- Provider mapping。

需要 unit + integration。

## Class C — Core Behavioral

- Agent Loop；
- Context Builder；
- Reducer；
- Plan / Hypothesis semantics。

必须 integration + scripted model + replay/property（适用）。

## Class D — Side Effect / Security

- Tool lifecycle；
- Capability；
- Approval；
- Sandbox；
- UNKNOWN/reconciliation。

必须 fault + adversarial + idempotency/reconciliation。

## Class E — Durable Contract

- Event schema；
- Store migration；
- persistent session format。

必须 ADR + fixture + migration + replay + backward compatibility。

风险越高，AI 越没有自由缩减验证范围。

---

# 9. 自动测试与质量门

`.praxis/quality-gates.yaml` 描述“改哪里 → 必须跑什么”。

示例：

```yaml
rules:
  - match: packages/core/src/agent-loop/**
    require:
      - format
      - lint
      - typecheck
      - unit
      - integration-agent-loop
      - replay
  - match: packages/core/src/tool-runtime/**
    require:
      - integration-tool
      - fault-tool
      - idempotency
      - capability-adversarial
```

`ai:verify` 从真实 Git diff 计算门禁，不能由 LLM 自由选择。

---

# 10. 自动验收的边界

## Task 自动验收

允许：

- 已有设计内的普通实现；
- 不改变 durable contract；
- 不改变 security semantics；
- 所有机器门与场景门均可自动验证。

## Task 人工放行

必须：

- ADR；
- Event schema；
- Capability policy 语义；
- dependency introduction；
- M4 Praxis 认识机制大改；
- TUI/CLI user-facing contract 大改。

## Milestone promotion

机器生成 acceptance report，但**不得由负责实现的 AI 自己最终推广 Milestone**。

Milestone 的最终状态变更至少要求：

```text
Machine Gates PASS
Scenario PASS
Failure Acceptance PASS
Required Human Demo PASS（如有）
Required Real-model Eval 完成（如有）
Independent/Human approval
```

这就是“自动验收而不自我认证”。

---

# 11. AI 不漂移的五个技术机制

## 11.1 Goal pinning

每次 `ai:brief` 都重新注入：

- project goal；
- current milestone goal；
- non-goals；
- active task objective。

不要依赖长对话记忆。

## 11.2 Scope guard

Git diff 越界自动 FAIL。

## 11.3 Architecture guard

Import / dependency 越界自动 FAIL。

## 11.4 Acceptance guard

AI 不能仅凭文字把 task/milestone 标成 accepted。

## 11.5 Handoff continuity

每次会话结束生成机器状态 + 人类可读 handoff，下一会话从 repo state 继续。

这五项比再写十页 Prompt 更能防漂移。

---

# 12. 与 Praxis Harness 理论的一次先验落地

AI Development Control Plane 本身就应用前面的 Praxis 原则：

| 理论 | 本项目开发机制 |
|---|---|
| 实践检验 | 代码必须运行测试/验收，不接受“看起来正确” |
| 事实/假设分离 | Task 中 Evidence 与 Hypothesis 独立 |
| 可证伪计划 | `falsified_if` 写入 Task Contract |
| 主要矛盾 | 每个 Milestone 有唯一阶段目标 |
| 群众路线 | 多来源调查可分布，但 commit/acceptance 统一归档 |
| 领导权 | AI 不能修改 Goal / Constitution |
| Challenge | 架构证据冲突必须 ADR，而不是 AI 偷改设计 |
| 再生产 | Handoff、event/acceptance artifact 形成下一任务前提 |
| 生产优先 | 对低风险小任务允许轻量路径，不制造流程崇拜 |
| 非常态治理 | 架构/安全变更提高门禁，而非所有 task 同样繁琐 |

如果这套机制本身造成明显开发阻塞，也必须用实际数据修订，而不是教条坚持。

---

# 13. Repository 目标形态

M0 结束前建议至少存在：

```text
.praxis/
  project.yaml
  architecture.yaml
  quality-gates.yaml
  ai-policy.yaml
  state.yaml
  schemas/
  milestones/
    M0.yaml ... M8.yaml
  tasks/
    TEMPLATE.yaml
  handoffs/

scripts/ai/
  praxis-dev.ts
  README.md

.agents/skills/
  execute-task/
  milestone-acceptance/
  architecture-change/
```

并通过 `mise` 暴露：

```text
ai:brief
ai:plan
ai:guard
ai:verify
ai:accept
ai:handoff
ai:status
```

这些不是“AI Agent 管理平台”，而是小型 repo-local development controller。

---

# 14. v1 开发控制面明确不做

本机制自身也遵循范围冻结：

- 不做独立 Web 项目管理 UI；
- 不做通用 autonomous software factory；
- 不让 AI 自动修改 Roadmap；
- 不让负责实现的 AI 自动推广 Milestone；
- 不做复杂多 Agent 任务调度平台；
- 不依赖云端 Project Management SaaS 才能工作；
- 不把所有文档复制进机器配置；
- 不自动 commit/push 未经用户要求的代码；
- 不做“AI 自我评分”替代真实 gate。

控制面必须始终比被开发项目简单。

---

# 15. 最终原则

> **文档解释设计；机器状态固定目标；Task Contract 约束范围；Guard 阻止越界；Verify 用实践检验实现；Acceptance 决定是否放行；Handoff 让下一轮工作建立在真实历史上。**

因此 AI 开发不再是：

```text
Prompt → AI 自由修改 → AI 说完成
```

而是：

```text
Project Constitution
        ↓
Current Milestone
        ↓
Task Contract
        ↓
AI Investigation & Plan
        ↓
Guarded Implementation
        ↓
Deterministic Verification
        ↓
Acceptance Evidence
        ↓
Accepted State / Rework
        ↓
Handoff
```

这就是 Praxis Harness 项目长期 AI 开发的正式控制机制。
