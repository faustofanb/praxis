# Praxis Work Graph 与工作生命周期详细规范

## v0.1 产品基线

版本：0.1  
状态：Product Baseline / Normative  
日期：2026-08-28

> 本规范建立在《Praxis 产品白皮书》与《Praxis Workbench 产品领域模型与核心概念规范 v0.1》之上，专门冻结 Work Lifecycle、Readiness、Dependency、状态传播、Graph Revision、Version 与 Audit 的产品语义。本规范不定义数据库 Schema、Graph 存储技术、GUI 框架、Automation DSL 或具体 Scheduler 实现。

---

# 1. 文档目的

Praxis Workbench 的核心产品对象是 Work，复杂 Work 通过 Work Graph（工作图）组织多个 WorkItem、执行主体、依赖、验证和交付。

本规范回答五类问题：

1. 一个 Work / WorkItem 当前究竟处于什么状态；
2. 一个 WorkItem 在什么条件下可以开始、暂停、重新执行或接受；
3. WorkItem 之间有哪些正式关系，这些关系怎样影响 Readiness 与 Validity；
4. 上游事实改变后，下游状态怎样传播，而不退化成机械状态复制；
5. Work Graph 在实践中发生变化时，怎样版本化、审计、批准并保护历史真实性。

本规范的目标不是把所有工作预定义成固定 Workflow（工作流），而是建立一个能够随着 Evidence（证据）持续演化的可执行工作模型。

---

# 2. 规范用语

本文使用：

- MUST / 必须：产品领域语义不得违反；
- MUST NOT / 禁止：出现即属于模型错误；
- SHOULD / 应当：默认采用，偏离必须有明确理由；
- MAY / 可以：允许实现选择。

本文中的“状态”若未特别说明，指领域语义或 Projection（投影），不等价于某个数据库字段。

---

# 3. 总体原则

## 3.1 Goal 高于 Graph

Work Graph 是实现 Work Goal 的当前结构化计划。

```text
Work Goal / Acceptance
        ↓
   Work Graph
        ↓
    WorkItem
        ↓
    AgentRun
```

Work Graph 完整执行完毕 MUST NOT 自动等价于 Work Acceptance 已满足。

如果 Graph 与新的现实 Evidence 冲突，应修改 Graph，而不是保护旧 Graph。

---

## 3.2 Graph over Tree

领域层的工作结构是有类型的 Graph。

GUI 左侧的 Work Tree 是基于 Decomposition（分解/归属关系）的层级 Projection。

```text
Domain:
Typed Work Graph

Human navigation:
Work Tree Projection
```

产品 MUST NOT 为了树形 UI 而强迫所有真实工作关系只有单父节点或严格串行。

---

## 3.3 State is Projected

Praxis 应尽可能从真实执行事实推导工作状态，而不是要求用户维护一套平行状态。

```text
Execution facts
Dependencies
Verifications
Blockers
Governance
        ↓
    Projection
        ↓
Ready / Waiting / Executing / Verifying / ...
```

“用户把卡片拖到 In Progress”不应成为判断真实执行状态的唯一事实。

---

## 3.4 History is append-oriented

过去发生过的执行、Acceptance、Verification、Graph 结构和交付事实 MUST NOT 通过覆盖当前字段而被抹除。

例如：

```text
Acceptance #1 PASS
↓
New Evidence E44
↓
WorkItemReopened
↓
Acceptance #2 ...
```

而不是把历史改写成“这个节点从来没有通过过”。

---

# 4. Work Lifecycle：状态不是一个枚举

Praxis MUST NOT 用一个不断膨胀的 `status` 枚举承载所有业务、执行、验证和交付含义。

建议从多个正交维度理解 Work / WorkItem。

## 4.1 Lifecycle State

回答：这个 Work 在业务/治理层是否仍然存在并被要求继续处理？

建议语义：

- `captured`：已经被系统捕获，但未必达到可执行条件；
- `active`：当前仍要求推进；
- `cancelled`：治理主体明确决定不再推进；
- `closed`：当前组织认为该 Work 无需继续行动。

`closed` 与 `delivered` 不等价；已 Delivery 的 Work 可以继续处于 active 以观察、签收或完成后续治理。

---

## 4.2 Readiness State

回答：当前客观和治理条件是否允许开始/继续这个 WorkItem？

主要 Projection：

- `ready`；
- `waiting`；
- `blocked`；
- `unknown`（必要条件状态无法确定）。

Readiness 应由 Readiness Policy 计算，而不是手工维护。

---

## 4.3 Execution State

回答：当前是否存在实际执行过程？

建议：

- `idle`；
- `executing`；
- `paused`。

`AgentRun failed` 不等于 `WorkItem failed`。一次执行失败后 WorkItem 可以重新分配、重新规划或由人工接管。

---

## 4.4 Acceptance State

回答：当前成果是否已经由所需 Verification 支持并满足 Acceptance Policy？

建议：

- `unverified`；
- `verifying`；
- `accepted`；
- `needs_rework`。

`Execution completed` MUST NOT 自动转成 `accepted`。

---

## 4.5 Delivery State

回答：已经 Accepted 的成果是否真正到达目标交付位置？

例如：

- `not_started`；
- `delivering`；
- `delivered`；
- `delivery_failed`。

Delivery failure 是交付尝试失败，不等于 Work Implementation 失败。

---

## 4.6 Validity / Impact Projection

回答：过去已经 Accepted/Verified 的结果在当前条件下是否仍然有效？

建议：

- `current`；
- `review_required`；
- `reverification_required`；
- `rework_required`；
- `unknown`。

Validity 通常从 Outcome Revision、Coordination、Verification Scope 等事实推导，不要求成为人工状态。

---

# 5. Work 的主显示状态

GUI 可以把多个维度压缩成人可理解的主状态，但领域层必须保留精确含义。

示例优先级（非实现算法）：

```text
if cancelled
  → Cancelled
else if work-level blocker
  → Blocked
else if active execution exists
  → Executing
else if required verification active
  → Verifying
else if accepted and delivery active
  → Delivering
else if accepted
  → Accepted
else if waiting dependencies
  → Waiting
else if ready
  → Ready
else
  → Captured
```

父 Work 应同时展示 Health Summary，例如：

```text
MES-2041
Executing
3 / 5 required items accepted
2 agents running
1 blocker
1 item requires reverification
```

而不是只显示粗糙的 `In Progress`。

---

# 6. Approved、Ready、Scheduled、Executing 必须分离

这四个概念回答不同问题：

| 概念 | 问题 |
|---|---|
| Approved | 业务/治理是否允许做？ |
| Ready | 所有开始条件是否已经满足？ |
| Scheduled | 系统是否决定现在分配执行资源？ |
| Executing | 是否真的存在执行过程？ |

因此：

```text
Approved ≠ Ready
Ready ≠ Scheduled
Scheduled ≠ Assigned
Assigned ≠ Executing
```

Automation 可以配置 `on Ready → schedule`，但这是一种 Policy，不是领域必然。

---

# 7. Waiting、Blocked、Paused 的正式区别

## 7.1 Waiting

正常等待已知前置条件。

```text
Frontend waits for Backend API Contract
```

这不是异常。

## 7.2 Blocked

按照当前计划原本应该能够继续，但出现了必须解决的现实阻碍。

例如：

- Acceptance Criteria 矛盾；
- 必需权限缺失；
- 构建环境损坏；
- Blocking Challenge 未解决。

## 7.3 Paused

执行主体或治理策略选择暂时停止，但不存在“想继续也无法继续”的客观阻碍。

例如：

- 用户主动暂停 Agent；
- 成本预算达到上限；
- 维护窗口结束。

这三者 MUST NOT 混成一个 `blocked` 状态。

---

# 8. Work Template 与生命周期策略

不同 Work Type 可以通过 Work Template（工作模板）提供不同的初始结构和 Policy，而不是创造不同硬编码状态机。

## 8.1 Feature 示例

```text
Capture
→ Approve
→ Execute
→ Verify
→ Deliver
→ Close
```

## 8.2 Incident 示例

```text
Capture
→ Stabilize
→ Investigate
→ Mitigate
→ Fix
→ Verify
→ Postmortem
→ Close
```

Template 应定义：

1. 初始 Work Graph；
2. Readiness / Acceptance / Delivery 默认 Policy；
3. Automation 建议。

Template 只负责生成初始结构。Work 创建后其 Graph 独立演化，Template 更新 MUST NOT 自动重写已有 Work。

---

# 9. Work Graph 的节点

v0.1 的主要可执行节点是 WorkItem。

WorkItem 必须满足至少一个产品意义：

- 可以被独立执行；
- 可以被独立验证；
- 可以被独立阻塞/暂停；
- 可以被独立交接；
- 可以被重新分配；
- 对用户理解工作结构具有独立价值。

Agent 内部的微观步骤，例如“读文件”“跑测试”“修改 FooService.java 第 142 行”，通常属于 Runtime Plan / Action，SHOULD NOT 提升为 WorkItem。

---

# 10. Decomposition：归属关系

Decomposition 回答：这个 WorkItem 属于哪个更大的工作结构？

```text
Feature
├─ Backend
├─ Web
├─ PDA
└─ Integration
```

Decomposition MUST NOT 自动意味着执行依赖。

```text
Decomposition ≠ Dependency
```

v0.1 建议：

- 一个 WorkItem 有一个 owning Work；
- 同一 Work 内 Decomposition 尽量保持单结构父节点；
- 跨节点复用通过 Dependency、Coordination、Artifact Reference 等表达。

因此 Decomposition 提供天然的 Work Tree，而其他关系形成真正 Work Graph。

---

# 11. WorkItem Requiredness

父结构对 WorkItem 的要求分为：

## 11.1 Required

始终参与父层 Acceptance / Completion 条件。

## 11.2 Optional

未完成也不阻止父层 Acceptance。

## 11.3 Conditional

当某个条件成立后转为 Required。

例如：

```text
Legacy Compatibility
required if legacy PDA population exists
```

Conditional 一旦触发，不应再按 Optional 处理。

---

# 12. Dependency：前置条件关系

Dependency 回答：Target WorkItem 的某个开始/接受条件依赖 Source 产生什么 Outcome？

领域上应理解为：

```text
Source Fact / Outcome
        ↓
   Condition
        ↓
Target Readiness / Acceptance
```

依赖的核心不是“箭头”，而是可满足条件。

---

# 13. Dependency 优先绑定 Outcome，而非节点粗状态

错误模型：

```text
Backend Done
→ Web Ready
```

更合理：

```text
Backend.APIContractAccepted(rev3)
→ Web Ready
```

原因：Web 可以在 Backend 完整实现之前开始，从而减少伪串行。

Dependency MAY 引用：

- WorkItem Outcome；
- Artifact；
- Verification；
- Human Decision；
- External Condition；
- Work-level fact。

v0.1 不要求把 Outcome 做成独立一级领域对象。

---

# 14. Start Condition 与 Acceptance Condition

同一 WorkItem 的开始条件和最终接受条件必须分开。

例如：

```text
Web Start:
API Contract Accepted

Web Acceptance:
Backend real implementation available
AND integration verification PASS
```

因此：

- Readiness Policy 决定“能否开始”；
- Acceptance Policy 决定“能否被接受”。

两者 MUST NOT 合并成“上游 Done”。

---

# 15. Required 与 Advisory Dependency

## 15.1 Required Dependency

不满足时 Target 不可 Ready / Accepted（取决于该条件用途）。

## 15.2 Advisory Dependency

不满足不阻止执行，但向执行者显示 Risk / Warning。

例如：

```text
Required:
API Contract Accepted

Advisory:
Backend implementation > 80% completed
```

不要用含义模糊的单一 `soft=true` 替代二者。

---

# 16. Dependency Condition 的三值逻辑

Condition evaluation 至少支持：

```text
SATISFIED
UNSATISFIED
UNKNOWN
```

对 Required Condition：

```text
UNKNOWN
→ not Ready
```

但 UI 应说明“等待确认/未知”，而不是伪装成明确失败。

这与 Praxis Runtime 的 `INDETERMINATE / UNKNOWN` 原则保持一致。

---

# 17. Condition Group

v0.1 Readiness / Acceptance 条件组合 SHOULD 只支持：

- `ALL OF`；
- `ANY OF`。

例如：

```text
ALL:
  - Requirement Approved
  - Backend Contract Accepted
  - ANY:
      - Test Env A Available
      - Test Env B Available
```

v0.1 MUST NOT 提前引入通用布尔 DSL。真实产品需求证明不足后再扩展。

---

# 18. Readiness Policy

WorkItem 的 Ready 至少依赖以下类别：

```text
Ready(W)
=
GovernanceAllows(W)
AND DependenciesSatisfied(W)
AND RequiredInputsAvailable(W)
AND ResourcesAvailable(W)
AND NOT BlockingConditionExists(W)
AND NOT Paused(W)
```

Readiness 必须可解释。

GUI/Agent 应能够获得：

```text
Why not ready?
✓ Requirement approved
✓ Repository available
○ Backend API Contract Accepted
? Test environment health unknown
```

Readiness MUST NOT 是不可解释的 boolean。

---

# 19. Scheduling Policy 独立于 Readiness

如果十个 WorkItem 都 Ready，而只有两个 Agent Slot：谁先运行属于 Scheduling Policy。

可考虑：

- Priority；
- Critical path；
- Deadline；
- Agent availability；
- Cost；
- Resource contention；
- User preference。

因此：

```text
WorkItem
↓
Readiness
↓
Scheduling
↓
Assignment
↓
AgentRun
```

Scheduler 是后续专题，本规范只冻结边界。

---

# 20. Dependency 子图必须无环

Required execution dependency：

```text
A requires B
B requires A
```

会造成执行死锁。

因此：

> Required Start Dependency subgraph MUST be acyclic。

但整个 Work Graph 不要求是 DAG，因为：

- Coordination 可以双向；
- Verification 可以多向；
- Decomposition 与其他 Relation 可以组合。

所以 Praxis 的模型是 typed graph（有类型图），不是简单 DAG。

---

# 21. Coordination：变化传播关系

Dependency 主要回答：

> “什么时候可以开始？”

Coordination 主要回答：

> “共享契约/Outcome 变化以后，谁需要重新评估？”

典型共享对象：

- API Contract；
- Database Schema；
- Protocol；
- Shared Type；
- Business Rule；
- Generated Schema。

Coordination SHOULD NOT 因任意 Git diff 触发，而应基于共享 Outcome 的语义变化。

---

# 22. Outcome Revision 与 Dependency Basis

一个 Dependency 被满足时，应能够追溯它所依据的 Outcome Revision。

例如：

```text
Web dependency satisfied by:
API Contract revision 3
```

当 rev4 发布：

```text
Current contract = rev4
Web basis = rev3
```

此时系统可以产生：

```text
re-evaluation / impact review / reverification required
```

而不是继续把 `dependency_satisfied=true` 当永久事实。

---

# 23. Accepted 不代表永远有效

Verification 必须保存其适用条件，例如：

```text
Verified against:
API Contract rev3
Environment X
Build Y
```

当条件发生变化：

```text
Verification #12 historically PASS
Current validity = reverification_required
```

系统 MUST NOT 改写历史为“以前没有 PASS”。

这使 Praxis 能表达：

> 某个结论当时成立，但当前条件已经改变。

---

# 24. 状态传播原则：传播 Impact，不复制状态

错误：

```text
Backend Failed
→ Web Failed
→ Integration Failed
```

正确：

```text
Source Fact Changed
↓
Evaluate typed relations
↓
Calculate affected conditions / validity
↓
Recompute affected projections
```

因此，上游状态改变不会直接复制到下游。

---

# 25. 四类传播

## 25.1 Readiness Propagation

影响下游能不能开始。

来源：Dependency / Governance / Resource / Blocker。

## 25.2 Validity Propagation

影响过去成果现在是否仍有效。

来源：Outcome Revision / Coordination / Acceptance Revision / Environment Revision。

## 25.3 Blocking Propagation

决定一个 Blocker 的影响范围。

## 25.4 Completion Propagation

决定子工作成果怎样成为父 Work Acceptance 的 Preconditions / Evidence。

这四类 MUST NOT 被实现成一个模糊的“status propagation”。

---

# 26. Multiple Dependency 语义

默认 Required Dependencies 是 `ALL OF`。

允许显式 `ANY OF`。

例如：

```text
Integration requires:
ALL:
  Backend Accepted
  Web Accepted
  PDA Accepted
```

或：

```text
Test execution requires:
ANY:
  TestEnvA Available
  TestEnvB Available
```

---

# 27. Cancelled、Superseded 与 Dependency

## 27.1 Cancelled

Cancelled WorkItem 默认 不能满足 Dependency。

## 27.2 Superseded

Superseded 表示旧计划被新工作替代，不等于失败。

原 Dependency MUST NOT 静默迁移到替代 WorkItem。

系统可提出 Dependency Rebind Proposal，但必须确认新 Outcome 是否与原 Required Outcome 兼容。

```text
Backend V1 superseded by Backend V2

Old:
Web requires V1.API

Proposal:
rebind → V2.API
```

语义发生变化时必须重新评估。

---

# 28. Reopen 的传播

`WorkItemReopened` 不自动使所有下游失效。

如果下游依赖：

```text
Backend.APIContract rev3
```

即使 Backend WorkItem 因其他原因 Reopened，只要 rev3 Outcome 仍有效，下游 Dependency 可继续 SATISFIED。

只有：

- Outcome withdrawn；
- Outcome superseded；
- Outcome revision changed 并影响适用性；

才产生下游 Impact。

---

# 29. Blocker Scope

Blocker 必须有影响范围，建议：

- `local`：只影响当前 WorkItem；
- `downstream`：通过 Dependency 影响下游；
- `work`：阻断 Work-level Goal / Acceptance；
- `delivery`：开发可继续，但阻止 Delivery。

父 Work MUST NOT 因任意子节点 Blocked 就自动显示整体 Blocked。

例如：

```text
MES-2041
Executing · 1 blocker
```

只有 Work-level 或 critical-path 的 Blocker 真正阻止整体推进时，才显示主状态 Blocked。

---

# 30. Challenge 与传播

Challenge 本身不自动等于 Blocked。

Challenge 可以：

- non-blocking；
- blocking（由 Policy/Scope 决定）。

当 Challenge 指向一个共享 Outcome 时，下游可能进入：

- `review_required`；
- `reverification_required`；
- `rework_required`；
- `unknown`。

不能机械把所有相关节点改成 Blocked。

---

# 31. Verification Failure 的回流

Verification failure 的标准路径：

```text
1. Verification produces Failure Evidence
2. Impact Analysis identifies affected targets
3. Affected target validity/acceptance projection changes
4. Rework / Investigation / Graph Revision is created where necessary
```

禁止：

```text
Test failed
→ reset entire Graph
```

如果失败只指向 PDA mapping，则 Backend/Web 可保持 Accepted。

---

# 32. Unknown Impact

当 Verification 失败但无法确定责任来源时：

```text
Impact = UNKNOWN
```

此时 SHOULD 创建 Investigation WorkItem，而不是随机 Reopen 多个节点。

例如：

```text
Integration failure
Cause unknown
↓
Investigation WorkItem
```

历史 Acceptance 可以保持，但 Validity Projection 标记 `under_review / unknown`。

---

# 33. Needs Rework

`needs_rework` 表示：

> 已经存在成果，但当前 Evidence 表明它还不能满足 Acceptance。

它与 Blocked 不同：

- Blocked：当前无法继续；
- Needs Rework：已知需要继续工作。

因此它属于 Acceptance/Outcome 语义，不是 Lifecycle 的一级状态。

---

# 34. 父 Work 的状态传播

父 Work MUST NOT 采用以下机械规则：

```text
any child blocked → parent blocked
all children accepted → parent accepted
```

父 Work 有自己的：

- Goal；
- Work-level Acceptance Policy；
- Verification；
- Delivery。

子 WorkItem 的 Acceptance 是父 Work 的 Preconditions / Evidence，而不是最终裁判。

父 Work GUI SHOULD 展示：

- Primary Phase；
- Required children accepted count；
- Running count；
- Blocker count；
- Reverification / Rework count；
- Work-level Acceptance progress。

---

# 35. 简单 Work 的隐式 WorkItem

简单工作，例如“修 README 拼写”，领域上仍可使用 WorkItem，但 UI SHOULD 折叠这一层。

```text
Simple Work
≈ one implicit WorkItem
```

复杂 Work 才展开 Work Graph。

这保证“简单需求走简单路径”。

---

# 36. Graph Revision：什么算 Revision

Graph Revision 是：

> 影响 Work 的工作结构、执行语义或验收语义的一次可审计变更版本。

以下通常属于 Graph Revision：

### Structural Revision

- 新增/移除（尚未执行的）WorkItem；
- WorkItem Superseded；
- Decomposition 改变；
- Dependency 新增/删除/重新绑定；
- Required / Optional / Conditional 改变。

### Semantic Revision

- WorkItem Goal 改变；
- WorkItem Acceptance Policy 改变；
- Required Outcome / Contract 改变；
- Dependency Condition 改变；
- Work-level Acceptance 改变。

以下 不属于 Graph Revision：

- AgentRun start/stop；
- 一次 Tool 调用；
- 测试开始/结束；
- 普通 Event Stream 增长；
- Execution State 从 idle → executing；
- Readiness Projection 自动变化。

这些是运行事实，不是工作模型版本变化。

---

# 37. Current Graph 与 Graph History

每个 Work 应存在：

- Current Graph Revision：当前用于规划和调度的工作模型；
- Graph Revision History：过去每次工作结构/语义变化的历史。

可以概念化：

```text
G1
↓ Revision R2
G2
↓ Revision R3
G3 (current)
```

实现可以使用 Event 重建、snapshot 或其他方式；本规范不规定存储技术。

---

# 38. Revision Identity

每次 Revision 应至少可追溯：

```text
Revision ID
Base Revision
Actor
Time
Reason
Evidence references
Changed graph elements
Impact class
Approval / policy decision
```

Graph revision number 可以是用户友好的单调版本（例如 `r17`），但不能代替稳定 Revision ID。

---

# 39. Proposal、Approval、Apply 分离

Graph 修改应区分：

```text
GraphChangeProposal
        ↓
Impact Evaluation
        ↓
Approval / Policy
        ↓
Applied Revision
```

AI 可以提出 Proposal，但 Proposal 本身不是事实上的 Current Graph。

这防止 Planner Agent 直接拥有重写整个生产计划的权力。

---

# 40. Revision Impact Class

v0.1 建议三档：

## 40.1 Local

只影响尚未执行的局部工作，不影响当前 Accepted/Running 的关键节点。

例如新增一个 optional documentation WorkItem。

可以允许 Automation/AI 按 Policy 自动应用。

## 40.2 Propagating

会改变多个节点 Readiness、Validity、Verification 或 Scheduling。

例如 API Contract Required Outcome 改变。

MUST 生成 Impact Report；是否自动应用由 Workspace Policy 决定。

## 40.3 Destructive / High-impact

涉及：

- 修改 Work Goal / Work-level Acceptance；
- 取消正在运行的 WorkItem；
- 让已经 Delivered 的结果失效；
- 改变安全/业务 Hard Constraint；
- 删除/隐藏已有执行历史。

此类 Revision MUST 要求治理主体明确批准，并且禁止抹除历史。

---

# 41. AI 的 Graph 修改权限

AI SHOULD 能够：

- 建议新增 Investigation WorkItem；
- 建议新增 Dependency；
- 建议 Supersede 旧计划；
- 根据 Evidence 生成 Impact Analysis。

AI MUST NOT 无条件自动：

- 改 Work Goal；
- 改 Hard Constraint；
- 改 Work-level Acceptance；
- 取消正在执行/已交付的关键 WorkItem；
- 删除历史 WorkItem；
- 让历史 Verification 消失。

即：

> AI 可以组织劳动，但不自动拥有最高产品目标和治理主权。

---

# 42. 正在运行的 WorkItem 遇到 Revision

Revision 影响 Running WorkItem 时 MUST NOT 默认 kill AgentRun。

Impact Evaluation 应至少得出：

### Unaffected

继续执行。

### Review Required

继续或短暂停留，由 Agent/Policy 检查新变化。

### Potentially Invalidating

通常 Pause & Re-evaluate；继续执行需要明确 Policy。

### Invalidated

当前 Assignment/Plan 已失去意义。停止执行、生成 Handoff/Evidence，并重新规划。

停止真实执行仍必须尊重 Runtime 的副作用安全规则。

---

# 43. Accepted WorkItem 遇到 Revision

如果过去 Verification 的适用条件变化：

```text
Historical Acceptance = remains true as history
Current Validity = stale / reverification_required
```

MUST NOT 直接删除过去 Acceptance。

新 Verification 完成后产生新的 Validity/Acceptance 判断。

---

# 44. Delivered Work 遇到 Revision

已经 Delivered 的现实变化尤其不能通过 Graph 修改“撤销历史”。

如果新业务要求改变已交付功能，应创建：

- Reopen；或
- Follow-up Work；或
- New WorkItem / ChangeSet。

具体选择由 Work Policy 决定。

但历史 Delivery 永远存在：

```text
Delivery #1 happened
Later Work changed it
```

而不是假装 Delivery #1 从未发生。

---

# 45. Graph Revision 与 Assignment

Assignment 是基于某个 Work Graph / WorkItem 语义创建的。

Assignment 应能够追溯：

```text
created_against_graph_revision: G17
```

如果 Current Graph 变为 G18：

- 不影响该 Assignment → 可继续；
- 语义发生变化 → Assignment `review_required`；
- Goal/Scope 实质改变 → old Assignment superseded，创建新 Assignment。

这避免 Agent 在旧任务定义下继续工作却没人知道。

---

# 46. Graph Revision 与 Verification

Verification 应记录：

```text
Target
Criteria version
Relevant Graph Revision
Relevant Outcome revisions
Environment / scope
Evidence
Result
```

Graph 更新后，系统通过这些关联判断旧 Verification 是否仍 Current。

Graph Revision MUST NOT 强迫所有旧 Verification 一律失效；只对真正受影响的范围传播 Validity Impact。

---

# 47. Graph Revision 与 Runtime Event Store

产品语义上二者相似，但不是同一个层级：

### Runtime Event Store

记录 AgentRun/Session 中的推理、Tool、Observation、Execution 等运行事实。

### Workbench Graph History

记录 Work/WorkItem 结构和组织语义如何改变。

实现上未来 MAY 使用同一物理 Event Infrastructure，也 MAY 分开。

本规范只要求：

> 两类历史都可追溯，并能够通过稳定引用建立因果关系。

例如：

```text
Runtime Evidence E381
↓ caused
Graph Change Proposal GP19
↓ accepted
Graph Revision G27
```

---

# 48. Graph Audit

用户必须能够回答：

1. 为什么这个 WorkItem 被加入？
2. 谁把 Dependency 从 A 改到 B？
3. 当时依据了什么 Evidence？
4. 哪些正在执行的 AgentRun 被 Revision 影响？
5. 为什么一个已 Accepted 节点现在需要 Reverification？
6. 旧 Graph 在当时是什么样？
7. 当前 Graph 与某个历史 Revision 有什么差异？

因此未来 GUI SHOULD 提供：

- Revision timeline；
- Graph diff；
- Impact report；
- Evidence links；
- actor / approval；
- affected WorkItems。

具体界面不属于本规范。

---

# 49. 删除、取消与历史完整性

## 49.1 未执行的计划节点

如果没有执行、Artifact、Verification、引用，可以允许更自由地删除/编辑。

## 49.2 一旦存在执行历史

WorkItem MUST NOT 被物理意义“消失”。

使用：

- Cancelled；
- Superseded；
- Reopened；
- Reworked。

保留其历史 Artifact、AgentRun、Verification 和原因。

---

# 50. Graph Revision 不等于 Workflow 回滚

Verification 失败或计划改变时：

禁止：

```text
rollback graph to G12
and pretend G13-G17 never existed
```

正确模型：

```text
G17 current facts
↓ New Evidence
G18 new revision
```

历史 Revision 仍然存在。

Praxis 的纠错是“基于新事实向前修正”，不是重写过去。

---

# 51. Graph Change 的来源

Graph Change Proposal 可以来自：

- Human；
- Planner Agent；
- Executor Agent；
- Reviewer / Verification；
- Automation；
- External Integration；
- Template 初始化。

来源不同不改变产品语义。

重要的是：

```text
Proposal ≠ Applied Revision
```

---

# 52. Graph Challenge

Challenge 可以把 Work Graph element 作为 Target：

```text
Challenge:
Target = Dependency D17
Claim = current dependency direction contradicts actual API ownership
Evidence = E32, E37
```

接受后产生 Graph Change Proposal / Revision。

这使 Praxis 的 Challenge 从 Runtime 内部认识纠错自然扩展到 Workbench 的组织计划纠错。

---

# 53. Graph 收敛与风险

Work Graph 不要求一开始稳定。

健康的复杂 Work 通常表现：

```text
Early:
high uncertainty / frequent graph revisions

Middle:
parallel execution / contracts stabilize

Late:
low graph volatility / verification + delivery dominate
```

如果接近 Delivery 仍频繁修改 Goal、核心 Acceptance 或关键 Dependency，系统 SHOULD 提示 Work 尚未真正收敛。

Graph Volatility（图波动率）以后可作为风险 Projection，本规范不定义指标公式。

---

# 54. Automation 与 Work Graph

Graph relation 定义现实工作关系；Automation 定义系统在事实变化后是否自动采取行动。

```text
Dependency:
Backend Contract → Web Ready

Automation:
on Web became Ready → schedule Frontend Agent
```

二者 MUST NOT 合并。

Automation 不应拥有修改 Work Goal / Hard Constraint 的默认权限。

---

# 55. Projection Change Events

Automation / GUI 可以消费派生变化通知，例如：

```text
WorkItemBecameReady
WorkItemBecameBlocked
VerificationBecameStale
WorkNeedsReverification
GraphRevisionApplied
```

这些通知可以被实现成 Event，但它们的根本依据仍是 durable facts + projection computation。

产品 MUST NOT 形成两套互相矛盾的权威状态。

---

# 56. MES 参考场景

Work：

```text
MES-2041 首检状态校验
```

初始结构：

```text
Analysis
   │
   ▼
Backend Contract
   │
 ┌─┼─────────────┐
 ▼ ▼             ▼
Web PDA         Machine
 \  |            /
  \ |           /
   Integration
       │
    Delivery
```

## 56.1 早期并行

Backend 先发布：

```text
API Contract rev3 = Accepted
```

因此：

```text
Web Ready
PDA Ready
Machine Ready
```

不需要等待 Backend Implementation 全部完成。

## 56.2 新 Evidence

PDA Agent 发现旧终端无法处理新字段。

```text
Blocking Challenge
↓
Compatibility Decision WorkItem
```

Human 选择保留兼容。

Graph Revision G4：

```text
Add Backend Compatibility Layer
Add Dependency:
Compatibility Layer → PDA Acceptance
```

PDA 从 Blocked 转 Waiting。

## 56.3 Contract Revision

Backend Contract rev4 改变字段类型。

Coordination Impact：

```text
Web based on rev3 → reverification_required
PDA based on rev3 → review_required
Machine not started → readiness recomputed
```

历史 Verification 不被删除。

## 56.4 Integration failure

Integration Test 指向 PDA mapping 错误。

```text
Failure Evidence
↓
Impact = PDA
↓
PDA needs_rework
```

Backend/Web 保持 Accepted。

这就是“传播 Impact，而不是复制状态”。

---

# 57. 正式 Work Graph 不变量

以下规则作为 v0.1 产品基线：

1. Work Goal / Acceptance 高于 Work Graph。
2. Work Graph 是当前计划，不是永久 Workflow。
3. Work Tree 只是 Decomposition 的人类 Projection。
4. Decomposition 与 Dependency 必须分离。
5. Required Dependency 子图必须无环。
6. Dependency 优先绑定 Required Outcome，而非 WorkItem 粗状态。
7. Start Condition 与 Acceptance Condition 必须分离。
8. Required、Advisory Dependency 分离。
9. Dependency condition 支持 SATISFIED / UNSATISFIED / UNKNOWN。
10. Ready 是派生状态，并且必须可解释。
11. Ready ≠ Scheduled ≠ Assigned ≠ Executing。
12. Waiting ≠ Blocked ≠ Paused。
13. Execution completed ≠ Accepted。
14. Accepted ≠ Delivered ≠ Closed。
15. 父 Work 有独立 Acceptance。
16. Required / Optional / Conditional WorkItem 分离。
17. Coordination 处理变化影响，Dependency 处理前置条件。
18. 传播 Impact，不复制状态。
19. Accepted/Verified 结果可以变 Stale，但历史不得改写。
20. Verification Failure 产生 Evidence → Impact → Rework，而非全图回滚。
21. UNKNOWN Impact 应触发调查，而非随机 Reopen。
22. Graph Revision 必须可追溯。
23. Proposal 与 Applied Revision 必须分离。
24. 高影响 Revision 需要治理批准。
25. 运行中的 WorkItem 遇到 Revision 不默认 kill。
26. 一旦存在执行历史，节点不能通过删除抹去。
27. Superseded 不等于 Dependency 自动迁移。
28. Graph 历史 append-oriented。
29. Automation 消费 Graph/Projection，不拥有最终 Goal 主权。
30. Graph 的所有复杂性必须服务于减少真实生产等待、提高可纠错性和交付可靠性。

---

# 58. v0.1 明确不做

本规范不冻结以下实施细节：

- Graph 数据库/存储引擎；
- Graph Event 与 Runtime Event 是否物理共库；
- Readiness Policy DSL；
- 通用布尔规则语言；
- Scheduler 算法；
- Critical Path 算法；
- Automation DSL；
- Impact Analysis 的具体 AI Prompt / Model；
- Graph Diff GUI；
- Work Tree 视觉组件；
- 多用户 Graph 并发编辑算法；
- CRDT / distributed graph；
- Graph permission Schema；
- Jira/Linear/禅道同步映射。

这些应由后续产品专题和系统设计决定。

---

# 59. 后续专题接口

本规范完成后，后续产品设计按以下顺序继续：

## 59.1 Agent Work / Handoff 详细规范

重点：

- Assignment 生命周期；
- Agent Definition；
- AgentRun 与 Resume/New Run 边界；
- Structured Handoff；
- Multi-Agent 工作交接。

## 59.2 Multi-Repository / Git / ChangeSet 规范

重点：

- Repository 与 Workspace；
- Git Worktree isolation；
- RepoChange；
- Cross-repo ChangeSet；
- Review / Merge / Delivery。

## 59.3 Automation 产品模型

重点：

```text
Trigger
Condition
Action
```

以及因果链、去重、循环保护与审批。

## 59.4 GUI 信息架构

建立在已经冻结的产品领域和 Work Graph 语义之上，而不是反过来为了 GUI 修改领域模型。

---

# 60. 总结

Praxis Work Graph 不是一个“AI 自动生成的流程图”。

它是：

> 为了实现 Work Goal，由 WorkItem、条件依赖、协调关系、验证关系以及可审计 Revision 共同组成，并根据现实 Evidence 持续演化的工作模型。

它的核心运动是：

```text
Goal
↓
Current Work Graph
↓
Ready WorkItems
↓
Execution
↓
Artifacts / Outcomes / Evidence
↓
Verification
↓
Relation & Validity Re-evaluation
↓
Graph Revision / Rework when needed
↓
Work-level Acceptance
↓
Delivery
```

因此 Praxis 所追求的不是“让任务严格按照计划执行”，而是：

> 让计划能够在真实工作中被检验、被修改，同时让每一次变化都有证据、有影响范围、有治理边界，并且不抹去已经发生的历史。

这就是 Praxis Workbench 从普通 Task Manager、固定 Workflow Engine 与聊天式 Coding Agent 中真正分离出来的核心产品机制之一。
