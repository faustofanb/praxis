# Praxis Workbench 产品领域模型与核心概念规范

## Work-centered Agentic Engineering Domain Model

**版本：v0.1**  
**日期：2026-08-28**  
**文档性质：产品领域基线 / Normative Product Domain Baseline**  
**上位文档：**《Praxis 产品白皮书》  
**下位专题：**Work Graph 与生命周期详细规范、Agent Work/Handoff 规范、Multi-Repository & Git Model、Automation Model、Workbench UX、Workbench System Design

> 本文冻结 Praxis Workbench 产品世界中的核心对象、对象边界、生命周期语义、工作关系与所有权原则。本文不规定数据库表、RPC/API、GUI 技术栈、Automation DSL、Git Worktree 物理目录或 Multi-Agent 调度算法。

---

# 目录

1. 文档定位与规范用语
2. 领域模型总览
3. Workspace：长期工作空间
4. Work：产品最高工作对象
5. Goal、Constraints 与 Acceptance
6. Work Type 与 Work Template
7. Work Lifecycle：状态来自哪里
8. Work Graph：工作的结构化组织
9. WorkItem：可独立管理的执行单位
10. Work Graph 关系语义
11. Readiness、Waiting、Blocked 与状态传播
12. Graph Revision：工作计划如何演化
13. Agent Definition 与 Executor
14. Assignment：执行责任的分配
15. AgentRun：一次真实执行过程
16. Session：Runtime 的持久运行容器
17. Artifact 与 Evidence
18. Handoff：跨执行主体的结构化交接
19. Repository 与 RepoChange
20. ChangeSet：跨仓库交付变更集合
21. Verification：为什么可以相信结果
22. Delivery：怎样进入目标交付位置
23. 对象所有权与生命周期矩阵
24. MES 参考场景
25. 产品领域不变量
26. v0.1 明确不做
27. 后续专题待决问题
28. 术语表

---

# 第一章　文档定位与规范用语

## 1.1 本文解决什么问题

《Praxis 产品白皮书》已经确定长期产品方向：Praxis 从可靠 Agent Runtime 向以 Work 为中心的 Agentic Engineering Workbench 演进。

但产品白皮书仍然停留在“产品要解决什么问题”的层次。要继续设计 GUI、Work Graph、Multi-Agent、Git、Automation 和跨仓库交付，必须先建立一个稳定的共同语言：

```text
Workspace 是什么？
Work 和 Requirement 有什么区别？
WorkItem 和 Agent Task 是否相同？
AgentRun 与 Session 有什么边界？
工作状态由谁决定？
Work Tree 和 Work Graph 是不是同一个东西？
一个跨多个仓库的需求最终以什么对象交付？
Agent 之间应该传聊天记录，还是传工作状态？
```

本文的任务就是回答这些问题。

---

## 1.2 规范用语

本文使用以下约束等级：

- **MUST / 必须**：后续产品设计与实现不得违反，除非通过正式产品领域模型修订；
- **MUST NOT / 禁止**：出现即视为领域边界破坏；
- **SHOULD / 应当**：默认产品设计方向，若实践证明不合适可以在专题规范中偏离；
- **MAY / 可以**：允许存在的扩展，不构成产品必备语义。

本文中的代码块主要表达领域关系，不代表最终 TypeScript、数据库或 API Schema。

---

## 1.3 核心方法

Praxis Workbench 领域模型遵循五条方法：

1. **Work over Chat**：产品围绕真实工作组织，而不是围绕聊天会话组织；
2. **Goal over Plan**：稳定目标高于当前工作图和执行计划；
3. **Execution-derived State**：尽可能从真实执行事实推导工作状态；
4. **Evidence over Declaration**：完成与验收必须有证据，不依赖 Agent 自我声明；
5. **State Transfer over Conversation Transfer**：跨 Agent 交接传递结构化工作状态，而不是无限聊天历史。

---

# 第二章　领域模型总览

## 2.1 顶层对象关系

Praxis Workbench 的第一版领域世界由以下对象构成：

```text
Workspace
│
├── Repository [0..N]
├── Agent Definition [0..N]
├── Automation [0..N]          # 仅定义其领域位置，详细语义后置
│
└── Work [0..N]
      │
      ├── Requirement / Context
      ├── Goal
      ├── Constraints
      ├── Acceptance Criteria
      │
      ├── Work Graph
      │     │
      │     └── WorkItem [1..N]
      │            │
      │            ├── Repository [0..N]
      │            ├── Assignment [0..N]
      │            │      │
      │            │      └── AgentRun / HumanRun [0..N]
      │            │              │
      │            │              └── Runtime Session [1..N]
      │            │
      │            ├── Artifact [0..N]
      │            ├── Handoff [0..N]
      │            └── Verification [0..N]
      │
      ├── ChangeSet [0..N]
      │      └── RepoChange [0..N]
      │
      ├── Verification [0..N]
      └── Delivery [0..N]
```

这里最重要的层次是：

```text
Work
↓
WorkItem
↓
Assignment
↓
AgentRun
↓
Session
↓
Turn / Event / Tool
```

**Work 是产品层最高工作对象；Session 是 Runtime 层执行历史。**

---

## 2.2 两条并行主线

这个模型实际上包含两条并行但互相引用的主线。

### 执行主线

回答“谁怎样工作”：

```text
WorkItem
→ Assignment
→ AgentRun
→ Session
→ Action / Tool / Event
```

### 产出主线

回答“工作产生了什么”：

```text
AgentRun
→ Artifact / Evidence / RepoChange
→ ChangeSet
→ Verification
→ Delivery
```

后续系统设计必须避免把执行者、运行历史和交付成果混成一个对象。

---

# 第三章　Workspace：长期工作空间

## 3.1 定义

> **Workspace 是一组为了长期完成相关工作而共同管理的代码仓库、Work、Agent、Automation 和外部集成的产品边界。**

Workspace 是 Praxis Workbench 的最高长期组织单位。

例如一个 MES Workspace 可以包含：

```text
MES Workspace
│
├── Repositories
│   ├── mes-server       Java backend
│   ├── mes-web          Vben5
│   ├── mes-pda          UniApp
│   ├── mes-machine      UniApp
│   └── mes-tablet       UniApp
│
├── Works
│   ├── MES-2041 首检状态校验
│   ├── BUG-993 PDA重复扫码
│   └── INC-271 报工服务异常
│
├── Agent Definitions
│   ├── Backend Developer
│   ├── Web Developer
│   ├── UniApp Developer
│   └── Reviewer
│
└── Automations / Integrations
    ├── GitLab
    ├── Jenkins
    └── Issue System
```

---

## 3.2 Workspace 不是文件夹

Workspace MUST NOT 被定义为一个文件系统目录。

以下结构完全合法：

```text
Workspace: MES

Repositories:
D:/work/server/mes
D:/frontend/mes-web
E:/mobile/mes-pda
```

Workspace 是逻辑生产空间，不要求 Repository 共享父目录。

---

## 3.3 Workspace 与 Repository

一个 Workspace MUST 支持：

```text
Workspace 1 ── 0..N Repository
```

产品领域层 MUST NOT 假设：

```text
Workspace == Git Repository
```

Multi-repository（多仓库）是 Praxis Workbench 的一等领域前提，而不是后续插件。

---

# 第四章　Work：产品最高工作对象

## 4.1 定义

> **Work 是一个由 Goal 驱动、具有边界、可分解、可执行、可验证，并最终要求现实状态发生变化的持久工作对象。**

Work 是 Praxis Workbench 的最高产品工作对象。

典型 Work 包括：

- Feature（功能）；
- Bug（缺陷）；
- Incident（生产事件）；
- Refactor（重构）；
- Migration（迁移）；
- Research（调查/研究）；
- Maintenance（维护）；
- Release（发布）；
- 未来用户定义类型。

---

## 4.2 Work 不等于 Requirement

Praxis MUST NOT 把所有工作都建模为 Requirement。

Requirement 回答：

> 为什么需要这项工作？希望什么结果？有哪些业务要求？

Work 回答：

> 当前有哪些现实状态需要被改变，并最终完成和交付？

简单场景中一个 Requirement 可以几乎等于一个 Work，但领域层保留两者区别。

例如：

```text
Requirement:
新厂区接入MES

creates/constrains:
├── Work: Backend integration
├── Work: Terminal adaptation
├── Work: Data migration
└── Work: Go-live verification
```

Requirement MAY 作为 Work 的输入、Context 或外部关联对象，但 v0.1 不要求独立 Requirement 子系统。

---

## 4.3 Work 的组成

一个可执行 Work SHOULD 至少拥有：

```text
Identity
Goal
Context
Constraints
Acceptance Criteria
Work Graph
Execution History
Artifacts / Evidence
ChangeSets（代码类工作适用）
Verification
Delivery
```

并非创建 Work 时必须一次填满所有字段。Praxis SHOULD 支持从低结构信息逐步澄清成 Ready Work。

---

# 第五章　Goal、Constraints 与 Acceptance

## 5.1 Goal

> **Goal 描述 Work 希望最终达到的现实状态。**

Goal MUST 高于当前 Work Graph、Agent Plan 和具体 Tool Action。

例如：

```text
Title:
报工增加质检拦截

Goal:
当工序要求质检且质检尚未通过时，所有相关报工终端均不得执行完工；
不需要质检的现有报工流程保持原有语义。
```

标题不是 Goal。

---

## 5.2 Constraints

> **Constraint 描述即使为了完成 Goal 也不能随意破坏的边界。**

例如：

```text
不得破坏旧终端兼容性
不得改变已完工订单状态
不得绕过既有权限控制
不得增加现场明显等待时间
```

Work Constraint 是 Runtime Goal Invariant 的上游产品来源之一。

---

## 5.3 Acceptance Criteria

> **Acceptance Criteria 定义什么证据出现时，可以认为 Work Outcome 满足 Goal。**

例如：

```text
AC-01 需质检且未通过时，完工被拒绝
AC-02 质检通过后允许完工
AC-03 不需质检的流程行为不变
AC-04 Web / PDA / relevant terminals 行为一致
AC-05 required regression tests pass
```

Acceptance MUST NOT 被简化为“所有 WorkItem Done”。

父 Work MUST 拥有自己的 Acceptance；子 WorkItem 的完成只能成为父级 Acceptance 的 Evidence 或 Preconditions。

---

# 第六章　Work Type 与 Work Template

## 6.1 Work Type

Work Type 表示不同工作的业务性质，例如 Feature、Bug、Incident。

Work Type MAY 影响：

- 推荐的 Work Template；
- 默认 Readiness Policy；
- 默认 Verification；
- 默认 Automation；
- GUI 呈现。

但 Work Type MUST NOT 导致每一种工作拥有完全不同的底层领域模型。

---

## 6.2 Work Template

> **Work Template 是一种可复用的工作组织模板，定义常见 WorkItem、依赖、Acceptance 和 Automation 建议。**

例如 Feature Template：

```text
Requirement Analysis
├── Backend
├── Web
├── Relevant Terminals
├── Integration
├── Regression
└── Delivery
```

Incident Template：

```text
Stabilize
→ Collect Evidence
→ Root Cause
→ Mitigation
→ Permanent Fix
→ Regression
→ Postmortem
```

Template 是起点，不是不可修改的 Workflow。

---

# 第七章　Work Lifecycle：状态来自哪里

## 7.1 核心原则

> **Work 状态 SHOULD 尽可能由真实执行事实推导，而不是依靠人手工维护单一 Status 字段。**

Praxis MUST 避免出现：

```text
现实中 Agent 已经停止三天
但卡片仍显示 In Progress
```

这称为 **Execution-derived State（执行事实派生状态）**。

---

## 7.2 不使用单一超级状态枚举

领域层 SHOULD 把状态拆成正交维度，而不是不断扩展：

```text
waiting_for_review_after_execution
blocked_during_verification
ready_but_not_approved
```

建议基础维度：

| 维度 | 回答的问题 | 典型语义 |
|---|---|---|
| Lifecycle | 这项 Work 在业务上是否继续存在？ | captured / active / cancelled / closed |
| Governance | 人/规则是否允许继续？ | pending / approved / paused |
| Readiness | 客观条件是否具备？ | ready / waiting / blocked |
| Execution | 是否有人或 Agent 正在执行？ | idle / executing |
| Acceptance | 结果是否被证明满足标准？ | unverified / verifying / accepted / needs_work |
| Delivery | 成果是否进入目标位置？ | not_started / delivering / delivered |

最终 GUI MAY 把多个维度投影成一个简洁主状态。

---

## 7.3 Captured

Captured 表示 Work 已进入 Praxis，但还没有达到可启动标准。

例如用户只输入：

```text
PDA 有时扫码两次
```

它已经是一个 Work，但可能缺乏复现、Goal、Acceptance 或 Scope。

Praxis SHOULD 允许先捕获、后澄清，而不是要求创建 Work 时填写大量管理字段。

---

## 7.4 Approved 与 Ready

必须冻结：

```text
Approved ≠ Ready
```

Approved 是业务/治理决定：

> 我们决定做这件事。

Ready 是客观就绪判断：

> 当前启动执行需要的前提已经满足。

一个 WorkItem 可以 Approved 但 Waiting，也可以技术上 Ready 但尚未被批准执行。

自动启动 Agent MAY 要求：

```text
Approved
AND Ready
AND Automation policy allows
```

---

## 7.5 Waiting、Blocked 与 Paused

三者 MUST 区分。

### Waiting

> 正常等待已经知道的前置条件。

例如 Web 等待 Backend API Contract Accepted。

### Blocked

> 当前原本应该能推进，但出现了需要解决的新障碍。

例如权限缺失、业务约束冲突、构建环境故障。

### Paused

> 工作本身没有客观阻塞，但治理主体选择暂时停止执行。

例如人工暂停、成本预算达到上限、维护窗口结束。

简化：

```text
Waiting = 正常前置尚未满足
Blocked = 想继续但现在无法继续
Paused  = 可以继续但选择暂时不继续
```

---

## 7.6 Executing

Executing SHOULD 从 Active AgentRun / Human execution 等事实推导。

```text
active AgentRun count > 0
→ Execution = executing
```

用户不应该主要靠手工把卡片拖到 In Progress。

---

## 7.7 Execution Completed ≠ Accepted

AgentRun 完成只表示一次执行过程结束。

```text
AgentRun = COMPLETED
```

并不能直接得到：

```text
WorkItem = ACCEPTED
```

如果 Required Verification 尚未满足，WorkItem 应处于 Verifying / Unverified 等派生状态。

---

## 7.8 Accepted ≠ Delivered ≠ Closed

三者 MUST 分开。

### Accepted

有足够 Verification 支持 Acceptance Criteria 已满足。

### Delivered

成果已经进入目标交付位置，例如 Merge、Release、Deploy 或报告发布。

### Closed

治理主体认定当前 Work 不再需要继续采取行动。

例如代码周五已 Accepted，但周一才部署，则期间：

```text
Acceptance = accepted
Delivery = not_started
Lifecycle = active
```

---

## 7.9 Reopen

Closed Work MUST 可以重新打开，但不得覆盖历史。

应产生显式 Reopen 事实，并关联原因与 Evidence，例如：

```text
WorkReopened
reason: production regression
Evidence: INC-912
```

---

## 7.10 “Done”不是领域权威状态

领域层 SHOULD 避免使用模糊的 `Done` 作为权威语义。

GUI MAY 对用户显示“完成”，但底层应能够回答：

```text
Accepted?
Delivered?
Closed?
```

---

# 第八章　Work Graph：工作的结构化组织

## 8.1 定义

> **Work Graph 是当前关于“为了完成 Work，需要哪些可管理工作单元以及它们如何互相约束”的可演化结构化工作模型。**

Work Graph 不是 Goal 本身，也不是永久 Workflow。

必须保持：

```text
Goal / Acceptance
>
Work Graph
```

Graph 是当前完成 Goal 的办法，可以被新 Evidence 修改。

---

## 8.2 Work Graph ≠ Work Tree

底层 MUST 使用 Graph 语义。

GUI 左侧的 Work Tree 是对 Graph 的层级化 Projection。

```text
Work Graph = 领域事实模型
Work Tree  = 人类可读 UI 投影
```

Praxis MUST NOT 为了树形 UI 强迫一个 WorkItem 只能有一个父节点或一个依赖来源。

---

# 第九章　WorkItem：可独立管理的执行单位

## 9.1 定义

> **WorkItem 是 Work Graph 中一个值得被独立执行、验证、阻塞、交接、重试、重新分配或追踪的工作单位。**

例如：

```text
Backend API
PDA Compatibility
Integration Verification
Business Compatibility Decision
```

---

## 9.2 WorkItem 不是 Action

以下通常不应成为 WorkItem：

```text
read FooService.java
run test once
change line 142
```

这些属于 AgentRun 内部 Action / Tool 行为。

正确的产品粒度是：

```text
Work
↓
WorkItem
↓
AgentRun
↓
Plan / Action
↓
Tool
```

---

## 9.3 WorkItem 不绑定 Agent

必须允许：

```text
WorkItem 1 ── 0..N AgentRun
```

一个 WorkItem 可能第一次执行失败，第二次换模型或换专业 Agent，第三次再由 Reviewer 验证。

WorkItem 是稳定责任单位；AgentRun 是执行尝试。

---

## 9.4 Executor 不限于 AI

WorkItem 的执行者 MAY 是：

```text
Agent
Human
Automation
External System
```

例如一个会阻塞下游的业务确认可以成为 Human Decision WorkItem。

Praxis MUST NOT 把所有现实工作强行假定为 AI 可自动完成。

---

# 第十章　Work Graph 关系语义

v0.1 冻结四种主要关系语义：

```text
Decomposition
Dependency
Coordination
Verification
```

第一版 SHOULD 优先使用有限明确语义，而不是任意 `edge.type: string`。

---

## 10.1 Decomposition：分解关系

回答：

> 这项大工作由哪些相对独立工作组成？

例如：

```text
MES-2041
├── Backend
├── Web
├── PDA
└── Integration
```

必须保持：

```text
Decomposition ≠ Dependency
```

父子归属不自动意味着执行顺序。

---

## 10.2 Dependency：前置条件关系

回答：

> 哪个 Outcome 在满足之前，目标 WorkItem 不能 Ready？

Dependency 的核心是前置条件，而不是“上一个任务 Done”。

例如 Web 真正依赖的可能是：

```text
Backend.APIContract = Accepted
```

而不是整个 Backend WorkItem 全部完成。

因此领域模型 SHOULD 允许 Dependency 引用：

- WorkItem Outcome；
- Artifact；
- Verification Result；
- Decision；
- External Condition。

这可以让多个专业工作更早并行。

---

## 10.3 Coordination：变化影响关系

回答：

> 哪个对象变化以后，另一个工作需要重新检查或协调？

例如 Backend 与 PDA 共享 API Contract：

```text
Backend
<-> coordination via API Contract <->
PDA
```

Dependency 主要影响 Readiness；Coordination 主要传播 Change Impact（变化影响）。

二者 MUST NOT 混为一种关系。

---

## 10.4 Verification：验证关系

回答：

> 谁负责证明谁的结果满足什么标准？

例如：

```text
Integration Verification
verifies
[Backend, Web, PDA, overall AC]
```

Verification Relation 可以与 Dependency 同时存在，但表达不同含义。

这使 Praxis 能区分：

```text
谁产生结果
≠
谁证明结果成立
```

---

# 第十一章　Readiness、Waiting、Blocked 与状态传播

## 11.1 Readiness 的基本语义

一个 WorkItem 的 Ready SHOULD 由当前事实推导。

概念上：

```text
Ready(W)
=
LifecycleAllowsExecution(W)
∧ GovernanceAllowsExecution(W)
∧ RequiredDependenciesSatisfied(W)
∧ RequiredResourcesAvailable(W)
∧ ¬Blocked(W)
∧ ¬Paused(W)
```

具体条件由 Work Template / Policy 进一步细化。

---

## 11.2 Dependency 未满足产生 Waiting

正常前置依赖未完成：

```text
Web requires API Contract
API Contract not accepted
→ Web = Waiting
```

它不是异常，也不是 Blocked。

---

## 11.3 状态应重新投影，而不是级联写 Status

当 Backend API Contract 被 Accepted：

```text
Outcome changed
↓
recompute dependent readiness
↓
Web: Waiting → Ready
```

领域权威应是 Outcome / Dependency 等事实；Ready 等状态是 Projection。

实现层 MAY 为性能缓存 Projection，但不得让缓存成为无法重建的唯一真相。

---

## 11.4 AgentRun Failure 不向上机械传播

必须保持：

```text
AgentRun failure ≠ WorkItem failure ≠ Work failure
```

一次 AgentRun 失败以后，可以：

- resume；
- retry；
- reassign；
- change model；
- human takeover；
- replan。

WorkItem 的目标没有因为一次执行失败而消失。

---

## 11.5 Verification Failure 的传播

Verification Failure SHOULD 产生新的 Evidence，并指向受影响范围。

禁止机械：

```text
Integration FAIL
→ reopen every child
```

应根据 Failure Evidence 判断：

```text
Failure points to Web mapping
→ Web needs rework
→ Backend remains accepted
```

具体传播算法留给 Work Graph 专题规范。

---

# 第十二章　Graph Revision：工作计划如何演化

## 12.1 Work Graph 必须可演化

实际工作中，新 Evidence 会发现新节点或旧计划错误。

例如：

```text
Initial:
Backend → Web/PDA → Integration

New Evidence:
DB migration required

Revision:
add DB Migration
add dependency DB Migration → Backend deployment
```

Work Graph MUST 支持运行中修改。

---

## 12.2 Graph 变化必须可追溯

一旦 WorkItem 已产生执行、Artifact、Evidence 或 Change，重要 Graph 变化 MUST NOT 通过无历史的直接覆盖表达。

领域上至少承认：

```text
WorkItemAdded
WorkItemCancelled
WorkItemSuperseded
DependencyAdded
DependencyRemoved
GraphRevisionReason
```

最终 Event Schema 后置到系统设计。

---

## 12.3 Cancel、Delete 与 Supersede

计划阶段、从未执行的临时节点 MAY 更自由地编辑或删除。

一旦存在执行历史：

- SHOULD 使用 Cancelled / Superseded / NotNeeded；
- MUST 保留执行与来源历史；
- MUST NOT 因计划改变而抹掉已经发生的劳动和变更。

`Superseded` 是重要语义：表示旧计划并非简单失败，而是被新的工作方案取代。

---

## 12.4 Graph Revision 的治理

AI MAY 提议 Graph Change，但影响正在运行的工作、业务批准或多个仓库的大规模 Revision SHOULD 进入 Impact Review / Approval。

低风险 Investigation 节点可以更自动化。

详细治理策略后置。

---

# 第十三章　Agent Definition 与 Executor

## 13.1 Agent Definition

> **Agent Definition 是可复用的执行能力配置，而不是一个拥有永久人格和永久聊天记录的产品主体。**

一个 Agent Definition MAY 定义：

```text
preferred models
skills
tools
capabilities
repository scope
runtime policy
instructions
default verification expectations
```

例如：

```text
Backend Developer
Web Developer
UniApp Developer
Integration Reviewer
Security Reviewer
```

---

## 13.2 Agent 不拥有 Work

Agent Definition 是劳动能力，Work 是劳动对象。

关系是：

```text
Agent Definition 1
↓
N Assignments
↓
N AgentRuns
```

同一个 Agent Definition 可以服务许多 Works。

---

## 13.3 Executor

Executor 是更上层的执行主体概念，可包括：

- Agent Definition；
- Human；
- Automation；
- External System。

这使 Work Graph 能表达真实混合生产，而不是 AI-only Workflow。

---

# 第十四章　Assignment：执行责任的分配

## 14.1 定义

> **Assignment 是把一个 WorkItem 的执行责任，在明确 Scope、Goal、Capability 与资源条件下交给某个 Executor 的治理决定。**

Assignment 回答：

> 谁被授权去做什么？

AgentRun 回答：

> 这次实际执行发生了什么？

二者 MUST 区分。

---

## 14.2 Assignment 可被替换

例如：

```text
WorkItem: Backend API

Assignment #1
→ GPT-backed Backend Agent
→ Run failed

Assignment #2
→ Claude-backed Backend Agent
→ Run completed
```

WorkItem 仍然是同一个长期责任对象。

---

## 14.3 Assignment 不得绕过 Readiness

Automation / Planner Agent MAY 创建 Assignment，但真正启动执行前 MUST 满足 WorkItem 的 Readiness、Capability 和资源条件。

自动分配没有绕过 Work Graph 的主权。

---

# 第十五章　AgentRun：一次真实执行过程

## 15.1 定义

> **AgentRun 是某个 Executor 根据一个 Assignment，在明确模型、工具、权限、仓库环境和 Runtime 条件下，对 WorkItem 进行的一次可追踪执行尝试。**

AgentRun 是一次劳动过程。

---

## 15.2 AgentRun 保存的语义

AgentRun SHOULD 能回答：

```text
由谁执行？
为什么执行？
使用什么 Model / Agent Definition？
何时开始和结束？
关联哪些 Session？
产生哪些 Artifact / Evidence / RepoChange？
结果是什么？
为什么中止或失败？
消耗多少资源？
```

---

## 15.3 AgentRun Completion 不拥有最终 Acceptance

AgentRun 可以声明：

```text
completed
failed
cancelled
blocked
```

但它不能直接把 WorkItem 提升为 Accepted。

Acceptance 属于 Verification / WorkItem Policy。

---

## 15.4 Resume 还是 New Run

SHOULD Resume 同一个 AgentRun 的情况：

- 进程 Crash；
- 机器重启；
- 网络短暂中断；
- 人工 Pause/Resume；
- Runtime Context Compaction；
- Goal、Assignment 和执行策略未发生实质变化。

SHOULD 创建新 AgentRun 的情况：

- 更换 Agent Definition；
- 更换主执行模型作为重新执行策略；
- Reviewer 开始独立审查；
- Human Takeover；
- 原执行假设被根本证伪，决定重新开始新的执行尝试。

具体判定可以在 Agent Work 专题中细化。

---

# 第十六章　Session：Runtime 的持久运行容器

## 16.1 定义

> **Session 是 AgentRun 在 Praxis Runtime 中保存、恢复和审计推理—行动过程的运行时容器。**

典型层级：

```text
AgentRun
↓
Session
↓
Turn
↓
Event
```

Session 可以保存：

- model interaction；
- tool call/result；
- Observation；
- Hypothesis；
- Runtime Plan；
- Capability state；
- Context projection；
- recovery state。

---

## 16.2 Session 不是 Workbench 最高导航对象

默认 GUI SHOULD 展示：

```text
Work
└── WorkItem
    ├── Run #17 failed
    └── Run #18 running
```

而不是：

```text
Chat 173
Chat 174
Chat 175
```

用户可以从 AgentRun 下钻到 Session。

---

## 16.3 一个 AgentRun 可引用多个 Session

普通情况 SHOULD 是：

```text
1 AgentRun = 1 main Session
```

领域模型 MAY 支持多个 Session，例如 Child Investigation / Subagent Session。

但如果某个 Subagent 工作具有：

- 独立 Goal；
- 独立 Acceptance；
- 独立 Artifact；
- 会阻塞其他工作；

则 SHOULD 提升为 WorkItem + Assignment + AgentRun，而不是隐藏在巨型 Session 中。

---

# 第十七章　Artifact 与 Evidence

## 17.1 Artifact

> **Artifact 是 Work 执行过程中产生，并值得被其他工作、Verification、Handoff 或 Delivery 持久引用的工作成果。**

Artifact 不限于文件。

可能包括：

- API Contract；
- Design Document；
- SQL Migration；
- Test Report；
- Screenshot；
- Log Bundle；
- Build Package；
- OpenAPI Schema；
- Decision Record；
- Patch。

---

## 17.2 Artifact 所有权

Artifact MAY 由 AgentRun、Human、Automation 或 Tool 产生，但其长期归属通常应关联 Work / WorkItem，而不是只留在某个 Session 中。

换 Agent 以后仍然应该存在的工作成果，不能只存在于旧 Agent 的聊天历史。

---

## 17.3 Evidence 是 Artifact 的证明角色

v0.1 倾向：

> **Evidence 不是另一种文件类型，而是某个 Observation / Claim / Verification 对 Artifact 或外部事实的证明引用关系。**

例如 `test-report.json` 是 Artifact；当它被用来证明 AC-02 时，它在这个 Verification 中扮演 Evidence。

这避免重复建模“Artifact 表”和“Evidence 文件表”。

---

# 第十八章　Handoff：跨执行主体的结构化交接

## 18.1 定义

> **Handoff 是 WorkItem 在执行主体发生变化或专业域流转时，对当前现实工作状态进行结构化交接的持久记录。**

Handoff 不是 Conversation Summary。

---

## 18.2 Handoff 传什么

一个有价值的 Handoff SHOULD 优先包含：

```text
Goal / Scope
Accepted Outcomes
Artifacts / Contracts
Relevant Evidence
Constraints
Assumptions
Open Challenges
Open Risks
ChangeSet / RepoChange refs
Expected Next Work
```

不应该默认传完整上游聊天历史。

原则：

> **State Transfer > Conversation Transfer。**

---

## 18.3 Handoff 与 Assignment

二者不同：

```text
Handoff
= 接手者应该知道什么现实状态

Assignment
= 谁接下来负责什么工作
```

典型链路：

```text
Backend AgentRun
→ Handoff
→ Frontend Assignment
→ Frontend AgentRun
```

---

## 18.4 Handoff 何时需要

SHOULD 在以下情况产生正式 Handoff：

- Agent → Agent；
- Agent → Human；
- Human → Agent；
- 工作跨专业域；
- 长任务需要以新 AgentRun 接力。

同一个 AgentRun 的技术 Resume MUST NOT 强制生成 Handoff。

Handoff 是否需要显式 Accept/Reject，留到专题规范决定。

---

# 第十九章　Repository 与 RepoChange

## 19.1 Repository

Repository 是 Workspace 中一种长期代码资产。

关系：

```text
Workspace 1 → N Repository
WorkItem N <-> N Repository
```

WorkItem SHOULD 优先保持单仓库责任边界，但领域层 MUST 允许合理的跨仓库 WorkItem。

---

## 19.2 RepoChange

> **RepoChange 表示某个 Work 在单个 Repository 中形成的逻辑变更事实/交付候选。**

它可以引用：

```text
base revision
branch
Git worktree
modified files
commits
diff
merge status
```

具体 Git Schema 后置。

---

## 19.3 AgentRun 不独占 RepoChange

AgentRun 可以贡献 RepoChange，但 RepoChange SHOULD 长期归属 Work / ChangeSet。

原因：一个 RepoChange 可能经历多个 Runs：

```text
Run #1 implementation
Run #2 review fix
Run #3 conflict resolution
```

最终仍然是同一项 Work 在该 Repository 的交付变化。

---

# 第二十章　ChangeSet：跨仓库交付变更集合

## 20.1 定义

> **ChangeSet 是为实现一个 Work 而产生的、跨一个或多个 Repository 的逻辑变更集合。**

例如：

```text
MES-2041 ChangeSet
│
├── mes-server RepoChange
├── mes-web RepoChange
└── mes-pda RepoChange
```

ChangeSet 是 Work 的代码交付视图，而不是某个 Agent 的成果袋。

---

## 20.2 ChangeSet 与 Commit

必须保持：

```text
Git Commit
= 单 Repository 的版本控制事实

ChangeSet
= Work 的跨 Repository 交付对象
```

用户最终应能回答：

> MES-2041 整体改了什么？

而不是手工去五个 Repository 搜索 commit。

---

## 20.3 一个 Work 可以有多个 ChangeSet

允许：

- 主实现 ChangeSet；
- Integration 后 Hotfix；
- 不同 release line 的 Backport；
- Follow-up compatibility patch。

普通 Feature SHOULD 默认拥有一个 Primary ChangeSet。

一个 ChangeSet SHOULD 有一个 Primary Work；可以关联 Related Works，但不鼓励一个 ChangeSet 同时无主次归属于大量 Work。

---

# 第二十一章　Verification：为什么可以相信结果

## 21.1 定义

> **Verification 是针对明确 Target 与 Criteria，使用可引用 Evidence 形成的结果判断。**

Verification MUST 说明自己验证的范围，而不是泛化成“已验证=true”。

---

## 21.2 Verification Target

Verification MAY 针对：

- Artifact；
- WorkItem；
- RepoChange；
- ChangeSet；
- Work；
- Delivery outcome。

通用结构概念：

```text
Verification
├── Target
├── Criteria
├── Verifier
├── Evidence
├── Result
├── Scope / Environment
└── Time
```

---

## 21.3 Verifier 不限于 Agent

Verifier 可以是：

- deterministic test；
- CI；
- Agent Reviewer；
- Human Reviewer；
- External System。

Reviewer Agent 不需要成为特殊领域对象。它仍是 Agent Definition + Verification WorkItem + AgentRun。

---

## 21.4 局部 Acceptance 不等于整体 Acceptance

Backend、Web、PDA 分别 Accepted，并不自动证明整体 Work Accepted。

父 Work MUST 使用 Work-level Verification / Acceptance Criteria 判断整体结果。

原则：

> **Local correctness ≠ global correctness。**

---

# 第二十二章　Delivery：怎样进入目标交付位置

## 22.1 定义

> **Delivery 是将已经形成并满足相应 Acceptance 的工作成果推进到目标交付位置的行为及结果记录。**

对代码工作，Delivery 可能是：

- PR/MR created；
- merged；
- package built；
- release published；
- deployed。

对 Research / Decision Work，Delivery 可能是：

- report published；
- ADR accepted；
- decision communicated。

---

## 22.2 Delivery Target

Delivery SHOULD 明确 Target，例如：

```text
GitLab main
release/2.3
staging
production
customer acceptance
architecture decision registry
```

---

## 22.3 Delivery Failure ≠ Work Failure

必须保持：

```text
Delivery Attempt Failed
≠
Implementation Failed
≠
Work Goal Failed
```

例如 Jenkins 暂时故障，只说明这次 Delivery Attempt 失败，Accepted ChangeSet 可以重新交付。

---

# 第二十三章　对象所有权与生命周期矩阵

以下矩阵是 v0.1 的重要领域基线。

| 对象 | 主要归属 | 是否长期持久 | 可否多次/替换 | 核心意义 |
|---|---|---:|---:|---|
| Workspace | Product | 是 | 长期 | 逻辑生产空间 |
| Repository | Workspace | 是 | N | 代码资产 |
| Work | Workspace | 是 | N | 最高工作对象 |
| Goal | Work / WorkItem | 是 | 可修订 | 目标现实状态 |
| Constraint | Work / WorkItem | 是 | 可修订 | 不可随意破坏的边界 |
| Acceptance | Work / WorkItem | 是 | 可版本化 | 完成判断标准 |
| Work Graph | Work | 是 | 可修订 | 当前工作结构 |
| WorkItem | Work Graph | 是 | N | 稳定执行责任单位 |
| Agent Definition | Workspace | 是 | N | 可复用执行能力配置 |
| Assignment | WorkItem | 是 | 可替换 | 谁被授权做什么 |
| AgentRun | WorkItem / Assignment | 是 | 0..N | 一次真实执行过程 |
| Session | AgentRun / Runtime | 是 | 1..N | 可恢复运行历史 |
| Artifact | Work / WorkItem | 是 | N | 持久工作成果 |
| EvidenceRef | Claim / Verification | 是 | N | Artifact/事实的证明角色 |
| Handoff | WorkItem execution flow | 是 | N | 结构化工作状态交接 |
| RepoChange | Work / ChangeSet | 是 | N | 单仓库逻辑变更 |
| ChangeSet | Work | 是 | 0..N | 跨仓库交付集合 |
| Verification | Target object | 是 | N | 有证据的结果判断 |
| Delivery | Work | 是 | N | 推进到目标交付位置 |
| Automation | Workspace | 是 | N | 工作事件驱动策略，细节后置 |

---

# 第二十四章　MES 参考场景

本章用一个跨仓库 MES 需求证明领域对象能够形成完整闭环。

## 24.1 Work 创建

```text
Work: MES-2041
Type: Feature
Title: PDA报工增加首检状态校验并在Web显示

Goal:
所有相关终端统一执行首检规则，并正确展示首检状态。

Affected Repositories:
mes-server
mes-web
mes-pda
```

Acceptance：

```text
AC-01 未完成首检时禁止相应报工
AC-02 首检通过后允许报工
AC-03 Web正确显示状态
AC-04 PDA行为与Backend规则一致
AC-05 不需要首检的现有流程不变
AC-06 Integration/regression pass
```

---

## 24.2 初始 Work Graph

```text
Analysis
   │
   ▼
Backend Contract
   │
 ┌─┴────────┐
 ▼          ▼
Web        PDA
  \        /
   \      /
   Integration
       │
    Delivery
```

`Backend Contract` 的 Accepted Artifact 成为 Web / PDA 的 Dependency Outcome，因此客户端可以在 Backend 完整实现结束之前开始工作。

---

## 24.3 Agent Work

```text
Backend WorkItem
↓
Assignment: Backend Developer Agent
↓
AgentRun #17
↓
Runtime Session S-17
↓
Artifacts:
- API Contract
- Integration fixture
↓
RepoChange: mes-server
```

Backend 完成 Contract 后生成 Handoff 给 Web/PDA，而不是传递 Backend Session 的完整聊天记录。

---

## 24.4 新 Evidence 导致 Graph Revision

PDA AgentRun 发现：

```text
旧终端版本不支持新字段
```

产生 Blocking Challenge。

系统增加 Human Decision WorkItem：

```text
Compatibility Decision
```

人决定必须兼容旧版本，于是 Graph Revision 新增：

```text
Backend Compatibility Layer
```

PDA 从 Blocked 转为 Waiting，兼容层 Accepted 后重新 Ready。

Graph 变化有历史，不覆盖原计划。

---

## 24.5 ChangeSet

最终产生：

```text
ChangeSet MES-2041
│
├── mes-server
│   ├── branch / commits / diff
│   └── contributed by Run #17 / #19
│
├── mes-web
│   └── branch / commits / diff
│
└── mes-pda
    └── branch / commits / diff
```

Integration Verification 对整体 ChangeSet 和 Work Acceptance 进行验证。

---

## 24.6 Delivery

```text
Work Acceptance: ACCEPTED
ChangeSet: ACCEPTED
Delivery #1: MR created
Delivery #2: merged
Delivery #3: staging deployed
Delivery #4: production deployed
```

Production Delivered 不一定立刻 Closed；还可以存在观察期或业务确认。

---

# 第二十五章　产品领域不变量

以下原则在 v0.1 中视为正式产品领域不变量。

## 25.1 Work over Chat

Work 是产品最高工作对象；Session 不能重新成为默认信息架构中心。

## 25.2 Goal > Work Graph

Graph 是达到 Goal 的当前办法。Graph 执行完不自动等于 Goal 达成。

## 25.3 Work Graph > Work Tree

Graph 是领域模型；Tree 是 UI Projection。

## 25.4 Decomposition ≠ Dependency

归属与先后条件严格分离。

## 25.5 Dependency is outcome-based

依赖应尽可能表达所需 Outcome / Artifact / Verification，而不是粗暴等待整个 WorkItem Done。

## 25.6 Execution-derived State

Ready、Waiting、Executing、Verifying 等 SHOULD 尽可能由当前事实推导。

## 25.7 Approved ≠ Ready

治理意志和客观执行条件必须分离。

## 25.8 Waiting ≠ Blocked ≠ Paused

正常等待、客观障碍和主动暂停是三种不同事实。

## 25.9 AgentRun failure ≠ WorkItem failure

一次执行失败不能自动否定长期工作目标。

## 25.10 Execution Completed ≠ Accepted

执行者声明完成不能替代 Verification。

## 25.11 Accepted ≠ Delivered ≠ Closed

结果成立、成果交付、治理关闭是三个不同阶段。

## 25.12 Parent has own Acceptance

父 Work 的完成必须有整体 Acceptance，不允许仅由子 WorkItem 全绿推导。

## 25.13 Agent Definition ≠ AgentRun ≠ Session

能力配置、一次执行、运行历史严格分层。

## 25.14 State Transfer > Conversation Transfer

跨 Agent 交接默认传结构化工作事实，不默认传无限 Conversation。

## 25.15 Artifact ≠ Evidence

Artifact 是工作成果；Evidence 是它在某个判断中的证明角色。

## 25.16 AgentRun contributes to RepoChange

RepoChange/ChangeSet 属于 Work 的长期交付结果，不属于某一次 AgentRun 私有。

## 25.17 Verification is scoped

Verification 必须说明 Target、Criteria、Evidence 与 Scope。

## 25.18 Graph Revision is auditable

有执行历史的工作结构不能被静默删除或覆盖。

## 25.19 One Agent When Enough

Multi-Agent 只在工作能够合理分离时产生，不为了“多 Agent”而制造 WorkItem。

## 25.20 Product objects require independent lifecycle

未来新增一级领域对象，必须证明它具有独立生命周期、所有权和产品意义，不能只是实现细节。

---

# 第二十六章　v0.1 明确不做

本规范完成的是领域语义，不提前解决以下问题：

- 不定义数据库表和存储引擎；
- 不决定 Work Graph 使用关系型、图数据库还是 Event Projection；
- 不定义 Event Schema；
- 不定义 GUI Framework；
- 不决定 Tauri / Electron；
- 不设计最终 Work Tree UI；
- 不定义 Automation DSL；
- 不定义 Multi-Agent Scheduler；
- 不定义 Git Worktree 的物理目录策略；
- 不定义 RepoChange 的最终 Git Schema；
- 不定义 Issue Tracker 双向同步协议；
- 不定义 Handoff Wire Protocol；
- 不定义 Requirement Management 完整子系统；
- 不定义 Team/Server 多用户权限；
- 不定义远程 Agent 基础设施；
- 不把所有 Subagent 都提升为 WorkItem；
- 不把每个 Runtime Action 都暴露到 Work Graph。

这些内容必须建立在本文领域模型之上，通过后续专题规范解决。

---

# 第二十七章　后续专题待决问题

完成本文后，后续产品设计按专题推进，而不是继续向本规范无限加入细节。

## 27.1 Work Graph 与生命周期详细规范

需要进一步解决：

- Work Graph relation 的精确定义；
- Dependency Condition 表达；
- Readiness Policy；
- Parent/child projection；
- Verification Failure 精确传播；
- Graph Revision 的影响评估；
- Derived State 的优先级；
- Work Type / Template 的生命周期差异。

---

## 27.2 Agent Work / Handoff 规范

待决：

- Assignment 生命周期；
- AgentRun Resume/New Run 精确边界；
- Handoff Preparation / Acceptance；
- Agent Capability Profile；
- Multi-Agent work decomposition；
- Child Session 何时提升为 WorkItem；
- 人工接管与 Agent 接力。

---

## 27.3 Multi-Repository & Git Model

待决：

- Repository workspace discovery；
- Git Worktree isolation；
- Branch strategy；
- RepoChange / ChangeSet schema；
- cross-repo review；
- commit / MR / merge / backport；
- working tree conflict ownership。

---

## 27.4 Automation Model

待决：

```text
Trigger
Condition
Action
```

以及：

- Ready 自动分配 Agent；
- Verification 失败后的自动 Rework；
- dependency 解锁；
- schedule / external event；
- Capability 与审批继承；
- Automation failure semantics。

---

## 27.5 Workbench UX / Information Architecture

待决：

- Work / Code / Git / Agents / Automation / Runtime 主导航；
- Work Tree 如何从 Graph 投影；
- 多仓库上下文；
- ChangeSet Review；
- AgentRun 与 Runtime Inspector；
- Progressive Disclosure；
- 搜索与跨 Work 导航。

---

## 27.6 Workbench System Design

最后才决定：

- Desktop 技术栈；
- Local service / daemon；
- Runtime IPC；
- Work Domain persistence；
- Git service；
- extension system；
- background agent execution；
- remote/team evolution。

---

# 第二十八章　术语表

| 术语 | 定义 |
|---|---|
| Workspace | 长期管理相关仓库、工作、Agent 与集成的逻辑生产空间 |
| Work | 由 Goal 驱动、最终要求现实状态改变的最高工作对象 |
| Requirement | 描述为什么需要 Work、希望结果与业务约束的输入/上下文 |
| Goal | Work 最终希望达到的现实状态 |
| Constraint | 即使为了 Goal 也不能随意破坏的边界 |
| Acceptance Criteria | 判断 Work/WorkItem 结果是否满足目标的标准 |
| Work Type | Feature/Bug/Incident 等工作业务类型 |
| Work Template | 可复用的初始 Work Graph / Acceptance / Automation 建议 |
| Work Graph | 当前为了完成 Work 而形成的可演化工作关系模型 |
| Work Tree | Work Graph 面向人的层级化 UI 投影 |
| WorkItem | 可独立执行、验证、阻塞、交接或重新分配的工作单位 |
| Decomposition | Work / WorkItem 的组成归属关系 |
| Dependency | 影响目标 WorkItem Readiness 的前置条件关系 |
| Coordination | 传播变化影响与一致性要求的工作关系 |
| Verification Relation | 指定谁验证谁、证明什么标准的关系 |
| Readiness | 当前是否具备合法启动执行的客观条件 |
| Agent Definition | 可复用的 Agent 执行能力配置 |
| Executor | Agent、Human、Automation 或 External System 等执行主体 |
| Assignment | 把 WorkItem 执行责任交给 Executor 的治理决定 |
| AgentRun | 对 WorkItem 的一次可追踪实际执行尝试 |
| Session | AgentRun 在 Praxis Runtime 中的可恢复运行历史容器 |
| Artifact | 值得长期引用的工作成果 |
| Evidence | Artifact/事实在某个判断中的证明角色 |
| Handoff | 执行主体变化时的结构化工作状态交接 |
| Repository | Workspace 中的一份版本控制代码资产 |
| RepoChange | 一个 Work 在单 Repository 中形成的逻辑变更 |
| ChangeSet | 一个 Work 跨一个或多个 Repository 的逻辑交付集合 |
| Verification | 对明确 Target/Criteria 使用 Evidence 得出的结果判断 |
| Delivery | 将已接受成果推进到目标交付位置的行为和结果记录 |
| Automation | 基于工作事实自动采取行动的 Workspace 级策略；详细模型后置 |
| Execution-derived State | 从真实执行/依赖/验证事实推导的工作状态 |
| Graph Revision | Work Graph 因新 Evidence 或计划变化产生的可追溯修订 |

---

# 结语

Praxis Workbench 的产品世界现在可以被压缩成一条清楚的生产链：

```text
Workspace
↓
Work
↓
Goal / Constraints / Acceptance
↓
Work Graph
↓
WorkItem
↓
Assignment
↓
AgentRun / Human / Automation
↓
Session / Actions
↓
Artifacts / Evidence / RepoChanges
↓
Handoff / Verification
↓
ChangeSet
↓
Work-level Acceptance
↓
Delivery
```

这里最重要的变化，是把 AI 从“聊天框中的建议者”放回真实生产结构中：Agent 不拥有工作目标，也不拥有最终完成主权；它只是被分配到 WorkItem 上的一次执行主体。Work Graph 可以随着实践改变，状态可以从执行事实推导，跨 Agent 传递的是结构化现实状态，跨仓库交付的是 ChangeSet，最终是否完成由 Verification 与 Work-level Acceptance 决定。

因此 Praxis Workbench 的领域核心不再是 Session，也不是 Agent，而是：

> **Work + Work Graph + Evidence-backed Execution。**

本规范 v0.1 到此冻结。后续专题应在这一领域边界上继续细化，而不重新定义最高产品对象。
