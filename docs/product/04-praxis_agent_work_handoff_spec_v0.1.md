# Praxis Agent Work / Handoff 详细规范

## v0.1 产品基线

**版本：v0.1**  
**日期：2026-08-28**  
**文档性质：产品执行模型基线 / Normative Agent Work Baseline**  
**上位文档：**《Praxis 产品白皮书》《Praxis Workbench 产品领域模型与核心概念规范 v0.1》《Praxis Work Graph 与工作生命周期详细规范 v0.1》

> 本规范冻结 Praxis Workbench 中 WorkItem 如何被分配给 Agent / Human / Automation，AgentRun 与 Runtime Session 如何划界，跨 Agent Handoff 如何可靠传递工作状态，以及多 Agent 并行执行时如何隔离环境、汇总 RepoChange 并形成可验证 ChangeSet。本文不定义数据库 Schema、RPC、GUI 技术栈、Git Worktree 物理目录、具体 Agent Scheduler 算法或模型 API 实现。

---

# 目录

1. 文档定位与规范用语
2. Agent Work 总体模型
3. Executor 与 Agent Definition
4. Scheduling 与 Assignment
5. Assignment Policy 与模型选择
6. AgentRun：一次真实执行过程
7. Resume、Rerun、Retry 与 Escalation
8. Runtime Session 边界
9. Execution Environment
10. Handoff Contract
11. Handoff 生命周期、有效性与版本
12. Agent Communication：临时沟通与持久协作
13. 并发执行模型
14. Git Worktree 与 Repository 隔离
15. Competitive / Exploratory Runs
16. Review 与 Verification 隔离
17. RepoChange / ChangeSet 贡献模型
18. Resource / Capability / Assignment Lease
19. Human Assignment、注意力与治理升级
20. MES 多 Agent 参考场景
21. 对象所有权矩阵
22. Agent Work 产品不变量
23. v0.1 明确不做
24. 后续专题待决问题
25. 术语表

---

# 第一章　文档定位与规范用语

## 1.1 本文解决什么问题

前两份产品规范已经回答：

```text
Work 是什么？
WorkItem 如何组成 Work Graph？
WorkItem 什么时候 Ready / Waiting / Blocked？
Graph 如何根据 Evidence 修订和传播影响？
```

但 Work Graph 只是“工作组织模型”。它本身不会写代码、调查问题、运行测试或完成交付。

Praxis 要进入真实生产研发环境，还必须回答：

```text
Ready 的 WorkItem 怎样真正进入执行？
谁来执行？
Assignment 和 AgentRun 有什么不同？
一次技术中断应该 Resume 还是创建新 Run？
更换模型什么时候属于同一个执行过程，什么时候属于新尝试？
Agent A 的工作怎样可靠交给 Agent B？
多 Agent 同时改多个仓库时怎样避免互相覆盖？
Review / Verification 为什么不能与 Implementation 混为一个 Run？
多个 AgentRun 的代码成果最终怎样汇合成一个 Work 的 ChangeSet？
```

本文即负责冻结这些产品语义。

---

## 1.2 规范用语

本文使用：

- **MUST / 必须**：后续产品设计与实现不得违反，除非通过正式产品规范 Revision；
- **MUST NOT / 禁止**：出现即视为 Agent Work 领域边界破坏；
- **SHOULD / 应当**：默认产品方向，偏离必须有清晰理由；
- **MAY / 可以**：允许的扩展，不构成 v0.1 必备语义。

本文中的状态、Policy、Role 为产品领域语义，不等价于最终数据库字段或 TypeScript enum。

---

## 1.3 五条最高原则

### WorkItem 是稳定责任单位

Agent、模型、Run 可以替换，WorkItem Goal / Acceptance 不能跟随某个 Agent 一起消失。

### Assignment 与 Execution 分离

“决定由谁做”与“实际做了一次”是两个事实。

### Work State Transfer over Conversation Transfer

跨执行主体交接应传递结构化工作状态，而不是无限聊天历史。

### Multi-Agent 来源于 Work 分离

多个 Agent 的存在必须由不同 WorkItem、不同执行角色或显式 Competitive / Investigation 需要产生，而不是为了“多 Agent”本身。

### Execution Isolation before Concurrency

允许并行前必须先明确写域、资源边界和成果汇合方式。并发不能以共享工作目录和隐式状态为代价。

---

# 第二章　Agent Work 总体模型

## 2.1 核心执行链

Praxis Workbench 的执行主线为：

```text
Work
  ↓
Work Graph
  ↓
WorkItem
  ↓
Scheduling
  ↓
Assignment
  ↓
Executor
  ↓
AgentRun / Human Execution / Automation Execution
  ↓
Runtime Session / Execution Environment
  ↓
Actions / Tools / Events
```

产出主线为：

```text
Execution
  ├─ Artifact
  ├─ Evidence
  ├─ Handoff
  └─ RepoChange Contribution
             ↓
          ChangeSet
             ↓
        Verification
             ↓
          Delivery
```

这两条线 MUST 保持分离：执行主体不拥有 Work 的最终成果主权；Run 结束后 Work、Artifact、ChangeSet、Verification 仍继续存在。

---

## 2.2 产品层级

推荐的稳定层级：

```text
Workspace
  ↓
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
Turn / Tool / Event
```

其中：

- `Work`：长期产品工作对象；
- `WorkItem`：可独立执行、阻塞、验证和交接的责任单元；
- `Assignment`：把责任授予某个 Executor 的治理决定；
- `AgentRun`：一次真实 AI 执行尝试；
- `Session`：Praxis Runtime 的可恢复运行历史。

Workbench MUST NOT 退化为 “Session list / Chat list” 产品。

---

## 2.3 执行者不是事实所有者

一个 AgentRun 可以产生：

```text
implementation
artifact
hypothesis
repo diff
test evidence
```

但以下对象的权威归属不应落在 AgentRun：

```text
Work Goal
WorkItem Acceptance
Workspace Knowledge
Current API Contract
Current ChangeSet
Final Verification
Delivery status
```

这些属于 Work / WorkItem / Workspace / ChangeSet 等稳定对象。

---

# 第三章　Executor 与 Agent Definition

## 3.1 Executor

`Executor` 是能够承担 Assignment 的执行主体抽象。

v0.1 至少承认：

```text
Agent
Human
Automation
External System
```

例如：

```text
Backend Implementation   → Agent
Compatibility Decision   → Human
Run Integration Tests    → Automation
Create GitLab MR          → External Integration
```

Work Graph MUST NOT 假设所有 WorkItem 都必须由 AI 完成。

---

## 3.2 Agent Definition

> **Agent Definition 是一组可复用的执行能力配置，而不是一个长期拥有工作和永久聊天记忆的虚拟人格。**

一个 Agent Definition MAY 包含：

```text
Capability profile
Skills
Tool set
Repository roles
Preferred model policy
Runtime policy
Default instructions
Default verification expectations
```

例如：

```text
Backend Developer
Web Developer
UniApp Developer
Investigation Agent
Code Reviewer
Integration Reviewer
```

---

## 3.3 Agent 不拥有长期项目知识

Praxis SHOULD 遵循：

```text
Knowledge belongs primarily to Workspace / Work.
Capability belongs primarily to Agent Definition.
```

长期业务知识、Repository Knowledge、Decision、Artifact、Work History MUST NOT 主要存储为某个 Agent 的私有永久记忆，否则更换模型或 Agent Definition 将导致知识所有权错乱。

AgentRun 应从当前 Work / Workspace 状态按需构建 Context。

---

## 3.4 Agent Definition 与 Model 分离

`Backend Developer` 不应等价于某个模型。

合理关系：

```text
Agent Definition
  ├─ preferred model
  ├─ fallback model
  └─ escalation model
```

真正的 AgentRun 启动后必须记录实际使用的模型和配置。

因此未来模型升级不会重写 Work Graph 或 Agent 类型。

---

# 第四章　Scheduling 与 Assignment

## 4.1 Ready 不等于开始执行

必须严格区分：

```text
Ready
  ↓
Scheduled
  ↓
Assigned
  ↓
Executing
```

- `Ready`：Work Graph 条件允许执行；
- `Scheduling`：决定哪些 Ready WorkItem 当前优先获得执行资源；
- `Assignment`：确定由谁、以什么约束执行；
- `AgentRun`：实际开始劳动。

Ready WorkItem MUST NOT 自动拥有一个 AgentRun，除非 Automation Policy 明确允许。

---

## 4.2 Scheduling 选择工作

Scheduler 主要回答：

> 在当前所有 Ready WorkItem 中，哪些应该先占用有限生产资源？

第一版产品语义 SHOULD 考虑：

1. Business Priority；
2. Dependency / Critical Path；
3. Unblocking Value（完成后能释放多少下游工作）；
4. Deadline / Delivery Window；
5. Execution Capacity；
6. Resource Conflict；
7. Cost / Budget；
8. Human Attention Capacity。

Praxis MUST NOT 以 “让所有 Agent 100% 忙碌” 作为主要调度目标。

更合理目标为：

> **提高 Work 的端到端流动速度，同时避免 Verification、Integration 和人类注意力形成新的瓶颈。**

---

## 4.3 Assignment 选择执行者

Assignment 回答：

```text
谁来做？
做哪个 WorkItem？
执行范围是什么？
允许使用哪些资源和 Capability？
期望产生哪些 Outcome？
本次责任什么时候结束？
```

概念示例：

```text
WorkItem: Backend API
Executor: Backend Developer Agent
Repositories: mes-server
Goal: implement accepted quality contract
Constraints: preserve legacy compatibility
Capabilities: fs.read / fs.write / shell
Required Outcome:
  - implementation
  - unit verification
  - handoff-ready API contract
```

Assignment MUST NOT 自行改变 WorkItem Goal / Acceptance。

---

## 4.4 Assignment 的来源

Assignment MAY 由：

```text
Human
Automation
Scheduler
Planner Agent proposal
Work Template policy
```

产生。

但最终必须经过 WorkItem Readiness、Capability、Resource、Risk Policy 的正式检查。

Planner Agent 没有“因为自己认为该做”就绕过 Work Graph 的权力。

---

# 第五章　Assignment Policy 与模型选择

## 5.1 Agent 匹配按能力，不按名称

Assignment SHOULD 先形成 WorkItem Requirements：

```text
required skills
repository access
required tools
required capabilities
risk class
execution role
```

再匹配 Candidate Agent Definitions。

必须区分：

### Hard Requirement

不满足则不能 Assignment。

### Preference

满足更优，但不构成执行合法性的前提。

例如：

```text
Hard:
  mes-server write capability
  Java build toolchain

Preference:
  Spring experience
  recent success in mes-server
  lower-cost model
```

---

## 5.2 Minimum Sufficient Model

Praxis SHOULD 优先选择满足任务可靠性要求的最小充分模型，而不是所有 WorkItem 一律使用最昂贵模型。

例如：

```text
Low risk docs/fixtures     → efficient model
Normal implementation     → primary coding model
Tier-0 / security / core   → strongest model + independent review
```

Risk Policy 可以提高模型、Review、Verification 门槛，但模型强度本身 MUST NOT 替代测试或 Acceptance。

---

## 5.3 自动化级别

Assignment SHOULD 支持三个产品模式：

### Manual

系统推荐执行者，人显式启动。

### Assisted

系统选择执行者和执行配置，人确认启动。

### Automatic

满足 Policy 后自动创建 Assignment 并启动执行。

生产型 Workbench 的默认演进路线 SHOULD 为：

```text
Manual
→ Assisted
→ Selective Automatic
→ Broader Automatic
```

而不是首次接入仓库即全自动。

---

## 5.4 风险与自动化

不同 Work Type / Risk MAY 使用不同 Assignment Policy：

| 工作 | 推荐默认 |
|---|---|
| Research / read-only investigation | Automatic / Assisted |
| Unit test / static check | Automatic |
| 普通业务实现 | Assisted |
| DB migration | Manual / high-governance |
| Production destructive action | Human approval mandatory |
| Incident investigation | Auto investigate; destructive action gated |

---

# 第六章　AgentRun：一次真实执行过程

## 6.1 定义

> **AgentRun 是某个 Agent 根据一个 Assignment，在确定模型、Runtime、权限、Execution Environment 和工作基线条件下，对 WorkItem 进行的一次连续执行尝试。**

AgentRun 是“劳动过程”，不是工作目标本身。

---

## 6.2 AgentRun 应回答的问题

一个 Run 至少应可追溯：

```text
Assignment
Agent Definition
Actual Model / reasoning policy
Execution role
Start / end
Runtime Session(s)
Execution Environment
Capabilities / resources
Produced Artifact refs
Evidence refs
RepoChange contributions
Cost / token / wall time
Termination reason
```

---

## 6.3 Run Role

v0.1 建议至少区分：

- `implementation`：生产实现；
- `investigation`：调查、复现、探索；
- `review`：独立代码/设计检查；
- `verification`：运行验证体系；
- `support`：检索、资料、辅助工作。

Run Role 直接影响并发、写权限和成果归属 Policy。

---

## 6.4 AgentRun 结束语义

Run 结束不应只有 success/failure 二值。

建议产品语义：

- `completed`：执行者完成当前 Assignment；
- `blocked`：需要新的外部条件才能继续；
- `paused`：主动暂时停止，仍可恢复；
- `cancelled`：治理主体终止本次执行；
- `failed`：执行过程本身无法可靠继续；
- `superseded`：新的执行策略/Run 取代当前 Run；
- `handoff`：责任转移到另一个 Executor。

`AgentRun completed` MUST NOT 自动推出 `WorkItem accepted`。

---

# 第七章　Resume、Rerun、Retry 与 Escalation

## 7.1 Resume 同一个 Run

如果执行责任、Executor、Assignment 和执行连续性仍然成立，则技术性中断 SHOULD Resume 同一 AgentRun。

典型：

```text
process crash
network interruption
provider temporary failure
user pause/resume
context compaction
machine restart
Runtime Session recovery
```

这类事件是“同一次劳动过程被打断”，不应人为制造新的 Run。

---

## 7.2 创建新 AgentRun

出现执行身份或执行战略断裂时 SHOULD 创建新 Run：

- 更换 Executor / Agent Definition；
- 显著换模型并作为独立新尝试；
- Reviewer / Verification 开始；
- 原执行路线已经不能作为同一次连续劳动继续；
- Human takeover；
- Competitive / independent second approach。

---

## 7.3 Replay 与 Rerun 分离

`Replay`：重建历史发生过什么，不重新执行真实副作用。

`Rerun`：重新尝试工作，MUST 创建新的 AgentRun。

Rerun 可以选择：

- fresh context；
- informed by old Artifact/Evidence；
- fork from a Session checkpoint。

但都属于新现实执行过程。

---

## 7.4 Retry Budget

系统 MUST 防止无证据的无限重试。

建议升级阶梯：

```text
L0  Resume same Run
 ↓
L1  New Run, same Agent Definition + model
 ↓
L2  New Run, same Agent Definition + stronger / alternate model
 ↓
L3  New Run, different Agent Definition
 ↓
L4  Human Assignment
```

升级必须有 Reason / Evidence。

---

## 7.5 禁止自动 Retry 的情况

至少包括：

- 不可逆外部副作用处于 UNKNOWN；
- Goal / Acceptance 业务歧义；
- Capability 缺失；
- Hard Constraint 冲突；
- 重复相同 Failure 且无新 Evidence；
- Policy 明确要求 Human Decision。

这类问题不应通过“换一个模型再试”掩盖。

---

# 第八章　Runtime Session 边界

## 8.1 Session 定义

> **Session 是 AgentRun 在 Praxis Runtime 中持续保存、恢复并审计推理—行动过程的运行时容器。**

Session 包含：

```text
Turn
Model interactions
Tool calls/results
Observations
Hypotheses
Runtime Plan
Capabilities
Context projections
Recovery state
Runtime Events
```

---

## 8.2 Session 不是 Workbench 的最高对象

Workbench 默认应展示：

```text
MES-2041
└─ Backend API
   ├─ Run #17 Failed
   └─ Run #18 Running
```

而不是：

```text
Chat 173
Chat 174
Session S301
```

Session 仅在 Runtime Inspector、Run Detail、Debug / Replay 等高级视图下展开。

---

## 8.3 Run 与 Session 基数

默认：

```text
1 AgentRun = 1 Main Session
```

产品模型 MAY 允许一个 Run 具有多个 Session（例如 child investigation）。

但：若某个 child execution 已经具有独立 Goal、Acceptance、责任、阻塞和持久成果，它 SHOULD 提升为新的 WorkItem / Assignment / AgentRun，而不是藏在一个巨型 Session 中。

---

# 第九章　Execution Environment

## 9.1 定义

> **Execution Environment 是 AgentRun 实际接触现实的受控执行边界。**

Coding 场景可能包含：

```text
Repository bindings
Git worktree(s)
Filesystem root
Environment variables
Tool set
Capabilities
Network policy
Runtime resources
Test environment
Temporary credentials
```

---

## 9.2 Environment 是暂态资源

Execution Environment 属于 Run 的生产条件，不属于 Work 的最终历史成果。

Run 结束后：

- Environment MAY 被清理；
- Artifact / RepoChange / Evidence / Session history MUST 继续存在；
- dirty / recovery-required environment MUST NOT 被自动破坏性清理。

---

## 9.3 多 Repository Run

一个 AgentRun MAY 绑定多个 Repository，但必须显式：

```text
Run R31
  repo mes-server → worktree A
  repo mes-web    → worktree B
  repo mes-pda    → worktree C
```

Agent MUST NOT 通过磁盘扫描获得未经 Assignment 授权的 Workspace 全局写权限。

---

# 第十章　Handoff Contract

## 10.1 正式定义

> **Handoff 是一个执行主体在责任边界发生变化时，把当前有效工作状态、已验证成果、未解决问题和下一责任，以结构化形式转移给后续执行主体的持久记录。**

Handoff 的核心是：

```text
State Transfer
not
Conversation Transfer
```

---

## 10.2 Handoff 的八个正式组成部分

### Intent

引用当前：

```text
Work / WorkItem
Goal
Scope
Constraints
Acceptance
```

Handoff 不拥有这些对象，只引用权威版本。

### Current Outcome

描述交接时已成立的现实结果，例如：

```text
API Contract rev3 accepted
backend endpoint implemented
unit verification passed
```

重点是“现实现在是什么”，不是“Agent 做过哪些动作”。

### Artifact References

引用：

```text
OpenAPI schema
SQL migration
test fixture
design decision
build artifact
```

Handoff 不复制大型 Artifact。

### Evidence / Verification

说明为什么相信 Outcome，例如：

```text
Verification V81
Target: backend API
Result: PASS
Evidence: test report, trace
```

### Open State

必须显式暴露：

```text
Open Challenges
Unknowns
Blockers
Risks
Unverified Assumptions
Pending external effects
```

Handoff MUST NOT 只传“已完成内容”。

### Change State

Coding Work 应引用：

```text
RepoChange / ChangeSet
Branch
Base revision
Commits
Working tree state
```

### Validity Basis

说明 Handoff 建立在哪些版本条件上：

```text
Graph Revision
Outcome / Artifact Revision
Acceptance Revision
Repository base
Verification environment
```

### Next Responsibility

明确接手者被期望完成什么，而不是“继续做”。

---

## 10.3 Fact 与 Hypothesis 必须分区

Handoff MUST 至少区分：

```text
Facts
Hypotheses
Unknowns
Risks
```

禁止把以下内容混成普通 notes：

```text
已验证事实
模型猜测
没有验证过的假设
外部未知
```

这是一条跨 Agent 防止“假设逐级变事实”的核心不变量。

---

## 10.4 System-owned 与 Agent-contributed 字段

建议：

| Handoff 信息 | 默认权威 |
|---|---|
| Goal / Acceptance ref | System |
| Graph revision | System |
| Commit / RepoChange | Git/System |
| Verification result | Verification/System |
| Artifact refs | System/Tool |
| Open durable Challenges | System |
| Hypothesis | Agent contribution |
| Risk explanation | Agent/System |
| Recommended next focus | Agent contribution |

Agent MUST NOT 主观覆盖系统记录的 Git、Verification、Artifact、Goal 等事实。

---

# 第十一章　Handoff 生命周期、有效性与版本

## 11.1 Handoff 类型

v0.1 只定义两类：

### Partial Handoff

当前 WorkItem 尚未整体完成，但一个稳定 Outcome 已满足下游 Dependency，下游可以开展独立有价值工作。

### Final Handoff

当前 Assignment / AgentRun 的责任阶段已经结束，状态正式交给后续执行主体或 Verification。

禁止为了“进度同步”频繁产生正式 Handoff。

---

## 11.2 Handoff 生命周期

建议：

```text
DRAFT
  ↓
PREPARED
  ↓
ACCEPTED
```

异常路径：

```text
REJECTED
SUPERSEDED
```

Validity 应与 Lifecycle 分开。

---

## 11.3 Prepared 不等于 Accepted

Handoff Prepared 只说明来源方已经形成交接清单。

目标 WorkItem 可能尚未 Ready、尚未 Assignment，或接手者认为资料不足。

接手方 Acceptance 表示：

> 当前已有足够有效的工作状态，可以承担新的责任。

---

## 11.4 Handoff 自动验收

低风险 Handoff 可以通过系统 + Agent 自动检查：

```text
Required refs exist
Dependency outcomes current
Required sections complete
No blocking unknown violates Assignment
Artifacts resolvable
```

高风险、跨业务责任、人类接管、关键 Acceptance 变化 MAY 要求 Human Acceptance。

---

## 11.5 Reject Handoff

Reject 必须结构化：

```text
Reason
Missing Requirement
Conflicting Evidence
Stale Reference
Required Resolution
```

例如：

```text
REJECTED
Reason: API Contract lacks error semantics required by AC-07
Required resolution: produce accepted error contract
```

Reject 应推动 Rework / Graph Revision / WorkItem，而不是成为纯沟通情绪。

---

## 11.6 Handoff Validity

Validity 建议：

```text
current
partially_stale
stale
```

失效来源包括：

- Graph Revision；
- Artifact / Outcome Revision；
- Verification invalidation；
- Repository revision conflict；
- Acceptance Revision。

---

## 11.7 Section-level Validity

Handoff SHOULD 支持部分失效：

```text
Intent: current
API Contract: stale
Test Fixture: current
Verification: partially stale
Open Risks: current
```

避免一个字段变化就把整个 Handoff 二值作废。

---

## 11.8 Handoff Revision

已被消费的 Handoff MUST NOT 原地覆盖历史。

应形成：

```text
H17 rev1
H17 rev2
```

从而可以回答：

```text
AgentRun R31 based on H17 rev1
```

Handoff Revision 与 Work Graph Revision 必须分开：交接内容变化不必然意味着工作结构变化。

---

## 11.9 Handoff Budget

Handoff 必须有大小预算。

原则：

- 大对象引用而非复制；
- 不复制完整 Diff / Log / Session；
- 只保留影响下游的当前 Hypothesis / Unknown / Risk；
- 默认小交接，允许 Downstream Pull 按需加载 Artifact / Evidence。

---

# 第十二章　Agent Communication：临时沟通与持久协作

## 12.1 默认不要以 Agent Chat 作为事实源

Agent 间 MAY 临时对话，但正式协作优先使用：

```text
Artifact
Evidence
Challenge
Handoff
WorkItem
Graph Revision
Verification
```

---

## 12.2 Ephemeral Communication

用于短期协调：

```text
测试环境地址是什么？
哪个文件包含这个 enum？
是否正在占用 simulator？
```

这类沟通不一定进入领域历史。

---

## 12.3 Durable Coordination

一旦消息改变 Work 的现实含义，例如：

```text
API schema changed
Acceptance changed
Compatibility decision approved
Verification invalidated
```

就必须晋升成正式 Durable Object / Event，而不能只留在 Chat。

---

## 12.4 Context Builder 与 Handoff

新 AgentRun 的 Context SHOULD 从：

```text
Assignment
Current WorkItem state
Relevant Handoffs
Workspace / Repository knowledge
Current Artifact / Evidence refs
```

构建。

MUST NOT 默认拼接所有上游 Agent Session。

---

## 12.5 Context Refresh

当上游 Handoff / Artifact / Graph Revision 发生影响时，运行中 Agent 应收到显式影响通知：

```text
Upstream state changed
API Contract rev3 → rev4
Impact: Review Required
```

然后执行明确 Context Refresh。

禁止静默更换重要 Goal / Dependency / Handoff Context，而让模型不知道条件已改变。

---

# 第十三章　并发执行模型

## 13.1 默认单 Implementation Writer

> **每个 WorkItem 默认最多一个 active implementation AgentRun。**

原因不是模型不能并行，而是：同一工作目标同时存在多个写入执行者会迅速造成责任、成果和 ChangeSet 归属模糊。

---

## 13.2 允许并行的 Run Role

默认可以考虑：

```text
Implementation + Investigation
Implementation + Read-only Review
Implementation + Verification (if target revision stable)
Independent Investigation Runs
```

但写权限和结果贡献必须隔离。

---

## 13.3 Write Domain

并发合法性 SHOULD 关注真实写域，而不是纯 Agent 数量。

例如：

```text
Run A write domain = mes-server worktree A
Run B write domain = mes-web worktree B
```

可以安全并行。

两个 Run 在同一共享目录写入则默认禁止。

---

## 13.4 Run Role 与写权限

默认：

| Role | 产品代码写权限 |
|---|---|
| implementation | 是，受 Scope/Capability 限制 |
| investigation | 临时/隔离，默认不进入最终 ChangeSet |
| review | 否 |
| verification | 否 |
| support | 按 Assignment 明确，默认否 |

Review / Verification MUST NOT 一边检查一边偷偷修改被检查对象。

---

# 第十四章　Git Worktree 与 Repository 隔离

## 14.1 Coding Run 的默认隔离原语

对于 Git Repository，Praxis SHOULD 以独立 Git Worktree 作为有写权限 AgentRun 的默认执行隔离方式。

```text
mes-server
├─ primary workspace
├─ worktree R101
└─ worktree R102
```

这样：

- 文件修改互不覆盖；
- branch / diff 独立；
- crash 后现场可恢复；
- Competitive Runs 可独立比较；
- Review 可基于确定 revision。

---

## 14.2 Worktree 不等于 Run

关系是：

```text
AgentRun uses Execution Environment
Execution Environment binds Git Worktree
```

Run 历史永久存在，而 Worktree 是可回收执行资源。

---

## 14.3 Dirty Worktree

Run crash / pause 后若 Worktree dirty，系统 MUST NOT 自动执行破坏性 reset / clean。

至少允许：

```text
Resume
Adopt
Checkpoint / Commit
Discard (explicitly authorized)
```

如果新 Run 接管旧 dirty Environment，应产生 Execution Handoff。

---

## 14.4 Merge Conflict

跨 WorkItem / Run 的 RepoChange 汇合出现 Git 冲突时，冲突 SHOULD 成为正式 Work Fact，并可创建 Conflict Resolution WorkItem。

禁止 Scheduler 在后台无审计地“自动修冲突”并把结果视为原 WorkItem 已验证成果。

---

# 第十五章　Competitive / Exploratory Runs

## 15.1 Competitive Execution

> **多个隔离 AgentRun 基于相同 WorkItem Goal、Acceptance 和 Base Revision 独立产生候选 Outcome，再由 Verification / Comparison 选择采用结果。**

必须显式启用。

---

## 15.2 共同起点

Competitive Runs MUST 冻结：

```text
WorkItem revision
Goal / Acceptance revision
Graph revision
Repository base revision
Input Artifact revision
```

否则不能视为可比较的独立尝试。

---

## 15.3 Candidate Outcome

多个候选结果 MUST NOT 自动混合。

流程：

```text
Candidate A
Candidate B
   ↓
Verification / Comparison
   ↓
Selected Candidate
```

未选候选保留历史，可用于模型评估和后续研究。

---

## 15.4 Exploratory Run

探索性 Run 可以调查不同方案、产生 Reproducer / Prototype / Proposal，但默认不直接贡献正式生产 ChangeSet。

若探索成果被采用，应通过显式 Promotion / Implementation Assignment 进入正式产出链。

---

# 第十六章　Review 与 Verification 隔离

## 16.1 Reviewer 是普通 Agent Definition

Praxis MUST NOT 创造拥有特殊真理主权的 Judge Agent。

Reviewer 仍是：

```text
Agent Definition
+ Verification / Review Assignment
+ AgentRun
```

它的权力来源于 Assignment / Acceptance Policy，而不是角色名称。

---

## 16.2 Independent Review

Tier-0 / 高风险 Review SHOULD 支持 independent context：

Reviewer 首先看到：

```text
Goal
Acceptance
ChangeSet
Raw Evidence
Tests
```

而不是先阅读 Implementation Agent 的全部主观解释。

需要时再查看 Implementation Handoff。

---

## 16.3 Review 默认只读

Reviewer SHOULD：

```text
read
run tests
inspect diff
raise Challenge
produce Verification
```

Reviewer 如果要直接修实现，应建立新的 Fix Assignment / implementation Run，明确责任切换。

---

## 16.4 Verification 默认不修改 Target

Verification Run 的责任是产生 Evidence / Verification Result。

如果发现缺陷：

```text
Verification FAIL
→ Evidence
→ Challenge / Needs Rework
→ Implementation Assignment
```

而不是直接修改代码使自己的测试通过。

---

# 第十七章　RepoChange / ChangeSet 贡献模型

## 17.1 RepoChange

`RepoChange` 表示一个 Work 在单个 Repository 上当前形成的逻辑变更。

它可以包含：

```text
Repository
Base revision
Branch / worktree refs
Modified files
Commits
Diff
Contributor Runs
Current state
```

---

## 17.2 AgentRun 是 Contributor，不拥有 RepoChange

多个 Run 可能连续贡献同一个 RepoChange：

```text
Run R17  initial implementation
Run R21  review fix
Run R26  integration conflict fix
        ↓
mes-server RepoChange
```

因此 Run 结束不会使 RepoChange 消失。

---

## 17.3 ChangeSet 属于 Work

> **ChangeSet 是一个 Work 为达到当前交付目标形成的跨一个或多个 Repository 的逻辑变更集合。**

```text
ChangeSet MES-2041 rev5
  backend @ abc123
  web     @ def455
  pda     @ 773bc1
```

ChangeSet MUST NOT 属于某一个 Agent。

---

## 17.4 ChangeSet Revision

任何正式 Verification / Delivery MUST 绑定明确 ChangeSet Revision。

如果后续代码变化：

```text
ChangeSet rev5 → rev6
```

旧 Verification 不能自动证明 rev6，必须根据 Verification Scope / Policy 重新评估。

---

## 17.5 Integration Environment

Integration SHOULD 从某个明确 ChangeSet Revision 构建组合环境：

```text
backend @ A
web @ B
pda @ C
```

而不是直接使用各 Implementation Agent 的临时 dirty worktree。

这样验证对象才是真实候选交付组合。

---

# 第十八章　Resource / Capability / Assignment Lease

## 18.1 Execution Resource

AgentRun 可能需要：

```text
Git worktree
execution slot
test DB
simulator
device
CI environment
credential
network access
```

资源可具有：

```text
exclusive
shared-read
shared-write
capacity=N
```

---

## 18.2 Resource Lease

临时资源占用 SHOULD 有 Lease / TTL / 回收机制，避免 Run crash 后资源永久“被占用”。

---

## 18.3 Assignment Lease

自动调度产生的 Assignment MAY 有有效期。

若长时间未启动或 Graph / Resource 状态变化，可过期并重新 Scheduling。

---

## 18.4 Capability 与 Resource 分离

```text
Resource available
≠
Executor allowed to use resource
```

例如 Production DB 即使在线，也必须经过 Runtime Capability、Policy、Approval。

生产资源不能仅因 Scheduler 发现它“空闲”就自动交给 Agent。

---

## 18.5 统一 Lease Primitive 的方向

未来系统实现 SHOULD 尽可能复用统一 Lease Primitive 支撑：

```text
Capability Lease
Assignment Lease
Resource Lease
```

但产品语义仍属于各自对象。

---

# 第十九章　Human Assignment、注意力与治理升级

## 19.1 Human Assignment 是正式工作

以下情形 SHOULD 形成 Human Assignment / Decision WorkItem，而不是简单让 Agent 发一句“请用户确认”：

```text
Goal / Acceptance ambiguity
Hard Constraint conflict
Business Decision
Unknown irreversible effect
High-impact Graph Revision
Repeated Agent failure
Production approval
```

---

## 19.2 Work Owner 与 Executor 分离

WorkItem MAY 同时具有：

```text
Owner: Human backend lead
Executor: GPT Agent
```

Owner 对 Work 结果负责；Executor 对当前执行负责。

自动 Agent 执行不会转移业务/组织责任。

---

## 19.3 Human Attention 是有限生产资源

Praxis Scheduler SHOULD 识别：

```text
pending approvals
pending reviews
pending decisions
same owner queue
```

系统 MUST NOT 为追求 Agent 利用率同时制造大量等待同一人的 Review / Approval。

---

## 19.4 My Attention

后续 GUI SHOULD 重点呈现真正需要人的事项：

```text
Human Assignment
Approval Required
Blocking Challenge
Unknown external effect
Handoff requiring human acceptance
High-impact Graph Revision
Human Verification
```

而不是把所有 Agent progress notification 都推给用户。

---

# 第二十章　MES 多 Agent 参考场景

## 20.1 Work

```text
MES-2041 首检状态校验
```

涉及：

```text
mes-server      Java backend
mes-web         Vben5
mes-pda         UniApp
mes-machine     UniApp
```

Work Graph：

```text
Analysis
   ↓
Backend Contract
   ├─────────────┬─────────────┐
   ↓             ↓             ↓
Backend Impl    Web            PDA
   │             │             │
   └─────────────┴─────┬───────┘
                       ↓
                  Integration
                       ↓
                    Delivery
```

---

## 20.2 Backend Assignment

```text
WorkItem: Backend Impl
Agent: Backend Developer
Run Role: implementation
Model: primary coding model
Environment: mes-server worktree R101
```

Backend AgentRun 在实现尚未完成时先产生：

```text
API Contract rev3 Accepted
```

Dependency 满足后 Web / PDA Ready。

系统形成 Partial Handoff：

```text
Intent: MES-2041 / clients
Outcome: API Contract rev3
Artifacts: OpenAPI rev3, fixture
Unknown: offline PDA not verified
Validity Basis: Graph rev12
```

---

## 20.3 Web / PDA 并行

Scheduler 创建两个独立 Assignment：

```text
Web AgentRun
→ mes-web worktree R102

PDA AgentRun
→ mes-pda worktree R103
```

两个 Run 不共享工作目录。

PDA Run 发现旧客户端兼容问题，提出 Blocking Challenge，而不是直接修改 Backend Contract。

Work Graph 创建 Human Decision WorkItem：

```text
是否继续兼容旧 PDA？
```

用户选择“兼容”。

Graph Revision 添加 Backend Compatibility WorkItem。

---

## 20.4 Graph / Handoff 变化

Backend Contract rev3 → rev4。

Web / PDA 已消费 Handoff rev1（基于 rev3）。

系统计算 Impact：

```text
Web: review_required
PDA: potentially_invalidating
```

运行中的 AgentRun 收到显式 Context Refresh，而不是在下一次模型请求中偷偷换协议。

---

## 20.5 Integration

各 Implementation WorkItem 产生 RepoChange：

```text
backend → A
web     → B
pda     → C
```

Work 当前 ChangeSet：

```text
MES-2041 ChangeSet rev7
  backend @ A
  web @ B
  pda @ C
```

Integration Verification 基于 rev7 构建独立组合环境。

Integration Agent 默认只读测试。

发现 PDA enum mapping 错误：

```text
Verification FAIL
→ Evidence
→ Challenge PDA
→ PDA Needs Rework
```

Backend / Web Acceptance 不被机械回滚。

---

## 20.6 Rework 与新 Run

PDA 原 AgentRun 已结束。

创建新 PDA Fix Assignment：

```text
Run R140
Role: implementation
Input:
  WorkItem state
  failure evidence
  current Handoff
  ChangeSet rev7
```

修复后形成 rev8，再次 Integration Verification。

全部 Work-level Acceptance 满足后进入 Delivery。

整个过程没有依赖多 Agent 互相复制 Session；协作主要通过 Work Graph、Artifact、Evidence、Handoff、Challenge、ChangeSet 和 Verification 完成。

---

# 第二十一章　对象所有权矩阵

| 对象 | 主要所属 | 能否跨 Run 持久 | 默认权威来源 |
|---|---|---:|---|
| Work Goal | Work | 是 | Work / Human governance |
| WorkItem Goal | WorkItem | 是 | Work Graph |
| Agent Definition | Workspace | 是 | Workspace configuration |
| Scheduling decision | Workspace / Work | 是 | Scheduler / Governance |
| Assignment | WorkItem | 是 | Governance / Scheduler |
| AgentRun | WorkItem / Assignment | 是 | Execution history |
| Session | AgentRun / Runtime | 是 | Runtime Event Store |
| Execution Environment | AgentRun | 暂态 | Runtime / resource manager |
| Artifact | Work / WorkItem | 是 | Artifact source |
| Evidence role | Claim / Verification | 是 | Verification / Evidence refs |
| Handoff | WorkItem execution flow | 是 | Structured transfer record |
| RepoChange | Work / ChangeSet | 是 | Git / Workbench |
| ChangeSet | Work | 是 | Workbench current delivery set |
| Verification | Target object | 是 | Verifier + Evidence |
| Delivery | Work | 是 | Delivery integration |
| Cost metrics | AgentRun | 是 | Runtime/provider telemetry |

---

# 第二十二章　Agent Work 产品不变量

以下规则作为 v0.1 正式产品不变量冻结。

1. **WorkItem 是稳定责任单位；AgentRun 只是一次执行。**
2. **Assignment 与 Execution 必须分离。**
3. **Agent Definition 表示能力，而不是永久拥有 Work 的虚拟员工人格。**
4. **长期项目知识优先属于 Workspace / Work，不属于 Agent 私有记忆。**
5. **Agent Definition 与 Model 分离；实际模型在 Run 启动时冻结并记录。**
6. **Ready ≠ Scheduled ≠ Assigned ≠ Executing。**
7. **Scheduler 优化端到端 Work Flow，而不是 Agent 利用率。**
8. **模型选择遵循 Minimum Sufficient Model，并受 Risk Policy 调整。**
9. **技术中断 Resume 同 Run；执行身份/战略断裂创建新 Run。**
10. **AgentRun completed ≠ WorkItem accepted。**
11. **Replay ≠ Rerun；Rerun 永远是新 AgentRun。**
12. **Retry 必须有 Budget；无新 Evidence 的重复失败必须升级或暂停。**
13. **UNKNOWN irreversible effect 禁止自动重试。**
14. **Session 是 Runtime 历史，不是产品最高工作对象。**
15. **具备独立 Goal / Acceptance 的 Subagent 工作应提升为 WorkItem。**
16. **Multi-Agent 来源于 Work 分解或明确执行角色，不来源于意见数量。**
17. **Handoff 传递工作状态，不传无限 Conversation。**
18. **Handoff 必须区分 Fact / Hypothesis / Unknown / Risk。**
19. **Handoff 引用权威 Artifact / Evidence / Git / Verification，而不是复制它们。**
20. **Handoff 必须具有 Revision 与 Validity，并允许部分失效。**
21. **Handoff Prepared ≠ Accepted；拒绝必须结构化并推动工作。**
22. **Context Refresh 必须显式，不能静默改变执行条件。**
23. **Agent Chat 中影响 Work 的结论必须晋升为 Durable Coordination Object。**
24. **默认每个 WorkItem 只有一个 active implementation Run。**
25. **Review / Verification 默认只读，不直接修被检查实现。**
26. **有写权限 Coding Run 优先使用隔离 Git Worktree。**
27. **Run crash 不得自动清理 dirty Execution Environment。**
28. **跨 Run 接管未完成执行环境必须有 Handoff。**
29. **Competitive Execution 必须显式启用并使用共同 Base / Goal / Acceptance。**
30. **ChangeSet 属于 Work，AgentRun 只是贡献者。**
31. **Verification / Delivery 必须绑定明确 ChangeSet Revision。**
32. **Integration 应验证组合 ChangeSet，而不是某个 Agent 的临时工作目录。**
33. **Resource availability 与使用权限分离。**
34. **临时 Assignment / Capability / Resource 必须可回收。**
35. **Work Owner 与 Executor 分离。**
36. **Human Attention 是有限生产资源，Automation 不得制造无限人工审核洪峰。**
37. **Agent 成本、Token、Tool Calls 是观测指标，不拥有 Goal 主权。**
38. **实现 Agent、Reviewer、Verifier 都不能拥有最终 Work-level Acceptance 主权。**

---

# 第二十三章　v0.1 明确不做

本规范不决定以下实现问题：

- 最终 Scheduler 算法与优先级打分公式；
- Agent Definition 配置文件格式；
- Model Router / Provider 具体实现；
- Assignment / Handoff 数据库 Schema；
- Handoff JSON Schema / token budget 数值；
- Git Worktree 物理目录结构；
- Git branch naming；
- 自动 merge / rebase 策略；
- Semantic merge conflict predictor；
- 分布式锁 / Kubernetes executor；
- Remote Agent infrastructure；
- Team RBAC；
- Agent-to-Agent 即时通讯协议；
- Agent 评价总分体系；
- 多 Agent 强化学习式 Scheduler；
- Production 自动部署策略。

以上内容必须由后续产品/系统专题基于真实 Pilot 需求决定。

---

# 第二十四章　后续专题待决问题

## 24.1 Multi-Repository / Git / ChangeSet

下一份专题应详细解决：

```text
Workspace 如何登记 N 个 Repo？
Repo identity / remote / branch policy 如何管理？
Git Worktree 的创建、回收、恢复怎么工作？
RepoChange 和 commit / branch / PR 有什么正式关系？
ChangeSet Revision 如何生成？
多 Repo Integration Environment 如何构建？
跨 Repo Delivery 如何追踪？
```

---

## 24.2 Automation

需要另行规范：

```text
Trigger / Condition / Action
WorkItemReady 自动 Assignment
HandoffChanged Impact handling
Verification Failed rework automation
Lease expiration
loop guard / causation / deduplication
```

---

## 24.3 Workbench UX

需要确定：

```text
Work Tree
Agent Timeline
Handoff Timeline
My Attention
Agents view
Git / ChangeSet view
Run / Runtime inspector
```

---

## 24.4 Team / Remote execution

需要真实单机 Workbench Pilot 后再讨论：

```text
remote agents
shared workspace
team ownership
RBAC
remote execution pool
server-side scheduler
```

---

# 第二十五章　术语表

| 术语 | 本规范定义 |
|---|---|
| Executor | 能承担 Assignment 的执行主体，包括 Agent、Human、Automation 等 |
| Agent Definition | 可复用执行能力配置，而非永久虚拟人格 |
| Scheduling | 从 Ready WorkItem 中决定当前优先执行哪些工作 |
| Assignment | 把一个 WorkItem 的执行责任和范围授予 Executor |
| AgentRun | Agent 对一个 Assignment 的一次真实执行尝试 |
| Run Role | implementation / investigation / review / verification / support 等执行职责 |
| Runtime Session | AgentRun 在 Praxis Runtime 中的持久推理—行动历史 |
| Execution Environment | AgentRun 接触文件、Repo、工具、资源的隔离运行边界 |
| Handoff | 跨责任边界的结构化工作状态交接记录 |
| Partial Handoff | WorkItem 未整体完成，但稳定 Outcome 已可供下游独立工作 |
| Final Handoff | 当前责任阶段完成后的正式交接 |
| Handoff Validity | Handoff 基于的版本事实是否仍然有效 |
| Competitive Run | 同一 WorkItem 上的多个隔离候选执行 |
| RepoChange | Work 在单个 Repository 上形成的逻辑变化 |
| ChangeSet | Work 跨一个或多个 Repository 的逻辑交付变更集合 |
| Integration Environment | 基于明确 ChangeSet Revision 构建的组合验证环境 |
| Resource Lease | AgentRun 对有限执行资源的可回收临时占用 |
| Human Assignment | 需要由人完成的正式 Work responsibility，而非普通通知 |

---

# 结语

Praxis 的 Multi-Agent 设计不应该从“让几个模型互相说话”开始，而应该从真实生产责任开始：

```text
WorkItem
→ Assignment
→ Executor
→ AgentRun
→ Runtime Session
→ Artifact / Evidence / RepoChange
→ Handoff
→ Verification
→ ChangeSet
→ Delivery
```

真正可靠的跨 Agent 协作，不依赖一个越来越长的共享 Conversation，而依赖：

- 稳定的 Work Goal；
- 明确的 Assignment；
- 可恢复的 AgentRun / Session；
- 隔离的 Execution Environment；
- 权威 Artifact / Evidence；
- 可版本化 Handoff；
- 独立 Verification；
- Work-owned ChangeSet。

因此本规范的核心结论是：

> **Praxis 中的 Agent 是可替换的执行能力，Work 才是持久对象；Handoff 传递工作状态，ChangeSet 汇聚现实成果，Verification 决定这些成果是否值得被接受。**
