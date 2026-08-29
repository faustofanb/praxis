# Praxis Multi-Repository / Git / ChangeSet 详细规范

## v0.1 产品基线

**版本：v0.1**  
**日期：2026-08-29**  
**文档性质：多仓库工作成果与交付模型基线 / Normative Multi-Repository Delivery Baseline**  
**上位文档：**《Praxis 产品白皮书》《Praxis Workbench 产品领域模型与核心概念规范 v0.1》《Praxis Work Graph 与工作生命周期详细规范 v0.1》《Praxis Agent Work / Handoff 详细规范 v0.1》

> 本规范冻结 Praxis Workbench 中 Workspace、Repository、Repository Binding、Git Worktree、RepoChange、ChangeSet、Integration、Review 与 Delivery 的产品语义，并规定多仓库代码成果如何从 AgentRun 的执行现场转化为可版本化、可验证、可审查、可交付的 Work Outcome。本文不定义数据库 Schema、Git 命令实现、Branch 命名规范、CI/CD 平台 API、具体 Merge/Rebase 算法、GUI 组件或远程执行协议。

---

# 目录

1. 文档定位与规范用语
2. 多仓库工作总体模型
3. Workspace：长期业务工作空间
4. Repository Identity 与 Repository Binding
5. Repository Scope、Role、Knowledge 与 Policy
6. Execution Environment 与 Git Worktree
7. Git Branch / Commit / Working Tree 的产品边界
8. RepoChange：单仓库逻辑工作成果
9. RepoChange 生命周期与 Candidate Revision
10. ChangeSet：Work 的跨仓库逻辑变更集合
11. ChangeSet Revision、完整性与验证边界
12. Repository Impact 与 No Change Required
13. Integration 总体模型
14. Integration Environment 与跨仓库组合验证
15. Target Divergence、Rebase 与 Candidate Lineage
16. Integration Conflict 与冲突处理
17. RepoChange Review 与 ChangeSet Review
18. PR / MR 与外部 Git 平台映射
19. Delivery 总体模型
20. Build、Release、Environment 与 Delivery Target
21. Staged Delivery、Observed State 与 Reconciliation
22. Delivery Failure、UNKNOWN、Rollback 与 Hotfix
23. MES 多仓库端到端参考场景
24. 对象所有权与权威关系矩阵
25. Multi-Repository 产品不变量
26. v0.1 明确不做
27. 后续专题待决问题
28. 术语表

---

# 第一章　文档定位与规范用语

## 1.1 本文解决什么问题

前四份规范已经回答了以下问题：

```text
Work 为什么存在？
Work / WorkItem / Work Graph 如何组织？
WorkItem 什么时候 Ready / Waiting / Blocked？
Assignment 怎样把 WorkItem 交给 Agent / Human / Automation？
AgentRun / Session / Handoff 如何划界？
多个 Agent 怎样隔离执行并把成果汇合到 ChangeSet？
```

但真实研发工作最终必须落到代码仓库和运行环境。尤其在 MES、ERP、WMS 等生产系统中，一个业务 Work 往往同时涉及：

```text
Java Backend
Web Admin
PDA UniApp
Machine Terminal
Shared Contract
Database Migration
CI/CD / Test Environment
```

如果 Praxis 只会管理 AgentRun，却不能回答以下问题，就仍然只是一个“多 Agent IDE”：

```text
一个 Repository 在 Praxis 中到底是什么？
换路径、换电脑、换 remote 后，它还是不是同一个 Repo？
AgentRun 的 dirty worktree 什么时候成为 Work 的正式成果？
RepoChange 与 commit / branch / diff 有什么区别？
三个 Repo 的候选版本怎样组成一个稳定的跨仓库 ChangeSet Revision？
Integration 到底验证什么？
main 分支变化以后，之前的 Verification 是否还有效？
Merge Conflict 是 Shell error 还是正式工作事实？
Repo Review 与 Work-level Review 为什么不同？
PR/MR 与 Praxis 的 RepoChange / ChangeSet 是什么关系？
Merge、Build、Release、Deploy、Delivered、Closed 为什么不能混成一个状态？
```

本文负责冻结这些产品语义。

---

## 1.2 规范用语

本文使用：

- **MUST / 必须**：后续产品设计和实现不得违反；
- **MUST NOT / 禁止**：出现即视为领域边界破坏；
- **SHOULD / 应当**：默认产品方向，偏离必须有明确理由；
- **MAY / 可以**：允许的扩展，不构成 v0.1 必备能力。

本文中的状态、Revision、Role、Policy 为产品领域语义，不等价于最终数据库字段、TypeScript enum、Git ref 或 API Schema。

---

## 1.3 六条最高原则

### Work over Git

Praxis 的最高交付对象仍然是 Work。Git Repository、Branch、Commit、PR/MR 是完成 Work 的生产手段，而不是产品世界观。

### Repository Identity over Path

逻辑 Repository 的身份 MUST 与当前本地路径、Remote URL 和执行 Host 分离。

### Working State is not Product State

AgentRun 的 Working Tree 是执行现场；只有被纳入 RepoChange / ChangeSet 的候选 Revision 才成为可验证的正式 Work 成果。

### Stable Revision before Verification

Review、Verification、Integration、Delivery MUST 尽可能绑定不可变、可重建的明确 Revision，而不是模糊的“最新代码”。

### Cross-Repository Consistency through ChangeSet

Praxis 不制造跨 Git Repository 的伪原子事务。跨仓库一致性通过 ChangeSet Revision 表达和验证。

### Propagate Impact, not Panic

Repository、Target Branch、ChangeSet 或 Delivery 发生变化时，系统传播具体影响并重新评估 Validity，而不是统一清空所有状态或机械全图回滚。

---

# 第二章　多仓库工作总体模型

## 2.1 产品主线

Praxis 中 Repository-changing Work 的主要生产链为：

```text
Workspace
  ↓
Work
  ↓
Work Graph / WorkItems
  ↓
Assignments / AgentRuns
  ↓
Execution Environments
  ↓
Working Changes
  ↓
RepoChange Candidate Revisions
  ↓
ChangeSet Revision
  ↓
Integration / Review / Verification
  ↓
Delivery
  ↓
Observed Target Reality
  ↓
Post-delivery Verification
  ↓
Work Acceptance / Closure
```

其中 Git primitives 只存在于中间：

```text
Repository
Branch
Commit
Tag
Merge Request
Worktree
```

这些对象帮助形成 RepoChange 和 ChangeSet，但不拥有 Work Goal / Acceptance。

---

## 2.2 四层对象关系

Praxis MUST 保持以下层级：

```text
Work
  ↓
ChangeSet
  ↓
RepoChange
  ↓
Git Primitives
```

### Work

回答：

> 为什么要改变现实？最终什么结果算完成？

### ChangeSet

回答：

> 为完成这个 Work，当前跨仓库候选代码现实由哪些精确 RepoChange Revision 组成？

### RepoChange

回答：

> 在一个具体 Repository 中，这个 Work 形成了什么逻辑变更？

### Git primitives

回答：

> 这些逻辑成果在 Git 中如何被保存、比较、协作和集成？

MUST NOT 把这四层折叠为一个 `branch = work` 或 `PR = task` 模型。

---

## 2.3 典型 MES 结构

```text
Workspace: MES

Repositories
├─ mes-server        Java backend
├─ mes-web           Vben Admin 5
├─ mes-pda           UniApp PDA
├─ mes-machine       UniApp machine terminal
├─ mes-tablet        UniApp tablet
└─ shared-contracts  optional shared contracts

Work: MES-2041 首检拦截

ChangeSet CS-2041 rev12
├─ RC-BACKEND rev5
├─ RC-WEB     rev3
├─ RC-PDA     rev6
└─ RC-MACHINE rev2
```

Praxis 用户应首先看到 `MES-2041` 的整体成果，再按需要下钻到 RepoChange、Branch、Commit 和 Diff。

---

# 第三章　Workspace：长期业务工作空间

## 3.1 Workspace 的正式定义

> **Workspace 是为长期完成一组相关 Work 而共同管理 Repository、Knowledge、Agent Definitions、Work Templates、Automation、Integration、Environment 与 Policy 的逻辑产品边界。**

Workspace MUST NOT 等同于本地文件夹或 IDE 当前打开目录。

例如：

```text
Workspace: MES

Business Context:
  manufacturing execution system

Repositories:
  backend
  web
  pda
  machine

Integrations:
  GitLab
  Jenkins
  issue tracker
  test DB
```

这些 Repository 即使物理路径分散、运行在不同 Host，仍然属于同一个逻辑 Workspace。

---

## 3.2 Workspace 是长期产品对象

Workspace 应当能够跨以下变化保持稳定：

```text
local path changed
machine changed
repository re-cloned
remote URL migrated
Agent execution moved to remote host
workspace partially offline
```

因此，历史 Work、Handoff、RepoChange、ChangeSet MUST 引用 Workspace / Repository 稳定身份，而不是临时文件路径。

---

## 3.3 Workspace 的典型资产

```text
Workspace
├─ Repositories
├─ Works
├─ Agent Definitions
├─ Work Templates
├─ Repository Knowledge
├─ Workspace Knowledge
├─ Policies
├─ Environment Definitions
├─ External Integrations
└─ Automation Definitions
```

本文只详细规范 Repository、ChangeSet 和 Delivery；其他对象由各自专题负责。

---

## 3.4 一个 Repository 可以属于多个 Workspace

共享 SDK 或 Contract Repository 可以同时服务多个产品：

```text
shared-sdk
├─ MES Workspace
├─ WMS Workspace
└─ QMS Workspace
```

因此 Workspace 与 Repository 在领域上 MAY 是多对多关系。

但每个 Work SHOULD 有一个 Primary Workspace，用于确定默认 Policy、Knowledge 与 Environment。

---

# 第四章　Repository Identity 与 Repository Binding

## 4.1 Repository 的正式定义

> **Repository 是 Workspace 中一个具有稳定产品身份、版本历史和变更边界的版本控制代码资产。**

Repository Identity MUST 独立于：

```text
local filesystem path
current remote URL
current clone
current Git worktree
current branch
current execution host
```

示意：

```text
Repository
  id: repo-mes-backend
  displayName: MES Backend
  role: backend
```

本地路径只是 Binding。

---

## 4.2 Repository Path 不是身份

以下两个 Binding 可以是同一个 Repository：

```text
Windows:
D:/projects/mes-server

Linux:
/srv/work/mes-server
```

Work / ChangeSet / Handoff MUST 引用 `repo-mes-backend` 等稳定身份，而不是 `D:/projects/...`。

---

## 4.3 Remote URL 也不是唯一身份

Remote 可能因为以下原因变化：

```text
GitLab migration
mirror
fork
SSH/HTTPS protocol switch
company domain migration
```

Praxis MAY 使用 remote fingerprint、Git object history 等协助识别 Repository，但 v0.1 不规定具体算法。

核心规则只有一个：

> Repository Identity 与 Remote Identity 必须分离。

---

## 4.4 Repository Binding

> **Repository Binding 是一个逻辑 Repository 在某个 Execution Host / 用户环境中的具体可操作实例。**

例如：

```text
Repository: repo-mes-backend

Binding A
Host: Developer Laptop
Path: D:/code/mes-server

Binding B
Host: Linux Agent Host
Path: /srv/agents/mes-server
```

AgentRun 不直接“拥有 Repository”；它通过 Execution Environment 使用一个或多个 Repository Binding。

---

## 4.5 Binding 的可用性是 Readiness Fact

如果 Repository 尚未 Clone 或当前 Host 无可用 Binding：

```text
RepositoryBindingAvailable(repo-pda) = false
```

则依赖该 Repo 写入的 WorkItem 可以派生为：

```text
Waiting
Reason: repository binding unavailable
```

而不是让 AgentRun 启动后才以 `cd: no such directory` 失败。

---

## 4.6 Monorepo 与 Multi-repo 共用同一模型

Praxis MUST NOT 建立两套独立领域模型：

```text
Monorepo Mode
MultiRepo Mode
```

产品统一表示：

```text
Workspace
  ↓
Repository [0..N]
```

Monorepo 内部 `apps/`、`packages/` 等属于 Repository 内部模块结构，不是 Workspace 多仓库语义。

---

# 第五章　Repository Scope、Role、Knowledge 与 Policy

## 5.1 Expected Repository Scope 与 Actual Impact

Work 创建时可以根据需求推断：

```text
Expected Repository Scope:
backend
web
pda
```

但实际执行以后可能只有：

```text
Actual Repository Impact:
backend
pda
```

二者 MUST 分离。

Expected Scope 是规划假设；Actual Impact 必须来自真实 RepoChange 或明确的 No Change Required Outcome。

---

## 5.2 WorkItem Repository Scope

WorkItem 应当比 Work 拥有更具体的执行范围：

```text
Work: MES-2041
Expected: backend, web, pda

WorkItem: Backend API
Primary: backend
Read: backend, web
Write: backend
```

建议区分：

- **Primary Repositories**：该 WorkItem 的主要代码责任范围；
- **Read Repositories**：执行主体可读取的 Repo；
- **Write Repositories**：执行主体可以产生正式修改的 Repo。

Repository Scope MUST NOT 自动等价于 Capability，最终写权限仍由 Execution Environment / Capability Policy 决定。

---

## 5.3 Repository Role

Repository MAY 拥有产品语义角色：

```text
backend
web
terminal:pda
terminal:machine
shared-contract
infra
```

Role 用于：

- Planner 提示；
- Work Template 默认范围；
- GUI 分组；
- Repository Policy 选择。

Role MUST NOT 被当成真实影响证据；最终 Actual Impact 仍由实践产生。

---

## 5.4 Repository Knowledge 的所有权

以下知识应主要归属于 Workspace / Repository：

```text
build commands
test commands
tech stack
code conventions
architecture notes
known limitations
AGENTS.md / repository instructions
setup procedure
```

MUST NOT 主要依赖某个永久 Agent 的隐式“记忆”。

> Knowledge belongs to Workspace / Repository; capability belongs to Agent Definition.

---

## 5.5 Repository Policy

Repository 可以拥有自己的默认 Policy，例如：

```text
required review
forbidden paths
branch protection expectations
DB migration review
security checks
build gate
```

这些 Policy 后续可映射到机器 Gate，但本文不规定文件格式。

---

# 第六章　Execution Environment 与 Git Worktree

## 6.1 Execution Environment 的定位

Agent Work 规范已定义：

> Execution Environment 是 AgentRun 接触文件、Repository、工具和有限资源的隔离运行边界。

对于 Coding AgentRun，它可以包含：

```text
AgentRun R17

Execution Environment
├─ backend binding → worktree WT17-A → read-write
├─ web binding     → checkout         → read-only
├─ test DB lease
├─ tools
└─ network/capabilities
```

一个 AgentRun MAY 同时绑定多个 Repository，但每一个 Binding 和 Read/Write Mode MUST 显式可解释。

---

## 6.2 AI 默认不写用户 Main Working Tree

用户当前主工作目录可能存在：

```text
uncommitted code
local experiments
manual branch
ignored files
private configuration
```

Praxis MUST 默认避免让 AI Coding Run 直接在用户 Main Working Tree 中执行 destructive Git operations 或持续写入。

默认推荐：

```text
Human Main Checkout
        ≠
Praxis Isolated Worktree
```

---

## 6.3 当前 Checkout 模式必须显式选择

用户可以明确要求：

> 就在我当前改动基础上继续。

此时 Praxis MAY 提供 `Use Current Checkout` 模式，但必须：

- 显示当前 dirty state；
- 不静默 stash/reset 用户修改；
- 记录 Run 起点；
- 必要时创建可重建 Snapshot / Checkpoint；
- 将用户已有修改与 Agent 新增修改尽量可区分。

默认仍应优先隔离 Worktree。

---

## 6.4 Git Worktree 的正式定义

> **Git Worktree 是某个 Repository Binding 为一个隔离执行上下文提供的具体 Git 工作副本。**

它是 Execution Resource，不是 Work、WorkItem、AgentRun 本身。

典型用途：

```text
IMPLEMENTATION
REVIEW
INTEGRATION
RECOVERY
COMPETITIVE
```

---

## 6.5 Worktree 生命周期与 AgentRun 不完全一致

Agent process 结束或 crash 后，Worktree 不应立即自动销毁。

尤其：

```text
AgentRun = FAILED / PAUSED
Worktree = dirty
```

系统必须保留现场，直到明确执行：

```text
Resume
Adopt
Checkpoint
Archive
Discard
```

其中 Discard 是有意识的治理动作，MUST NOT 由 Agent默认执行 `git reset --hard` 代替。

---

## 6.6 Run 启动时冻结 Base Revision

有写权限的 Repo Binding 在 AgentRun 启动时，应记录：

```text
Repository
Base Revision
Branch / Candidate identity
Worktree identity
```

Remote main 后续变化不会悄悄修改 Run 起点。

---

# 第七章　Git Branch / Commit / Working Tree 的产品边界

## 7.1 Work ≠ Branch

一个 Work 可能涉及多个 Repository，自然不会只有一个 Git Branch。

同一个 Work 也可能经历：

```text
implementation branch
competitive candidate branch
review fix
hotfix follow-up
release mapping
```

因此 Branch MUST NOT 成为 Work Identity。

---

## 7.2 AgentRun ≠ Worktree ≠ Branch

稳定关系应理解为：

```text
AgentRun
  uses
Execution Environment
  uses
Worktree
  checks out
Branch / Candidate
  contributes to
RepoChange
```

Run 完成后 Branch / RepoChange 可以继续演进；Worktree 可以清理；Run 历史不可消失。

---

## 7.3 Branch 主要承载 RepoChange 的 Git 演进

默认情况下，一个主要 RepoChange 可以拥有一个主要 Git Branch / candidate lineage：

```text
WorkItem(s)
   ↓
RepoChange
   ↓
Branch
```

多个顺序 Run 可以继续贡献同一个 RepoChange，而不必每个 Run 都创建一个最终独立 Branch。

Competitive Execution 是例外：多个候选 RepoChange 应拥有隔离 Branch / Worktree。

---

## 7.4 RepoChange ≠ Commit

一个 RepoChange 可以表现为：

```text
1 commit
5 commits
squashed commit
rebased commits
synthetic snapshot
```

Git Commit 是版本控制历史形式；RepoChange 是 Work 的产品语义。

因此交互式 rebase 改变 Commit 数量，不会自动改变“这是哪个逻辑工作成果”。

---

## 7.5 RepoChange ≠ Diff

Diff 是某个 Base 与 Head / Snapshot 的差异表示。

RepoChange 还包含：

```text
Purpose
Repository
Base
Candidate Revision
Contributors
WorkItem relations
Verification
Review
Integration status
```

所以“当前 diff 为空”也不意味着这个 RepoChange 的历史不存在。

---

## 7.6 Working Changes ≠ RepoChange

Working Tree 中的临时修改可以包含：

```text
scratch code
debug logging
failed approach
instrumentation
temporary fixture
```

这些只是执行现场。

只有被明确纳入 Work 的候选成果才成为 RepoChange 的正式组成。

---

# 第八章　RepoChange：单仓库逻辑工作成果

## 8.1 正式定义

> **RepoChange 是一个 Work 在单一 Repository 中形成的逻辑变更单元，它汇聚一个或多个 AgentRun / Human Execution 对该 Repository 的有效贡献。**

核心属性语义上包括：

```text
Work relation
Repository
Purpose
Candidate lineage
Base
Current candidate revision
Contributors
Related WorkItems
Review / Verification relations
External PR/MR mappings
```

---

## 8.2 一个 Work 默认每个 Repo 一个主要 RepoChange

为降低产品复杂度，v0.1 推荐：

```text
Work MES-2041
├─ RC backend
├─ RC web
└─ RC pda
```

只有当同一 Repository 中确实存在独立的：

- Review；
- Delivery；
- rollback；
- competitive candidate；
- 生命周期；

才拆成多个 RepoChange。

---

## 8.3 RepoChange 可由多个 Run 顺序贡献

例如：

```text
Run R17
initial implementation
↓
RC backend rev1

Review changes requested
↓
Run R21
fix review findings
↓
RC backend rev2

Integration conflict
↓
Run R26
conflict resolution
↓
RC backend rev3
```

Work 的逻辑成果没有变成三个 RepoChange；Contributor History 记录劳动过程。

---

## 8.4 默认单写

同一个 RepoChange MUST 默认只有一个 active implementation writer。

如果两个 Agent 需要独立尝试同一 WorkItem：

```text
Candidate A → RepoChange A
Candidate B → RepoChange B
```

最终通过 Verification / Review 选择，而不是让两个 Agent 同时写同一个逻辑 RepoChange。

---

## 8.5 Investigation 变化默认不进入 RepoChange

Investigation Run 产生的：

```text
reproducer
trace hook
temporary SQL
scratch script
```

应首先作为 Investigation Artifact / Working State。

只有明确 `Promote` 后，才纳入正式 RepoChange。

---

# 第九章　RepoChange 生命周期与 Candidate Revision

## 9.1 不使用一个超级状态枚举

RepoChange SHOULD 至少分解为以下正交语义：

### Composition

```text
working
candidate
frozen
```

### Verification

```text
unverified
verifying
verified
needs_rework
```

### Review

```text
unreviewed
reviewing
approved
changes_requested
```

### Integration

```text
standalone
assembled
conflicting
integrated
```

这些名称是产品语义，不要求成为最终字段。

---

## 9.2 Working State 与 Candidate Revision

AgentRun 可以持续修改 Working State，而不持续破坏当前稳定 Candidate。

```text
RC backend
Current Candidate: rev5 ✓ verified
Working State: 3 files ahead
```

这是正常情况。

Praxis MUST 允许：

> Execution Current 与 Candidate Current 同时存在。

---

## 9.3 Candidate Revision 的正式定义

> **RepoChange Candidate Revision 是在某个时刻被冻结、可重建、可用于 Review / Verification / ChangeSet Assembly 的逻辑候选版本。**

它 SHOULD 尽量绑定不可变 Git Commit；如果用户不愿 Commit，也可以通过可重建 Snapshot 表示。

关键不是“必须 commit”，而是：

> Verification Target 必须可重建。

---

## 9.4 Candidate Revision 不等于每个 Commit

AgentRun 可能连续产生多个 Commit，但仍在同一 Working 阶段。

Candidate Revision 应由以下事件之一触发：

```text
Run submits candidate
Review requested
Verification requested
Final Handoff
ChangeSet assembly
Explicit checkpoint
```

这样不会让每一次 save / commit 都使整个 Work 验证失效。

---

## 9.5 语义变化产生新 Revision

只要被验证代码语义发生改变，必须形成新 RepoChange Revision：

```text
RC rev5
↓ implementation fix
RC rev6
```

旧 Verification：

```text
V81 → target RC rev5 → PASS
```

仍然是历史事实，但不能自动证明 rev6。

---

## 9.6 Review Fix 与 Conflict Fix 通常延续原 RepoChange

只要 Work Goal 和逻辑变更身份没有改变：

```text
changes requested
conflict resolution
small bug fix
```

都通常产生同一 RepoChange 的新 Revision，而不是新 RepoChange。

如果原方案被完全放弃，新的方案具有独立候选身份，则 MAY 新建 RepoChange 并将原 Candidate supersede。

---

# 第十章　ChangeSet：Work 的跨仓库逻辑变更集合

## 10.1 正式定义

> **ChangeSet 是一个 Work 为满足整体 Goal / Acceptance 而形成的、跨零到多个 Repository 的逻辑变更集合。**

典型：

```text
Work MES-2041
↓
ChangeSet CS-2041
├─ RC backend
├─ RC web
├─ RC pda
└─ RC machine
```

ChangeSet 属于 Work，不属于某个 AgentRun。

---

## 10.2 Repository-changing Work 可以从一开始拥有 Current ChangeSet

Work 创建后，若预计会修改代码，可以建立空的 Current ChangeSet：

```text
CS-2041
RepoChanges: []
```

随着调查和实现，Actual RepoChanges 逐渐加入。

这样 ChangeSet 从一开始就是：

> “这个 Work 当前正在形成的代码现实”。

---

## 10.3 Expected Scope 不等于 ChangeSet Composition

如果规划预计：

```text
backend
web
pda
```

但调查证明 Web 无需改变，则 ChangeSet 不应创建“零 Diff 的 Web RepoChange”来满足形式完整性。

实际组成：

```text
backend
pda
```

Web 通过 No Change Required Outcome 解释。

---

## 10.4 Work 默认展示一个 Current ChangeSet

领域上一个 Work MAY 有多个 ChangeSet，但普通产品体验 SHOULD 默认提供一个主要 Current ChangeSet。

多 ChangeSet 情况主要留给：

```text
competitive candidates
multiple delivery targets
hotfix / follow-up
special release composition
```

避免让普通用户手工管理大量 CS1 / CS2 / CS3。

---

# 第十一章　ChangeSet Revision、完整性与验证边界

## 11.1 ChangeSet Revision 是不可变组合快照

> **ChangeSet Revision 是一组精确 RepoChange Candidate Revisions 的不可变逻辑组合。**

例如：

```text
CS rev12

backend RC rev5
web     RC rev3
pda     RC rev6
```

一旦创建，rev12 永远表示这组组合。

Backend 变成 RC rev6 时：

```text
CS rev13

backend RC rev6
web     RC rev3
pda     RC rev6
```

MUST NOT 原地修改 rev12。

---

## 11.2 Working Changes 不自动推动 ChangeSet Revision

AgentRun 正在编辑：

```text
backend working ahead of RC rev5
```

Current ChangeSet 可以继续稳定指向：

```text
CS rev12 → backend RC rev5
```

直到新的 RepoChange Candidate Revision 被提交。

这保证 Verification 不会追着每一次文件保存不断失效。

---

## 11.3 ChangeSet 状态同样采用正交投影

建议语义：

### Composition

```text
evolving
candidate
frozen
```

### Completeness

```text
partial
complete_for_current_graph
```

### Integration

```text
not_assembled
assembling
assembled
conflicting
```

### Verification

```text
unverified
verifying
verified
needs_rework
```

### Review

```text
unreviewed
reviewing
approved
changes_requested
```

### Delivery Readiness

```text
not_ready
ready
```

MUST NOT 把这些全部压成一个无法解释的 `status=done`。

---

## 11.4 Complete ChangeSet 的判断来自 Work Graph / Acceptance

“完整”不能定义成：

> Expected Repositories 全部有 Diff。

更准确：

> **当前 Work Graph / Acceptance 中由 Repository Change 承担的所有 Required Outcomes，都有当前有效的候选成果或明确的 No Change Required 结论。**

因此 ChangeSet Composition 从属于 Work Goal，不拥有反向主权。

---

## 11.5 Verification 必须绑定明确 Revision

例如：

```text
Verification V91
Target: CS rev12
Scope: cross-repo API integration
Result: PASS
```

之后 CS rev13 出现，V91 仍然证明 rev12。

系统应评估哪些 Verification Scope 仍可复用，而不是说“MES-2041 测试通过过，所以最新代码也通过”。

---

## 11.6 Verification Validity 是 Scope-based

例如仅 Web 文案变化：

```text
Backend Unit V1      current
Web Unit V2          stale / rerun
PDA Unit V3          current
API Integration V4   impact evaluation
E2E V5               likely stale
```

ChangeSet Revision变化触发的是 Validity Evaluation，不是统一 reset。

---

# 第十二章　Repository Impact 与 No Change Required

## 12.1 Expected Impact 是 Hypothesis

Work 创建初期可能认为：

```text
Web must change
```

执行调查后发现后端保持兼容，Web 无需改动。

这不是“少完成一个 RepoChange”，而是新的有效认识。

---

## 12.2 No Change Required 是正式 Outcome

Praxis SHOULD 支持：

```text
Repository Impact Outcome
repository: mes-web
result: NO_CHANGE_REQUIRED
basis: impact analysis / evidence
```

这样以后可以回答：

> 为什么 MES-2041 当时没有改 Web？

而不是让 Web 从范围中悄悄消失。

---

## 12.3 No Change Required ≠ Empty RepoChange

禁止为了满足流程创建：

```text
RepoChange
Diff: 0 files
```

No Change 是 Work / WorkItem 的 Repository Impact 结论，不是伪造 Git 变更。

---

## 12.4 No Change 结论也可以失效

如果后续新 Evidence 证明 Web 实际受影响：

```text
NoChange Outcome
↓ invalidated by evidence
Web WorkItem / RepoChange created
```

这再次体现 Goal > Initial Plan。

---

# 第十三章　Integration 总体模型

## 13.1 Integration ≠ Git Merge

> **Integration 的目标是证明一组精确 RepoChange / ChangeSet Revision 在目标基线和目标环境下能够共同成立。**

Git Merge 只是可能使用的 Integration Strategy 之一。

---

## 13.2 两层 Integration

### Repository Integration

回答：

> 一个 RepoChange Candidate 能否与目标 Repository 基线共同成立？

检查可能包括：

```text
mergeability
build
tests
repository policy
```

### Work Integration

回答：

> 当前 ChangeSet 中多个 Repository Candidate 一起运行是否满足跨仓库契约与 Work Acceptance？

例如：

```text
backend + web + pda
API compatibility
schema consistency
E2E workflow
```

两者 MUST 分离。

---

## 13.3 Mergeability ≠ Correctness

```text
Git merge clean
```

只能说明没有 Git 检测到的结构冲突。

它不能证明：

```text
API contract consistent
DB migration safe
behavior meets acceptance
```

因此：

```text
Git Mergeability
≠ Semantic Compatibility
≠ Verification
≠ Work Acceptance
```

---

# 第十四章　Integration Environment 与跨仓库组合验证

## 14.1 正式定义

> **Integration Environment 是根据一个精确 ChangeSet Revision，将其 RepoChange Revision 与指定目标基线、运行依赖和测试配置组合起来形成的可重建验证环境。**

例如：

```text
Integration Environment IE-41
Target: CS rev12

backend @ candidate A / target main A0
web     @ candidate B / target main B0
pda     @ candidate C / target main C0
```

---

## 14.2 不直接使用 Implementation Worktree

Integration MUST NOT 默认直接拼接多个 Agent 的临时 Worktree。

原因：

- Worktree 可能 dirty；
- Run 仍在执行；
- 存在 scratch code；
- Base 不一致；
- 不能重建。

正确链路：

```text
RepoChange Candidate Revision
        ↓
ChangeSet Revision
        ↓
Integration Environment
```

---

## 14.3 Integration Environment 是暂态资源

它可以被创建、缓存、销毁、重建。

永久权威事实应是：

```text
ChangeSet Revision
Environment Definition
Integration Verification
Evidence
```

而不是某个临时目录。

---

## 14.4 Integration Result 应至少区分四类结论

### Structural

组合能否形成？

### Build

能否构建 / 启动？

### Contract

接口 / Schema / Protocol 是否兼容？

### Behavioral

跨仓库行为是否满足 Acceptance？

不同 Work Template MAY 要求不同深度。

---

## 14.5 Integration Agent 默认只读

Integration / Verification Run 应主要：

```text
assemble
test
inspect
analyze
produce evidence
```

发现实现问题后应产生：

```text
Failure Evidence
Challenge
Needs Rework
```

而不是直接跨多个 Repo 偷偷修代码。

如果确有必要修复，应创建独立 Integration Fix Assignment，并授予明确 Write Scope。

---

# 第十五章　Target Divergence、Rebase 与 Candidate Lineage

## 15.1 Target Branch 变化不篡改候选历史

假设：

```text
RC backend rev5
Base main@A
```

后来 main 变为 B。

RC rev5 仍然是有效历史 Candidate；新事实是：

```text
Target Divergence
candidate based on A
target currently B
```

---

## 15.2 Divergence 不是自动失败

系统可以评估：

```text
behind by N commits
changed files overlap
contract impact
mergeability
```

结果可能：

```text
unaffected
review_required
refresh_recommended
conflicting
unknown
```

Target Branch变化 MUST NOT 自动让所有 Verification stale。

---

## 15.3 Rebase 是 Strategy，不是生命周期

Rebase / Merge / Cherry-pick / Squash / platform-managed merge 都属于 Integration Strategy。

具体策略由：

```text
Repository Policy
Team Policy
Delivery Policy
```

决定。

Praxis Core Product Model MUST NOT 写死 “always rebase” 或 “always merge”。

---

## 15.4 Rebase 后保留 Candidate Lineage

例如：

```text
RC rev5
↓ rebase onto main B
RC rev6

derived_from: rev5
```

两个 Revision 都存在。

如果系统能够证明内容语义等价，可以帮助复用部分 Review / Verification Evidence，但 MUST 通过 Validity Evaluation，而不是简单根据 Commit Hash 或 Diff猜测。

---

## 15.5 Content Identity 与 Git Lineage Identity 分离

Rebase可能导致全部 Commit Hash 改变，但业务代码内容近似等价；也可能 Diff 看似很小却改变关键 Base 语义。

因此：

> Hash changed 不等于 everything invalid；diff same 也不等于 everything valid。

Praxis需要的是 Scope-aware Impact Evaluation。

---

# 第十六章　Integration Conflict 与冲突处理

## 16.1 Conflict 是一等 Work Fact

Git 命令返回 non-zero 不是足够的领域表达。

Praxis SHOULD 形成：

```text
Integration Conflict
Target Repository
Candidate Revision
Target Base
Conflict Scope
Files / Objects
Conflict Type
Detected At
Resolution Status
```

---

## 16.2 三类冲突

### Textual Conflict

Git可以直接检测到的同区域修改。

### Structural Conflict

例如 rename / move / schema restructure，Git可能部分处理，但仍需要理解结构。

### Semantic Conflict

Git可能完全不报错，但多仓库业务语义已经冲突，例如：

```text
Backend changes enum semantics
PDA still interprets old semantics
```

因此：

> No Git Conflict ≠ No Integration Conflict.

---

## 16.3 Conflict 按 Scope传播

Backend Repo 的 Conflict 不自动把整个 Work 标成 Blocked。

系统应判断它影响：

```text
that RepoChange
specific downstream integration
Delivery
critical path
```

只有真实阻断整体 Acceptance 时，父 Work 才需要显示整体 Blocked。

---

## 16.4 自动冲突解决必须受 Policy 约束

可自动处理的候选情形：

```text
format-only
simple generated lockfile
independent imports
unambiguous non-semantic rename
```

高风险情形必须 Assisted / Human：

```text
business rule conflict
API contract conflict
DB migration conflict
security policy conflict
```

任何自动 Conflict Resolution 后都 MUST 产生新 RepoChange Revision，并重新进行受影响 Verification。

---

## 16.5 Conflict Resolution 何时提升为 WorkItem

如果只是局部机械冲突，可以作为原 WorkItem 的一个 Fix Run。

如果冲突：

- 需要独立业务决策；
- 涉及多个 Repository；
- 会阻塞多个节点；
- 需要独立 Acceptance；
- 值得用户单独跟踪；

则 SHOULD 创建 Conflict Resolution WorkItem。

---

## 16.6 Integration Failure ≠ Merge Conflict

以下情况：

```text
merge clean
build pass
E2E fail
```

属于 Integration Verification Failure。

它应产生 Evidence → Impact Analysis → Rework / Investigation，而不是被 Git UI 统一叫做“冲突”。

---

# 第十七章　RepoChange Review 与 ChangeSet Review

## 17.1 两层 Review

### RepoChange Review

关注单仓库局部质量：

```text
correctness
architecture
style
security
SQL / migration
repository conventions
unit tests
```

### ChangeSet Review

关注 Work 整体跨仓库关系：

```text
Work Goal covered?
required clients included?
contracts aligned?
delivery order safe?
NoChange conclusions justified?
rollback / compatibility acceptable?
```

两者不能互相替代。

---

## 17.2 Simple Work 可以折叠 Review 层

如果 Work 只修改一个 Repo 且风险低：

```text
RepoChange Review ≈ ChangeSet Review
```

Praxis MAY 通过 Template/Policy 折叠，不强迫形式主义双 Review。

---

## 17.3 Review 必须绑定 Revision 与 Scope

例如：

```text
Review R81
Target: RC backend rev5
Scope: correctness + security
```

或者：

```text
Review R92
Target: CS rev12
Scope: cross-repo completeness + compatibility
```

之后代码产生 rev6 / rev13 时，旧 Review保留历史；是否仍适用由 Impact Evaluation决定。

---

## 17.4 Review Finding 是正式 Work Fact

Review输出不应只有自由文本 Comment。

至少应承认：

```text
Comment
Finding
```

Finding MAY 有：

```text
blocking
major
minor
advisory
```

阻塞 Finding 可以推动：

```text
changes requested
Challenge
Needs Rework
```

---

## 17.5 Reviewer 默认不能修改被审查实现

继承 Agent Work 规范：

```text
Review Run = read-only by default
```

需要修复时：

```text
Review Finding
↓
Fix Assignment
↓
Implementation Run
↓
New RepoChange Revision
↓
Re-review / validity evaluation
```

保持作者、Reviewer、Verifier 责任边界。

---

## 17.6 Review 独立性

高风险 Review SHOULD 支持：

```text
independent model family
independent context
read-only candidate
```

Reviewer不必默认继承实现 Agent 的全部主观叙事。

---

# 第十八章　PR / MR 与外部 Git 平台映射

## 18.1 PR/MR 不是核心领域对象

GitHub Pull Request、GitLab Merge Request、Gerrit Change 等是外部平台的协作与 Integration Representation。

Praxis 应保持：

```text
RepoChange
  ↔ external PR/MR
```

而不是：

```text
RepoChange = MR
```

---

## 18.2 为什么必须分离

因为 RepoChange 可以：

- 尚未创建 MR；
- 经过多个 MR；
- 在没有 Git hosting 的本地仓库中存在；
- MR 被关闭后仍保留历史；
- 迁移 Git 平台。

外部平台是 Adapter，不是 Work 事实的唯一所有者。

---

## 18.3 多 Repo PR/MR 仍属于一个 ChangeSet

例如：

```text
CS rev12
├─ backend MR #317
├─ web MR #88
└─ pda MR #912
```

Workbench 应从 Work / ChangeSet 聚合显示这些状态，而不是让用户在多个 Project 页面之间手工拼接现实。

---

## 18.4 外部 MR 元数据变化不必产生 ChangeSet Revision

以下变化：

```text
title changed
reviewer added
label changed
comment added
```

不会改变 RepoChange Candidate。

但如果 push 新代码：

```text
RC rev5 → rev6
```

则推动新的 ChangeSet Revision。

---

## 18.5 Merge 后需要 Integration Mapping

Squash / Rebase / Merge Commit 可能让候选 Commit 与目标分支 Commit 不同。

Praxis需要能够表示：

```text
Candidate Revision
→ Integrated Revision
```

并通过内容、Git lineage、Verification等手段确认二者关系。

本文不规定具体算法。

---

# 第十九章　Delivery 总体模型

## 19.1 Delivery 的正式定义

> **Delivery 是将一个已达到相应验收条件的 Work Outcome 推送到明确 Delivery Target，使预期接收方能够实际获得或使用该结果的过程与事实记录。**

因此：

```text
Accepted
≠ Merged
≠ Built
≠ Released
≠ Deployed
≠ Delivered
≠ Closed
```

具体 Work 是否需要这些步骤，由 Work Type / Acceptance / Delivery Policy 决定。

---

## 19.2 Delivery 绑定明确 Revision

Coding Work 的 Delivery MUST 绑定：

```text
ChangeSet Revision
```

或者其他明确、可追溯 Outcome Revision。

禁止语义：

```text
deploy latest
deliver current code
```

正确：

```text
Delivery D17
Target: Production
ChangeSet: rev12
```

---

## 19.3 Delivery Target

Delivery Target可以是：

```text
Git target branch
package registry
artifact repository
UAT environment
Production environment
mobile enterprise distribution
accepted ADR repository
external customer handoff
```

因此 Merge 是否等于 Delivery，要看 Work 的 Target，而不是 Git 操作名称。

---

## 19.4 Delivery Ready 是派生状态

概念上：

```text
DeliveryReady(CS)
=
Required Composition Complete
AND Required Integration current
AND Required Verification current
AND Required Review approved
AND No blocking conflict
AND Acceptance permits delivery
AND Delivery governance satisfied
```

用户不能通过手工拖卡绕过这些事实。

---

# 第二十章　Build、Release、Environment 与 Delivery Target

## 20.1 Merge / Build / Release / Deploy 必须分离

### Merge

候选代码进入目标 Git 历史。

### Build

源 Revision 产生可运行 / 可分发 Artifact。

### Release

一组被选择的 Artifact / Revision 被赋予稳定发布身份。

### Deploy

Release / Artifact 被应用到具体运行目标。

这些都是独立事实。

---

## 20.2 Build Artifact 是 Artifact 的一种角色

Praxis 不需要创建独立庞大的 BuildProduct 领域。

可以使用：

```text
Artifact
role: build_output
DerivedFrom: RC / CS Revision
Build Evidence: toolchain / run / checksum
```

必须能回答：

> Production 中运行的 Artifact 到底来自哪个被 Review / Verification 的代码 Revision？

---

## 20.3 Release 与 ChangeSet 分离

ChangeSet回答：

> 一个 Work 改了什么？

Release回答：

> 一个实际发布版本由哪些 Artifact / Changes 组成？

未来一个 Release可以包含多个 Work：

```text
Release 2.4.17
├─ Work A ChangeSet
├─ Work B ChangeSet
└─ Hotfix C
```

因此 ChangeSet MUST NOT 等同于 Release。

---

## 20.4 Environment 的正式定义

> **Environment 是一个具有稳定身份、运行配置和访问治理的 Work Outcome 运行 / 验证目标。**

例如：

```text
MES Integration
MES UAT
MES Production
```

Environment 不等于 IP 地址；它可以包含多个服务器、DB、Cache、Web、终端模拟器等。

---

## 20.5 Delivery Environment 与 Agent Execution Environment 分离

```text
Execution Environment
→ Agent 干活的环境

Delivery Environment
→ 产品运行 / 被验证的目标环境
```

两者 MUST NOT 因为名称相似而合并。

---

## 20.6 Delivery 可以分阶段但不固定环境名称

不同 Workspace 可能采用：

```text
DEV → TEST → UAT → PROD
TEST → Pilot → Production
Direct → Production
```

Praxis SHOULD 使用可配置 Delivery Plan / Target，不在 Core 写死固定状态机。

---

# 第二十一章　Staged Delivery、Observed State 与 Reconciliation

## 21.1 Delivery Strategy

v0.1 至少承认三类语义：

### Lockstep

多个必要 Repo / Artifact 作为一个逻辑整体交付。

### Staged

按明确顺序分阶段交付。

### Independent

各 Repository / Artifact 可以在不破坏 Work Acceptance 的情况下相对独立交付。

这是 Work Delivery Strategy，不是 Git Strategy。

---

## 21.2 Partial Delivery 是一等现实

例如：

```text
Backend ✓
Web ✓
PDA pending
Machine pending
```

系统不能只显示“50%”。它需要解释：

```text
Delivered targets
Pending targets
Compatibility condition
Current Acceptance impact
Whether this partial state is valid
```

---

## 21.3 Partial ≠ Failed

在 Staged Delivery 中：

```text
new backend + old PDA
```

如果明确满足 backward compatibility Constraint，则：

```text
Delivery = partial but valid
```

因此 Staged Delivery SHOULD 明确 Compatibility Conditions。

---

## 21.4 Desired State 与 Observed State 必须分离

生产系统不能只保存：

```text
last deployed = CS rev12
```

更可靠的模型：

```text
Desired
  backend: BA91
  web: WA81
  pda: PA71

Observed
  backend: BA91
  web: WA81
  pda: PA70
```

于是系统可以派生：

```text
Delivery Consistency = partial
```

---

## 21.5 Mixed Delivery State 必须可表达

现实可能出现：

```text
Backend from CS12
Web from CS12
PDA from CS10
```

Praxis MUST 表达真实 Observed State，而不是强迫声称“Production = CS12”。

---

## 21.6 Reconciliation

> **Reconciliation 是通过目标环境可观察事实确认实际 Side Effect 是否发生、发生到什么程度，以及 Desired 与 Observed State 是否一致的过程。**

典型：

```text
Expected backend version: 2.4.17
Observed: 2.4.16
→ effect not applied
```

或者：

```text
Deploy API timed out
Observed migration table contains M92
→ effect actually occurred
```

这是 Delivery 可靠性的核心能力。

---

## 21.7 Deploy ≠ Activate

Feature Flag、灰度、分批设备升级可能导致：

```text
Code deployed
Feature disabled
```

因此产品必须容纳：

```text
Deployment complete
Activation pending
Delivery Goal not yet satisfied
```

是否真正 Delivered，仍由 Target Reality / Acceptance决定。

---

# 第二十二章　Delivery Failure、UNKNOWN、Rollback 与 Hotfix

## 22.1 Delivery Failure 不等于 Implementation Failure

例如：

```text
ChangeSet accepted
Production deploy failed because infrastructure unavailable
```

则：

```text
Implementation Outcome = still accepted
Delivery = failed / blocked
```

不应机械把 Backend WorkItem 退回 Needs Rework，除非新 Evidence证明代码本身有问题。

---

## 22.2 Failure 必须先分类

例如 Build Failure：

```text
CI unavailable
```

是基础设施问题；

```text
compiler error
```

才可能影响 RepoChange。

统一链路仍然是：

```text
Failure Evidence
↓
Classification
↓
Impact Analysis
↓
Affected object
```

---

## 22.3 外部 Side Effect 允许 UNKNOWN

典型：

```text
deploy request sent
connection lost
```

系统不知道：

```text
succeeded
failed
partially succeeded
```

必须进入：

```text
UNKNOWN
```

MUST NOT 盲目 Retry。

---

## 22.4 Retry requires known effect state

只有在系统通过 Reconciliation 确认：

```text
effect not applied
```

或操作本身具有明确幂等语义时，才允许安全 Retry。

这一规则直接继承 Praxis Runtime 的 Side Effect Safety 原则。

---

## 22.5 不可逆 Delivery Effect 必须被审计

数据库 Migration、设备固件、生产配置等不可逆或难回滚操作必须：

```text
observable
auditable
version-bound
reconcilable
```

UNKNOWN 不得通过重复执行“试试看”。

---

## 22.6 Rollback 是新的现实改变操作

> **Rollback 是试图把某个 Delivery Target 从当前现实状态转移到一个先前已知可接受状态的新操作事实。**

例如：

```text
D17 deploy CS rev12
↓ smoke fail
R1 rollback to Release 2.4.16
```

历史必须保留：

```text
D17 occurred
R1 occurred
Current observed state = old release
```

MUST NOT 修改 D17 使其看起来从未发生。

---

## 22.7 Rollback 后必须重新验证现实

尤其多仓库环境可能：

```text
Backend rolled back
Web remains new
```

系统必须重新判断这种 Mixed State 是否安全，而不能把 `rollback command exit 0` 直接等同恢复完成。

---

## 22.8 原 Work 还是 Hotfix Work

如果 Work 尚未 Closed，且修复仍属于原 Goal / Acceptance：

```text
original Work
→ Needs Rework
→ new RepoChange Revision
→ new ChangeSet Revision
→ new Delivery
```

如果原 Work 已 Closed，新问题构成新的现实目标：

```text
New Bug / Incident / Hotfix Work
```

优先保留原 Work 的完成历史，而不是不断重写旧任务。

---

## 22.9 Closed 的条件

概念上：

```text
CanClose(Work)
=
Work Acceptance satisfied
AND Required Delivery satisfied
AND Required post-delivery verification satisfied
AND No unresolved blocking obligation
AND Governance permits closure
```

不同 Work Type 的 Required Delivery 可以为空。

例如 Research Work 可能只需要 Report Accepted。

---

# 第二十三章　MES 多仓库端到端参考场景

## 23.1 场景

业务需求：

> 报工完成前增加首检 / 质检拦截，同时兼容旧 PDA；涉及 Java Backend、Vben Admin、PDA 与机台终端，分阶段发布到生产。

Workspace：

```text
MES
├─ mes-server
├─ mes-web
├─ mes-pda
└─ mes-machine
```

Work：

```text
MES-2041 首检拦截
```

---

## 23.2 Work Graph 与 Repository Scope

初始规划：

```text
Analysis
├─ Backend Contract
├─ Backend Implementation
├─ Web
├─ PDA
├─ Machine Terminal
└─ Integration
```

Expected Repository Scope：

```text
backend
web
pda
machine
```

每个 Implementation WorkItem 获得独立 Write Scope 和 Git Worktree。

---

## 23.3 AgentRun 产生 Working State

Backend Agent：

```text
Base: mes-server main@A
Worktree: WT-BE-17
```

执行过程中产生：

```text
failed approach
scratch logging
final implementation
unit tests
```

只有最终候选通过 `Submit Candidate` 后形成：

```text
RC-BE rev1
```

Web / PDA / Machine 同理。

---

## 23.4 RepoChange 演进

Review发现 Backend error semantics 缺失：

```text
RC-BE rev1
Review Finding: blocking
↓
Fix Run
↓
RC-BE rev2
```

PDA Integration发现新字段类型错误：

```text
RC-PDA rev1
↓
Needs Rework
↓
RC-PDA rev2
```

各自历史保留。

---

## 23.5 ChangeSet 形成

某时刻：

```text
CS rev7
backend RC-BE rev2
web     RC-WEB rev1
pda     RC-PDA rev2
machine RC-MC rev1
```

Integration V31：

```text
Target: CS rev7
Result: PASS
```

随后 Machine 修改兼容逻辑：

```text
RC-MC rev2
↓
CS rev8
```

V31 仍证明 rev7；系统只重新评估受 Machine 变化影响的 Verification。

---

## 23.6 Target Divergence 与 Conflict

在准备合并 Backend 时，main 已被其他团队修改：

```text
main A → B
```

系统产生 Target Divergence。

Rebase 时发现同一业务规则发生冲突：

```text
Integration Conflict
Type: semantic / business rule
```

由于涉及质检状态语义，系统不允许低风险自动冲突解决，创建：

```text
Conflict Resolution WorkItem
```

解决后：

```text
RC-BE rev3
CS rev9
```

受影响 Review / Integration 重新验证。

---

## 23.7 Repo Review 与 ChangeSet Review

Repo Review：

```text
Backend review ✓
Web review ✓
PDA review ✓
Machine review ✓
```

ChangeSet Review 重点确认：

```text
all required terminals covered
new backend remains compatible with old PDA
quality status contract aligned
staged deployment safe
```

通过后 CS rev9 进入 Delivery candidate。

---

## 23.8 Delivery Strategy

采用 Staged Delivery：

```text
Stage 1 Backend
Stage 2 Web
Stage 3 PDA
Stage 4 Machine
```

Compatibility Constraint：

```text
new backend MUST remain compatible with old PDA/Machine until stages 3/4 complete
```

Stage 1 发布后进行：

```text
backend health
old PDA compatibility smoke
```

PASS，因此：

```text
Delivery = partial but valid
```

---

## 23.9 UNKNOWN 与 Reconciliation

Machine updater 发出部署请求后连接中断：

```text
Delivery Effect = UNKNOWN
```

Praxis禁止直接 Retry，先查询设备版本：

```text
Observed = old version
```

确认 Effect 未发生，再安全 Retry。

第二次成功后再执行设备 Smoke Verification。

---

## 23.10 Final Observed State

最终：

```text
Backend  BA91 ✓
Web      WA81 ✓
PDA      PA71 ✓ 96% rollout
Machine  MA22 ✓
```

Work Acceptance 规定：

```text
PDA rollout >= 95%
Machine critical stations upgraded
business smoke PASS
```

全部满足：

```text
Delivery succeeded
Work accepted
Work closed
```

Praxis 保留完整：

```text
Work Graph revisions
AgentRuns / Handoffs
RepoChange revisions
ChangeSet revisions
Reviews
Integration evidence
Delivery effects
Observed environment state
```

这构成可审计的真实研发闭环。

---

# 第二十四章　对象所有权与权威关系矩阵

| 对象 | 主要所有者 | 核心问题 | 不应等同 |
|---|---|---|---|
| Workspace | Product / User | 哪些长期资产共同工作？ | Folder |
| Repository | Workspace asset | 哪个稳定版本控制资产？ | Local Path / Remote URL |
| Repository Binding | Host / Environment | 当前在哪里可操作？ | Repository Identity |
| Git Worktree | Execution Environment | 本次隔离在哪里执行？ | AgentRun / Work |
| Branch | Git | Git 历史如何演进？ | Work / WorkItem |
| Commit | Git | 某次不可变 Git revision 是什么？ | RepoChange |
| Working Changes | AgentRun Environment | 当前执行现场改了什么？ | Formal Outcome |
| RepoChange | Work | 单 Repo 逻辑成果是什么？ | Diff / Commit / MR |
| RepoChange Revision | RepoChange | 哪个稳定候选被验证？ | Every Commit |
| ChangeSet | Work | 跨 Repo 整体改了什么？ | PR 集合 / Release |
| ChangeSet Revision | ChangeSet | 哪套精确 RepoChange 组合？ | Mutable “latest” |
| Integration Environment | Verification Execution | 组合在哪里被验证？ | Agent Worktree |
| Review | Governance / Verification | 哪个 Revision 哪个 Scope 被审查？ | Comment Thread |
| PR/MR | External Git platform | 外部协作/合并表示是什么？ | RepoChange authority |
| Build Artifact | Artifact | 哪个 Source Revision 构建出什么？ | ChangeSet |
| Release | Product delivery | 哪些 Artifact 构成发布版本？ | Work ChangeSet |
| Environment | Workspace / Operations | 哪个逻辑运行目标？ | IP / Agent Execution Env |
| Delivery | Work / Operations | 哪个 Outcome 到哪个 Target？ | Deploy command |
| Observed State | Environment projection | 现实现在到底是什么？ | Desired State |
| Rollback | Delivery operation | 如何恢复到已知可接受现实？ | Erasing old Delivery |

---

# 第二十五章　Multi-Repository 产品不变量

以下规则作为 v0.1 产品基线冻结。

1. **Work over Git。** Git primitives 不拥有 Work Goal / Acceptance 主权。
2. **Workspace ≠ Folder。** Workspace 是长期逻辑工作边界。
3. **Repository Identity ≠ Path ≠ Remote。**
4. **Repository Binding 表示 Repository 在具体 Host 的可操作实例。**
5. **Monorepo / Multi-repo 使用同一 Repository 模型。**
6. **Expected Repository Scope 与 Actual Impact 分离。**
7. **Repository Knowledge / Rules 属于 Workspace / Repository，而非永久 Agent 记忆。**
8. **AgentRun 通过 Execution Environment 使用 Repository Binding。**
9. **AI 写入默认不直接接管用户 Main Working Tree。**
10. **Git Worktree 是 Execution Resource，不是 Work / AgentRun 身份。**
11. **Run 启动时必须可追溯其 Base Revision。**
12. **Work ≠ Branch；AgentRun ≠ Branch；RepoChange 承载逻辑 Git 变更。**
13. **Working Changes ≠ RepoChange。**
14. **RepoChange ≠ Diff ≠ Commit ≠ PR/MR。**
15. **一个 RepoChange 可以由多个顺序 Run / Human Execution 贡献。**
16. **同一 RepoChange 默认单 active implementation writer。**
17. **Investigation scratch changes 默认不进入 RepoChange。**
18. **正式 Review / Verification 必须绑定可重建 Candidate Revision。**
19. **RepoChange Revision ≠ 每一个 Git Commit。**
20. **ChangeSet 属于 Work，并汇聚 0..N RepoChange。**
21. **ChangeSet Revision 是精确 RepoChange Revision 组合的不可变快照。**
22. **Working Changes 不自动修改当前 ChangeSet Revision。**
23. **No Change Required 是正式 Repository Impact Outcome，不创建空 RepoChange。**
24. **ChangeSet 完整性由 Work Graph / Acceptance 决定，不由 Repo 数量决定。**
25. **Integration ≠ Git Merge。**
26. **Integration Environment 从正式 Candidate 构建，不直接使用 Agent 临时工作目录。**
27. **Repository Integration 与 Work Integration 分离。**
28. **Mergeability ≠ Semantic Compatibility ≠ Acceptance。**
29. **Target Branch变化产生 Divergence，不篡改候选历史。**
30. **Rebase / Merge / Cherry-pick 是 Integration Strategy，不是 Work 生命周期。**
31. **No Git Conflict ≠ No Semantic Conflict。**
32. **Conflict 是一等 Work Fact，并按 Scope传播。**
33. **自动 Conflict Resolution 必须产生新 Candidate Revision 并重新评估 Validity。**
34. **RepoChange Review 与 ChangeSet Review 分离；Simple Work 可折叠。**
35. **Review / Verification 必须绑定明确 Revision 与 Scope。**
36. **Reviewer 默认只读；修复进入新的 Fix Assignment / Run。**
37. **PR/MR 是外部 Representation，不是 Praxis 领域 authority。**
38. **Accepted ≠ Merged ≠ Built ≠ Released ≠ Deployed ≠ Delivered ≠ Closed。**
39. **Delivery 必须绑定明确 ChangeSet / Outcome Revision 和 Delivery Target。**
40. **ChangeSet ≠ Release。** 一个 Release 可以包含多个 Work。
41. **Agent Execution Environment 与 Delivery Environment 分离。**
42. **Partial Delivery 是一等现实，且不自动等于失败。**
43. **Staged Delivery 必须明确 Compatibility Conditions。**
44. **Desired State 与 Observed State 分离。**
45. **Mixed Delivery State 必须表达真实组合，不伪造单一版本。**
46. **外部 Side Effect 允许 UNKNOWN；UNKNOWN 禁止盲目 Retry。**
47. **Delivery 必须支持 Reconciliation。**
48. **Delivery Failure ≠ Implementation Failure。**
49. **Rollback 是新的现实改变操作，不抹除旧 Delivery。**
50. **Work Closure 由 Acceptance、Required Delivery、Post-delivery obligations 共同决定。**

---

# 第二十六章　v0.1 明确不做

本规范不决定以下实现问题：

- Repository ID 生成算法；
- Remote fingerprint / same-repo detection 算法；
- Repository Binding 存储格式；
- Git Worktree 物理目录；
- Branch naming；
- Commit message policy；
- 自动 Commit / Squash 策略；
- Git CLI vs libgit2 / JGit 等实现选择；
- Semantic diff / semantic merge 算法；
- 自动 conflict predictor；
- 复杂 file lock / distributed mutex；
- RepoChange / ChangeSet 数据库 Schema；
- Synthetic Snapshot 的具体实现；
- GitHub / GitLab / Gerrit Adapter 协议；
- PR/MR 双向同步细节；
- CI/CD 平台具体 API；
- Jenkins / GitLab CI / ArgoCD 编排实现；
- Release Train / 跨 Work Release Planning；
- Kubernetes / container runtime 实现；
- Database Migration DSL；
- Feature Flag 平台；
- Production deployment engine；
- Remote Agent / Team Server；
- Fork-like Git GUI 具体交互；
- Work Tree / ChangeSet Graph 最终视觉设计。

这些应由后续 Automation、UX、System Design 和 MES Pilot 基于真实实践决定。

---

# 第二十七章　后续专题待决问题

## 27.1 Automation Model

下一份专题应正式定义：

```text
Trigger
Condition
Action
Policy
Causation / Correlation
Deduplication
Loop Guard
Retry / Backoff
Human Attention Gate
```

并围绕已经稳定的产品事实自动推进：

```text
WorkItem Became Ready
Assignment Failed
Handoff Accepted
RepoChange Candidate Created
ChangeSet Revision Changed
Verification Became Stale
Merge Conflict Detected
Delivery Became Ready
Delivery Became UNKNOWN
Work Closed
```

---

## 27.2 Workbench UX / Information Architecture

需要确定：

```text
Workspace navigation
Work Tree / Work Graph
ChangeSet view
Repository / Git view
Agent timeline
Handoff timeline
Verification matrix
Delivery timeline
My Attention
Runtime inspector
```

产品视图应从领域模型自然投影，而不是以传统 Git Repo 或 Chat 为最高导航对象。

---

## 27.3 Workbench System Design

在产品语义冻结后才决定：

```text
storage / event model
local desktop architecture
Git adapter
workspace indexing
projection engine
process supervision
remote provider boundaries
plugin APIs
```

不得为了实现便利反向合并已经冻结的领域对象。

---

## 27.4 MES Pilot PRD

应选择一个真实多仓库需求完整验证：

```text
Requirement
→ Work Graph
→ multiple AgentRuns
→ RepoChanges
→ ChangeSet
→ Integration
→ Review
→ staged Delivery
→ production verification
```

如果真实 Pilot 证明某个基线概念无法表达现实，应形成显式 Product Revision，而不是偷偷修改历史语义。

---

# 第二十八章　术语表

| 术语 | 本规范定义 |
|---|---|
| Workspace | 长期管理相关 Work、Repo、Knowledge、Policy 与 Environment 的逻辑工作空间 |
| Repository | 具有稳定产品身份、版本历史和变更边界的版本控制代码资产 |
| Repository Binding | Repository 在具体 Host / 环境中的可操作实例 |
| Repository Scope | Work / WorkItem 对 Repo 的 Expected / Read / Write 范围 |
| Execution Environment | AgentRun 使用文件、Repo、工具和资源的隔离执行边界 |
| Git Worktree | Repository Binding 为隔离执行上下文提供的 Git 工作副本 |
| Working Changes | AgentRun 当前执行现场中的临时修改 |
| RepoChange | Work 在单一 Repository 中形成的逻辑代码变更成果 |
| RepoChange Revision | 可重建、可 Review / Verification 的稳定 RepoChange Candidate |
| ChangeSet | Work 跨零到多个 Repository 的逻辑变更集合 |
| ChangeSet Revision | 精确 RepoChange Revision 集合的不可变组合快照 |
| Repository Impact | Work 对某 Repository 的实际影响结论 |
| No Change Required | 有 Evidence 支持的“不需要修改该 Repository”正式 Outcome |
| Integration | 证明候选与目标基线、跨仓库组合能够共同成立的工作过程 |
| Integration Environment | 根据明确 ChangeSet Revision 构建的组合验证环境 |
| Target Divergence | Candidate Base 与当前目标分支现实之间的分叉事实 |
| Candidate Lineage | RepoChange Candidate Revision 之间的演进 / 派生关系 |
| Integration Conflict | 候选与目标基线或跨仓库语义无法直接共同成立的正式工作事实 |
| RepoChange Review | 对单 Repository 逻辑变更的局部审查 |
| ChangeSet Review | 对 Work 整体跨仓库成果完整性与一致性的审查 |
| PR/MR Mapping | RepoChange 与外部 Git 协作对象之间的映射 |
| Build Artifact | 从明确 Source Revision 构建出的可运行 / 可分发 Artifact |
| Release | 对一组待发布 Artifact / Revision 建立稳定发布身份的逻辑集合 |
| Environment | 具有稳定身份、配置和治理的产品运行 / 验证目标 |
| Delivery Target | Work Outcome 需要实际到达的目标现实 |
| Delivery | 将明确 Outcome Revision 推向 Delivery Target 的过程和事实 |
| Desired State | Delivery 希望目标环境达到的版本 / Artifact 组合 |
| Observed State | 通过现实观察得到的目标环境实际版本 / Artifact 组合 |
| Reconciliation | 对账 Desired 与 Observed，确认 Side Effect 是否真实发生 |
| Mixed Delivery State | 一个目标环境中不同组件来自不同 ChangeSet / Release 的现实组合 |
| Rollback | 将目标现实转移到先前已知可接受状态的新操作事实 |

# 结语

Praxis 的多仓库能力不应该被理解为“能同时打开几个 Git Repo”。真正的产品问题是：

```text
业务 Work → 多 Repository → Agent / Human 分工 → RepoChange → ChangeSet Revision → Integration / Review → 真实运行环境
```

因此，Praxis 应始终保持以下产品层级：

```text
Work → ChangeSet → RepoChange → Git Primitives
```

并保持以下交付链：

```text
Working Changes → RepoChange Candidate Revision → ChangeSet Revision → Integration / Review / Verification → Delivery → Observed State / Reconciliation → Post-delivery Verification → Work Acceptance / Closure
```

本规范的核心结论是：

> **Git 是 Praxis 的生产工具，而不是最高产品对象；RepoChange 把 Git 变化提升为 Work 成果，ChangeSet 把多仓库成果提升为可验证整体，Delivery 再把这个整体推入真实世界。**
