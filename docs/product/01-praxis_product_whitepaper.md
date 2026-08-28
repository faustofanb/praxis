# Praxis 产品白皮书

## 从可恢复 Agent Runtime 到面向真实研发工作的智能体工作台

**版本：Product Vision Baseline v0.1**  
**日期：2026-08-28**  
**文档性质：产品愿景与产品边界白皮书**

> 本文定义 Praxis 的长期产品方向、目标用户、核心价值、产品层次、能力边界与演进路线。它不是详细 PRD，也不是系统实现文档。底层 Runtime 的技术与工程约束继续由现有 Praxis Harness 技术白皮书、系统设计与开发基线负责。

---

# 目录

1. 产品背景：Agent 能力提升以后，新的瓶颈是什么
2. Praxis 的产品命题
3. 目标用户与优先场景
4. 产品核心模型：从 Session 转向 Work Graph
5. 产品能力版图
6. GUI 产品形态
7. Execution-derived Work Management
8. 可扩展产品生态
9. 信任、责任与生产安全
10. 产品分层
11. 产品路线图
12. 与现有产品的关系
13. Praxis 的长期差异化
14. 产品成功指标
15. 主要产品风险
16. MES Pilot：产品验证标准
17. 白皮书边界：现在不决定什么
18. 最终产品原则
19. 参考资料

---

# 摘要

软件开发正在从“人直接操作代码工具”进入“人管理多个能够独立完成工程任务的 Agent”阶段。模型能力的提升正在把瓶颈从单次代码生成，转移到更高层的问题：**怎样组织需求、上下文、代码仓库、多个 Agent、Git 分支、验证、交付和长期工作状态，使 Agent 真正进入生产研发流程，而不是停留在一个个孤立的聊天窗口里。**

2026 年的主流产品已经明显表现出这一趋势。OpenAI 将 Codex App 定位为多 Agent 的 command center，并将 worktree、Skills 和 Automations 作为核心能力；Cursor 3 强调 unified workspace、multi-repo、local/cloud agent handoff 和 async subagents；ZCode 将 workspace、task、Git、长任务和 automation 放进同一桌面工作流；GitKraken 则继续强化 multi-repo workspace、Git graph 与 worktree；Linear 开始把 Agent 直接纳入 issue delegation，并明确强调“人仍然拥有最终责任”。[1][2][3][4][5]

Praxis 的机会不在于再做一个“更会写代码的聊天框”，也不在于简单复制 IDE、Git Client 或 Issue Tracker，而在于把此前已经设计的**可恢复、证据驱动、可审计 Agent Runtime**向上扩展为一个真正围绕“工作”组织的软件研发平台。

Praxis 的长期产品形态因此被定义为三层：

1. **Praxis Runtime**：可靠执行底座。负责 Session、Event、Agent Loop、Tool Runtime、Capability、Verification、Recovery 与 Evidence；
2. **Praxis Workbench**：面向个人与高级研发者的桌面工作台。负责 Workspace、Work Tree、Multi-repo、Git、Agent Runs、ChangeSet、Automation 和 GUI；
3. **Praxis Team / Server**：未来团队级协作层。负责共享 Work Graph、远程执行、权限、组织策略、团队 Agent、审计与企业集成。

其中最重要的产品抽象不是 Chat，而是：

```text
Workspace
   ↓
Work / Requirement
   ↓
Work Graph / Work Tree
   ↓
Work Item
   ↓
Agent Run / Session
   ↓
ChangeSet
   ↓
Verification
   ↓
Delivery
```

Praxis 希望把传统“需求管理—开发—Git—Agent—测试—交付”之间的断裂，压缩成一条由真实执行事实驱动的工作链路。

最终目标不是让用户管理更多 Agent，而是：

> **让用户只管理目标、判断、优先级和关键决策，其余工程工作尽可能由可观察、可恢复、可验证的 Agent 系统持续推进。**

---

# 第一章　产品背景：Agent 能力提升以后，新的瓶颈是什么

## 1.1 从代码补全到长周期 Agent

早期 AI 编程产品主要围绕：

```text
当前文件
→ 补全
→ Chat
→ 少量编辑
```

随后演变为：

```text
Repository
→ Agent
→ Terminal
→ Tool Calls
→ Multi-file Change
```

而当前正在进入第三阶段：

```text
多个项目 / 多个仓库
→ 多个长周期 Agent
→ 并行工作
→ Worktree / Cloud Environment
→ Review / Verification
→ Automation
```

OpenAI 在 2026 年发布 Codex App 时明确指出，随着 Agent 能够承担小时、天甚至周级任务，核心挑战已经从“Agent 能不能做”转向“人怎样同时指导、监督和协作多个 Agent”；Cursor 3 也把工程师需要在多个 Agent 对话、终端和工具之间不断切换视为新的主要问题。[1][2]

因此下一代 AI 开发产品的核心竞争，不只是模型本身，而是：

> **Work Management + Agent Orchestration + Context + Git + Verification + Automation + Trust。**

---

## 1.2 Issue Tracker、IDE、Git Client 与 Agent Console 正在相互靠近

传统工具边界原本很清楚：

```text
Jira / Linear     → 管需求
IDE               → 写代码
Git Client        → 管版本
CI                → 验证
Chat              → 沟通
Agent             → 辅助编码
```

Agent 正在改变这些边界。

Linear 已允许 issue 被 delegate 给 Agent，而人类 assignee 继续保留最终责任；GitHub 允许 coding agents 从 issue、Agents tab、PR 和 IDE 中接受任务并产出 PR；ZCode 把 Task、Workspace、Agent、Git 和 Automation 放到同一个桌面产品；GitKraken 的 Workspace 与 Worktree 则体现出多仓库和并行 Agent 对 Git 基础设施的新要求。[3][4][5][6]

这意味着未来产品不再只是把这些工具并排放进一个窗口，而是需要形成一个新的统一工作对象。

Praxis 选择的统一对象是：

**Work**

而不是：

**Conversation**

---

# 第二章　Praxis 的产品命题

## 2.1 一句话定义

> **Praxis 是一个面向复杂真实研发工作的 Agent-native Workbench：它把需求、工作树、多仓库、Git、Agent、验证和自动化组织成一条可恢复、可审计的执行链。**

英文可以暂定：

> **Praxis — an evidence-driven workbench for agentic software engineering.**

这不是最终品牌文案，但准确表达当前产品方向。

---

## 2.2 Praxis 不是什么

Praxis 不以成为下面任何一种产品的简单替代为目标：

- 不只是 Coding Chat；
- 不只是 IDE；
- 不只是 Git Client；
- 不只是 Jira / Linear；
- 不只是 Agent Framework；
- 不只是 Workflow Engine；
- 不只是 Multi-Agent Dashboard。

这些能力都会出现在 Praxis 中，但它们围绕一个更高层目标组织：

> **把一个真实工作需求持续推进到经过验证、可以交付的结果。**

---

## 2.3 产品北极星

Praxis 的 North Star（北极星）不是“生成多少代码”，而是：

> **一个真实工作项，从用户表达目标，到跨仓库实施、验证、Review 和交付，需要多少人工协调成本与多长闭环时间。**

因此 Praxis 优化的是：

```text
Intent-to-Verified-Delivery
```

即：

> **从意图到经过验证的交付结果。**

---

# 第三章　目标用户与优先场景

## 3.1 第一目标用户：复杂业务系统研发人员

Praxis 第一阶段不以所有软件开发者为目标，而优先服务：

- 同时维护多个仓库；
- 需求经常跨前端、后端、终端、数据库或基础设施；
- 需要频繁在需求、代码、Git、测试、终端之间切换；
- 已经使用 AI 编码，但苦于 Session 碎片化和上下文流失；
- 需要自己承担最终工程责任；
- 对生产安全、恢复、验证有明确要求。

典型角色：

- Tech Lead / 架构师；
- 全栈工程师；
- 复杂业务系统核心开发；
- 小型团队技术负责人；
- DevOps / 平台工程师；
- 负责复杂跨模块 Bug 与生产事件的高级工程师。

---

## 3.2 核心验证场景：MES 多仓库研发

Praxis 第一批最有价值的真实验证场景，可以是一个典型 MES 系统：

```text
MES Workspace
│
├─ Java Backend
├─ Vben5 Web
├─ UniApp PDA
├─ UniApp Machine Terminal
├─ UniApp Tablet
└─ Other Terminal Repositories
```

一个“工单完工增加质检拦截”的需求可能同时影响：

```text
Backend
Web
PDA
部分终端
Integration Test
Release
```

传统工作方式需要人工：

- 阅读需求；
- 判断影响面；
- 分别切仓库；
- 建分支；
- 反复给不同 Agent 补上下文；
- 联调；
- 追踪各仓库改动；
- 汇总提交和验收状态。

Praxis 的目标是把它变成一个统一 Work：

```text
Requirement
→ Impact Analysis
→ Work Tree
→ Multi-repo Agent Execution
→ Integration Challenge / Rework
→ Cross-repo ChangeSet
→ Verification
→ Delivery
```

这将作为 Praxis Workbench 的第一类“杀手场景”。

---

# 第四章　产品核心模型：从 Session 转向 Work Graph

## 4.1 Workspace

Workspace 是用户对一个真实产品、系统或长期工作环境的组织单位。

Workspace 可以包含：

- 多个 Git Repository；
- 项目说明与领域知识；
- Agent Rules / Skills；
- Issue / Requirement 来源；
- CI / Test / Database / Browser 等 Integration；
- Automation；
- Workspace Policy。

关键原则：

> **Workspace ≠ Repository。**

多仓库必须是一等能力，而不是后期补丁。

这与 Cursor 2026 年引入 multi-root workspace、GitKraken 长期维护 multi-repo Workspace 的方向一致。[2][4]

---

## 4.2 Work

Work 是产品层最高的执行对象。

一个 Work 可以来自：

- Requirement；
- Feature；
- Bug；
- Incident；
- Refactor；
- Migration；
- Research；
- Release；
- Operations Task。

Work 保存用户真正关心的长期稳定信息：

```text
Goal
Business Context
Acceptance Criteria
Constraints
Priority
Affected Areas
Status
Delivery Target
```

它不是一次模型会话。

---

## 4.3 Work Tree / Work Graph

复杂 Work 会被展开为 Work Items。

例如：

```text
MES-1842 完工质检拦截
│
├─ Requirement Analysis
├─ Backend
│   ├─ Domain Change
│   ├─ API
│   └─ Test
├─ Web
├─ PDA
├─ Integration
├─ Regression
└─ Delivery
```

简单场景可以表现为树。

复杂场景本质是图：

```text
depends_on
blocks
produces
validates
challenges
supersedes
```

因此产品概念上统一称为 **Work Graph（工作图）**，GUI 可以根据场景显示 Tree、Board、Timeline 或 Dependency Graph。

---

## 4.4 Work Item

Work Item 是最小的可委派工作单元。

一个 Work Item 可以：

- 由人执行；
- 由一个 Agent 执行；
- 多次交给不同 Agent；
- 因 Challenge 回流；
- 等待其他 Work Item；
- 产生一个或多个 ChangeSet。

Work Item 是“工作责任”的稳定对象。

---

## 4.5 Agent Run 与 Session

Session 不再是产品顶层导航对象，而是 Work Item 下的执行历史。

关系为：

```text
Work
  ↓
Work Item
  ↓
Agent Run 0..N
  ↓
Session / Events
```

一个 Work Item 可能经历：

- 实现 Agent；
- 第二模型重新尝试；
- Reviewer Agent；
- 修复 Review 的 Agent；
- Integration Agent 回流。

这样既保留 Runtime 的完整 Event History，又不会让用户的工作系统退化成“几百个 Chat Session”。

---

## 4.6 ChangeSet

ChangeSet 表示一个 Work 在现实代码世界中产生的变更集合。

一个 ChangeSet 可以跨多个 Repository：

```text
MES-1842 ChangeSet

backend
  branch: feat/MES-1842
  commits: 3

web
  branch: feat/MES-1842
  commits: 2

pda
  branch: feat/MES-1842
  commits: 1
```

用户 Review 的核心对象应逐渐从“某个 Agent 说了什么”转向：

> **这个 Work 到底改变了哪些代码、为什么改变、怎样验证。**

---

# 第五章　产品能力版图

Praxis Workbench 的产品能力不应一次全部实现，但长期版图应该明确。

## 5.1 Work Management

核心能力：

- Work Inbox；
- Work Tree / Graph；
- Priority；
- Dependency；
- Blocked / Ready / Running / Verify / Done；
- Work Template；
- Requirement / Bug / Incident / Migration 类型；
- Agent delegation；
- Human ownership；
- Work history。

重要理念：

> **状态尽量由真实执行事实推导，而不是要求用户手工维护。**

这与 Linear 当前 Agent delegation 中“Agent 执行、Human 保持 ownership”的模式具有一致方向，但 Praxis 更进一步希望让 Git、Verification 和 Runtime Events 直接成为 Work 状态来源。[5]

---

## 5.2 Multi-repo Workspace

长期能力：

- Workspace 绑定 N 个 repo；
- Repository role：backend / web / terminal / shared / infra；
- repo health / branch / dirty status；
- cross-repo search；
- requirement impact analysis；
- cross-repo ChangeSet；
- repository-specific Rules / Skills；
- bulk fetch/pull/status；
- multi-repo release context。

多仓库不只是 UI 分组，而是 Work Graph 的核心维度。

---

## 5.3 Git Workspace

Praxis 不应该重新实现 Git，而应该把 Git 提升为产品的一等可视层。

目标体验参考成熟 Git Client：

- Working Tree；
- Staging；
- Diff；
- Commit；
- Branch Graph；
- File History；
- Merge / Rebase / Cherry-pick；
- Worktree；
- Conflict Resolution；
- PR / MR Context。

GitKraken 已证明 multi-repo Workspace 和 visual worktree 管理在复杂研发场景中具有高价值；2026 年其 Worktree 文档还直接把 worktree 与 coding agent sessions 联系起来。[4]

Praxis 的差异在于：

> 每个 Git Change 都能回溯到 Work、Agent Run、Verification 和 Evidence。

---

## 5.4 Multi-Agent Work Execution

Praxis 的 Multi-Agent 不以“多个角色辩论”为核心，而以工作对象分工为核心。

例如：

```text
Backend Work Item
→ Backend Agent

Web Work Item
→ Frontend Agent

PDA Work Item
→ UniApp Agent

Integration Work Item
→ Integration Agent
```

Agent 之间通过 Work Graph、Handoff、ChangeSet 和 Event 协作，而不是共享无限聊天上下文。

Codex App、Cursor 和 GitHub 都已经把多个 Agent 并行、worktree 隔离和任务委派视为重要产品能力。[1][2][6]

Praxis 的原则是：

> **Practice diversity > opinion diversity。**

即：多个 Agent 的价值首先来自接触不同代码仓库、测试环境和专业对象。

---

## 5.5 Agent Handoff

跨 Agent 流转不能简单复制全部 Conversation。

Handoff 应形成结构化交付：

```text
Goal
Completed Work
Relevant Evidence
Changed Repositories
API / Contract
Verification
Open Risks
Blocked Items
Recommended Next Action
```

下一个 Agent 读取必要状态，而不是继承前一个 Agent 所有语言历史。

这将成为 Work Graph 能够长期运行的关键能力。

---

## 5.6 Verification & Review

Praxis 的 Verification 不应隐藏在 Agent 最后一条消息里。

产品需要显式展示：

- Unit Test；
- Integration Test；
- Build；
- Lint；
- Runtime Check；
- Security Check；
- Human Review；
- Agent Review；
- Acceptance Criteria。

用户最终看到的不是：

> “Agent 说完成了。”

而是：

```text
Implementation: Complete
Verification: 18 / 21 PASS
Blocked: 2
Human Approval: Required
```

---

## 5.7 Automation

Automation 是 Praxis 从“Agent 工具”进入“工作流平台”的关键能力。

Praxis 应同时支持：

### Scheduled Automation

例如：

- 每天汇总多个仓库变化；
- 每周生成 Release Note；
- 每月依赖风险扫描。

ZCode 和 Codex 已经将定时/背景 Automation 作为产品方向。[1][3]

### Event-driven Automation

更重要的是由工作状态驱动：

```text
Work.Ready
→ create worktree
→ allocate agent

Backend.Verified
→ unblock Web / PDA

AllChildren.Verified
→ start Integration

CI.Failed
→ open Investigation Work Item

Challenge.Accepted
→ re-open upstream Work Item
```

Praxis 的优势在于已经有 Event-driven Runtime 基础，因此 Automation 可以建立在真实状态转换之上，而不是额外维护一套 Workflow 假状态。

---

## 5.8 Integrations

长期 Integration 类型：

### Development

- GitHub；
- GitLab；
- Gitea；
- Azure DevOps；
- CI/CD；
- Artifact Registry。

### Work / Requirement

- Linear；
- Jira；
- 禅道；
- 飞书项目；
- GitHub Issues / GitLab Issues。

### Engineering Environment

- Database；
- Browser；
- Logs；
- APM；
- Kubernetes；
- SSH / Remote Host；
- Internal API。

第一阶段原则：

> Praxis 不强迫公司马上替换现有需求系统，而是先把外部 Requirement 导入 Work Graph，再把执行结果同步回去。

---

# 第六章　GUI 产品形态

## 6.1 GUI 是长期产品的必要组成

CLI 非常适合 Runtime 开发、自动化和高级用户，但当产品开始承担：

- Work Graph；
- 多仓库；
- 多 Agent；
- Git Graph；
- Diff；
- Verification；
- Automation；

纯终端会逐渐成为信息瓶颈。

因此 Praxis Workbench 的长期形态必须是 Desktop GUI。

GUI 不是为了“更漂亮”，而是为了支持：

> **同时观察多个长期状态，并在高层工作视图与底层代码/事件之间快速钻取。**

---

## 6.2 设计原则：Progressive Disclosure

默认界面不应该展示全部 Agent 内部状态。

用户首先看到：

```text
Work
Status
Repositories
Agent Progress
Changes
Verification
```

需要时才展开：

```text
Observation
Hypothesis
Challenge
Event
Capability
Tool Trace
```

即：

> **默认看工作，必要时看认识，出现问题时看 Runtime。**

---

## 6.3 一级产品视图

长期可以收束成六个一级页面：

### Work

默认主页。

- Work Tree；
- Work Graph；
- Requirement；
- Status；
- Priority；
- Agent Progress。

### Code

- Workspace file tree；
- Search；
- Diff-oriented code view；
- External IDE integration。

Praxis 第一阶段不必重新制造完整 VS Code；可以优先做好 Review 和跳转外部 IDE。

### Git

- Repo selector；
- Working Tree；
- Diff；
- Commit Graph；
- Branch；
- Worktree；
- PR/MR。

### Agents

- Running；
- Waiting；
- Blocked；
- Failed；
- Completed；
- Agent ownership / work item；
- cost / duration / tool state。

### Automation

- Trigger；
- Schedule；
- Condition；
- Action；
- Execution history；
- Approval requirements。

### Runtime

高级调试面板：

- Events；
- Observations；
- Hypotheses；
- Plans；
- Challenges；
- UNKNOWN；
- Capability；
- Replay。

---

## 6.4 GUI 概念布局

```text
┌────────────────────────────────────────────────────────────────┐
│ Praxis | Workspace | Search | + Work | Agents | Automation    │
├────────────────┬─────────────────────────┬─────────────────────┤
│ WORK / REPOS   │          WORK           │      CONTEXT        │
│                │                         │                     │
│ Work Tree      │ Goal                    │ Repositories        │
│ ├ MES-1842 ◉   │ Plan / Progress         │ Agents              │
│ ├ MES-1857 ○   │                         │ Verification        │
│ └ Incident ... │ Agent activity          │ ChangeSet           │
│                │                         │                     │
│ Repositories   │ Diff / Work detail      │ Risks / Challenges  │
│ ├ backend      │                         │                     │
│ ├ web          │                         │                     │
│ └ pda          │                         │                     │
├────────────────┴─────────────────────────┴─────────────────────┤
│ Terminal | Git | Tests | Problems | Events | Agent Logs       │
└────────────────────────────────────────────────────────────────┘
```

它只是产品信息架构示意，不是最终 UI 规范。

---

# 第七章　Execution-derived Work Management

## 7.1 为什么传统需求管理在 Agent 时代会变得更重

传统 Issue Tracker 依靠人手工更新：

```text
Todo
→ In Progress
→ Review
→ Test
→ Done
```

Agent 开始承担执行以后，如果人还需要手工维护同样状态，就会形成新的管理负担。

Linear 在 2026 年提出“issue tracking is dead”，核心判断之一正是 Agent 会压缩 planning、implementation 和 review 之间的传统流程，而人的工作更集中于 intent、judgment 和 taste。[7]

Praxis 不必完全接受“Issue Tracking 会消失”这一判断，但认同其中一个产品方向：

> **状态管理应该越来越来自执行事实，而不是人为填表。**

---

## 7.2 Praxis 的状态来源

例如：

```text
Work Item = Running
```

不是用户手工拖卡片产生，而可以来自：

```text
Agent Run Started
```

```text
Work Item = Blocked
```

可以来自：

```text
Dependency unresolved
Capability denied
UNKNOWN external effect
Challenge pending
```

```text
Work Item = Verified
```

来自：

```text
Required verification PASS
```

因此 Work Management 是 Runtime Events 的 Projection，而不是另一套事实系统。

这将是 Praxis 很重要的产品差异。

---

# 第八章　可扩展产品生态

## 8.1 扩展的目标

Praxis 不可能内建每家公司的业务流程。

真正进入生产环境必须允许用户定义：

- 私有仓库规则；
- 内部开发流程；
- 内部 API；
- 特殊测试；
- MES 领域工具；
- 数据库访问；
- 发布流程；
- 特殊 Agent。

所以扩展能力不是附加功能，而是 Workbench 成为真实工作平台的必要条件。

---

## 8.2 扩展类型

### Model Provider

可替换模型供应商。

### Tool / Connector

连接：

- 文件；
- Shell；
- DB；
- Browser；
- HTTP；
- CI；
- 公司内部系统。

### Skill

团队工程方法、领域知识、固定任务流程。

### Agent Profile

例如：

- Java Backend；
- Vben Frontend；
- UniApp；
- Database；
- Reviewer；
- Integration。

GitHub 当前已经用 custom agent profile 把项目专属工具、指令和 agent specialization 产品化。[6]

### Work Template

Feature / Bug / Incident / Migration 的标准 Work Graph。

### Automation

Trigger / Condition / Action。

### Integration

外部 Requirement、Git Host、CI、Notification、Observability。

---

## 8.3 扩展不是无限权限

任何扩展必须遵守 Praxis Runtime 的 Capability 与安全模型。

插件可以增加能力，但不能绕过：

- Audit；
- Capability；
- Tool lifecycle；
- Verification；
- Secret policy。

这是 Praxis 与“脚本拼起来就能跑”的自动化平台之间的重要边界。

---

# 第九章　信任、责任与生产安全

## 9.1 Human Ownership

Praxis 的长期自动化能力越强，越不能模糊最终责任。

产品原则：

> **Agent 可以承担执行责任，但人的 Goal Ownership 与最终 accountability 不自动消失。**

Linear 当前明确把 agent delegation 与 human assignee 分开，也是相同思路。[5]

---

## 9.2 可观察，而不是盲信

产品需要始终回答：

```text
现在谁在做什么？
为什么？
改了什么？
测试到了什么？
阻塞在哪里？
哪些结果不确定？
谁批准了高风险操作？
```

用户应该能够从高层状态向下钻取，而不需要相信 Agent 的自然语言总结。

---

## 9.3 生产环境默认保守

未来即使 Praxis 能操作生产环境，也应该遵循：

```text
Read / Observe
<
Reversible Change
<
Staged Change
<
Production Change
```

权限、验证与人工确认逐级增强。

产品默认不应鼓励“让一个 Agent 无限权限跑一整晚”。

---

# 第十章　产品分层

## 10.1 Praxis Runtime

定位：

> **Agent execution kernel。**

负责：

- Session；
- Event；
- Agent Loop；
- Context；
- Tool Runtime；
- Capability；
- Verification；
- Recovery；
- Evidence / Hypothesis / Challenge。

Runtime 不知道：

- MES；
- Jira；
- GUI；
- Work Tree；
- Git Graph 产品体验。

这是稳定底座。

---

## 10.2 Praxis Workbench

定位：

> **Personal Agentic Engineering Workbench。**

负责：

- Workspace；
- Work / Requirement；
- Work Graph；
- Multi-repo；
- Git；
- Agent Runs；
- ChangeSet；
- Automation；
- GUI；
- Integrations。

它调用 Runtime，而不是重新实现 Runtime。

---

## 10.3 Praxis Team / Server

未来定位：

> **Shared Agentic Engineering Platform。**

可能包含：

- Shared Workspace；
- Team Work Graph；
- Remote Agent Environments；
- RBAC；
- Policy Server；
- Shared Automation；
- Organization Skills；
- Secrets / Audit；
- Team Analytics；
- Self-host / Enterprise Deployment。

这一层不应在个人 Workbench 被验证之前提前建设。

---

# 第十一章　产品路线图

产品路线与 Runtime M0-M8 工程路线是两套不同层级。

## Phase A — Praxis Runtime v1

目标：

> Developer-grade reliable Agent Runtime。

包括：

- CLI；
- Session/Event；
- Model/Tool；
- Capability；
- Recovery；
- Verification；
- basic Epistemic Runtime；
- Operator TUI；
- Test / Eval。

这一阶段完成以后，Praxis 已可作为可靠的高级 Coding Agent Runtime 使用。

---

## Phase B — Praxis Desktop / Workbench Alpha

核心目标：

> 从 Session 产品转向 Work 产品。

新增：

- Desktop GUI；
- Workspace；
- Multi-repo；
- Work Inbox；
- Work Tree；
- Work Item ↔ Session；
- Git Overview；
- Agent Dashboard；
- Cross-repo ChangeSet。

重点验证：

> 是否能成为日常开发主入口，而不是附加 Dashboard。

---

## Phase C — Praxis Workbench v2

目标：

> 真正完成跨 Agent、跨仓库工作闭环。

新增：

- Work Graph；
- Git Worktree Agent Isolation；
- Agent Handoff；
- Cross-agent Challenge；
- Integration Agent；
- Work Templates；
- Event-driven Automation；
- Requirement system integration；
- GitHub/GitLab/Gitea integration。

这是进入真实 MES 日常研发流程的关键版本。

---

## Phase D — Production Engineering Platform

目标：

> 从 Coding Workbench 扩展到持续工程自动化。

新增候选：

- Remote Agent；
- CI/CD Automation；
- Incident workflow；
- Logs/APM；
- Database / Ops Agent；
- Scheduled Work；
- Background Agent；
- Team Handoff；
- Release orchestration。

---

## Phase E — Team / Enterprise

只有在前面阶段真实证明价值后，才考虑：

- Multi-user；
- Shared server；
- Enterprise RBAC；
- Central Policy；
- SSO；
- Org-level Skills / Agents；
- Remote fleet；
- Compliance / Audit；
- On-premise deployment。

---

# 第十二章　与现有产品的关系

## 12.1 ZCode

ZCode 当前已经把 Workspace、Task、Agent、Git branch context、Review 和 Automation 收束到桌面工作台，并强调长任务连续推进。[3]

Praxis 应学习：

- 易用 GUI；
- 长任务连续性；
- Project/Task 导航；
- Automation 入口；
- 运行过程不要求用户一直盯终端。

Praxis 的目标差异：

- Work Graph 不只是一组 Task Session；
- Multi-repo Work 是一等对象；
- Runtime Event/Recovery/UNKNOWN 更强；
- Work 状态由执行事实产生；
- Cross-agent Handoff / ChangeSet / Verification 更系统化。

---

## 12.2 OpenAI Codex

Codex App 已把多个并行 Agent、worktree、Skills 和 Automations 作为核心产品形态。[1]

Praxis 应学习：

- Agent command center；
- worktree isolation；
- Session/Project continuity；
- Skills；
- Background Automation。

Praxis 不应试图在模型能力本身与 Codex 正面竞争，而应把重点放在：

> **多仓库 Work Graph、跨 Agent 需求流转、可恢复 Runtime 和生产工作管理。**

---

## 12.3 Cursor

Cursor 3 正在走向 unified agent workspace，并在 2026 年加入 multi-root workspace、async subagents 和 improved worktrees，明显瞄准跨 repo 与并行 Agent。[2]

Praxis 应学习：

- 优秀 GUI；
- 高层 Agent 视图与 IDE 的自由切换；
- local / cloud agent handoff；
- Multi-root workspace。

Praxis 不以编辑器体验为第一竞争面，而应优先解决：

> **Work Management + Execution Graph。**

---

## 12.4 GitKraken

GitKraken 在多仓库 Workspace、Git Graph、Worktree 与 Agent Session 基础设施方面成熟。[4]

Praxis 应避免重复造低层 Git 功能的错误实现，产品体验可以学习 GitKraken，但 Git 状态应与 Work/Agent/Verification 深度关联。

---

## 12.5 Linear / GitHub

Linear 正在把 Agent 作为 workspace participant，并保留 human ownership；GitHub 则将 Agent 直接连接 Issue、PR、IDE 和 custom agent profile。[5][6]

Praxis 的长期方向不是立刻替代它们，而是：

```text
External Requirement System
          ↕
      Praxis Work Graph
          ↓
     Agent Execution
          ↓
        Git / CI
          ↓
External System Status Sync
```

先成为执行中枢，再决定是否需要承担更多需求管理职责。

---

# 第十三章　Praxis 的长期差异化

在模型与基础 Agent 能力逐渐商品化以后，Praxis 的差异不能建立在“某个模型更聪明”上。

长期最值得积累的产品资产可能是：

## 13.1 Recoverable Agent Runtime

Agent 崩溃、重启、未知副作用、Replay、Capability、Verification 的可靠性。

---

## 13.2 Execution-derived Work Graph

Work 状态与依赖不是手工维护，而由真实 Agent / Git / Verification Events 驱动。

---

## 13.3 Cross-repo Change Intelligence

围绕一个 Work 聚合多个仓库变更、依赖、验证与交付。

---

## 13.4 Structured Agent Handoff

Agent 之间传递工作事实，而不是无限 Conversation。

---

## 13.5 Trust & Inspectability

用户可以从 Work 高层一路下钻到 Change、Test、Agent Event 和 Evidence。

---

## 13.6 Local-first Extensibility

能够真正适配公司的私有仓库、内部 API、MES 领域流程和本地网络，而不要求所有业务上下文上传到某个固定云平台。

---

# 第十四章　产品成功指标

Praxis 不应把以下指标作为第一成功标准：

- 生成 LOC；
- Agent 数量；
- Token 数量；
- Session 数量；
- 自动化数量。

更有意义的指标：

## 14.1 Delivery

- Requirement → Verified Change 的周期；
- Work 首次通过 Acceptance 的比例；
- 跨 repo 需求平均协调时间。

## 14.2 Human Burden

- 人工补上下文次数；
- 人工同步状态次数；
- 人工切换 repo / branch / tool 的次数；
- 人工监督 Agent 的时间。

## 14.3 Agent Quality

- Rework rounds；
- invalid retries；
- plan invalidation 后恢复时间；
- Challenge 捕获真实错误比例；
- Human Review 发现的 P0/P1 数。

## 14.4 Reliability

- Session recovery success；
- duplicate side-effect incidents；
- UNKNOWN reconciliation rate；
- capability violations；
- Work status 与实际 Git/Test 状态不一致率。

真正的产品目标是：

> **减少工作流摩擦，而不是制造一个需要人持续照顾的 Agent 农场。**

---

# 第十五章　主要产品风险

## 15.1 GUI 膨胀成“大而全 IDE”

风险：为了 Code、Git、Terminal、Requirement 全部自己做，产品失去重点。

原则：

> Workbench 优先，Editor 可集成；Work/Git/Agent/Verification 的组合体验优先于重新实现所有编辑器功能。

---

## 15.2 Work Management 重新制造 Jira

风险：增加字段、状态、审批、表单，最后流程本身成为工作。

原则：

> Execution-derived state；只有无法从事实推导的信息才要求用户维护。

---

## 15.3 Multi-Agent 变成 Agent 数量竞赛

风险：Agent 越多，协调和上下文噪音越多。

原则：

> 一个 Agent 能完成，就不要两个；只有实践对象可有效分离时才并行。

---

## 15.4 Automation 失控

风险：背景 Agent 大量自动运行，消耗资源、产生未知改动甚至生产风险。

原则：

> Automation 继承 Runtime Capability、Verification 和 Approval，不存在“自动化特权”。

---

## 15.5 状态多源

风险：Work 状态、Git 状态、Agent 状态、Issue Tracker 状态互相矛盾。

原则：

> 定义 Source of Truth 与 Projection；同步失败必须显式，而不是偷偷覆盖。

---

## 15.6 过早团队化

风险：在单用户产品尚未证明价值时进入 RBAC、Server、SSO 和团队协作。

原则：

> Personal Workbench → Production Workflow → Team Platform。

---

# 第十六章　MES Pilot：产品验证标准

Praxis Workbench 真正是否有价值，可以不用抽象讨论，直接用 MES 作为 Pilot。

选择一个真实中等复杂 Feature：

```text
Requirement:
工单完工增加质检拦截
```

影响：

```text
Java backend
Vben5 web
至少一个 UniApp terminal
Integration tests
Git delivery
```

期望 Praxis 能完成：

1. 建立 Work；
2. 识别相关 repositories；
3. 生成 Work Tree；
4. 用户确认 Goal / Acceptance；
5. 创建隔离工作环境；
6. Backend Agent 实现；
7. 将 API Handoff 给 Web / UniApp Agent；
8. Agent 并行推进；
9. Integration 验证；
10. 出现契约冲突时产生 Challenge / Rework；
11. 汇总 Cross-repo ChangeSet；
12. Git GUI Review；
13. 展示所有 Verification；
14. 形成交付摘要；
15. 外部 Requirement 状态可同步更新。

如果这一流程相比现有“人工 + 多 IDE/终端 + Agent Chat + Git Client + Issue Tracker”能够明显降低：

- 上下文切换；
- 人工追进度；
- 重复解释；
- 漏改仓库；
- 联调返工；

那么 Praxis Workbench 的核心产品命题得到验证。

---

# 第十七章　白皮书边界：现在不决定什么

为了避免再次过早工程化，本白皮书**暂不决定**：

- Desktop 技术栈；
- GUI Framework；
- Work Graph 数据库；
- 是否使用 Electron / Tauri / 原生；
- 具体 Work Item Schema；
- 自动拆需求算法；
- Multi-Agent Scheduler 算法；
- Git Worktree 目录规则；
- 具体 Jira/禅道同步协议；
- Automation DSL；
- Remote Agent 基础设施；
- Team Server 架构；
- 收费模式。

这些属于后续 Product Design / System Design / PRD 阶段。

当前白皮书只冻结：

> **产品为什么存在、面向谁、最终组织什么工作、哪些能力属于长期产品版图、产品层如何分层、什么方向明确不做。**

---

# 第十八章　最终产品原则

Praxis 后续产品设计应始终遵守以下原则：

## 1. Work over Chat

聊天是交互方式，不是工作系统的最高对象。

## 2. Goal over Activity

Agent 忙碌、Token 消耗、Commit 数不是价值；完成用户 Goal 才是价值。

## 3. Execution over Manual Status

尽量从真实执行事件推导状态，不让用户维护第二套“管理现实”。

## 4. Evidence over Narrative

验收结果、Git 变化、Runtime Event 比 Agent 自我总结更可信。

## 5. Human Ownership

Agent 可以执行，用户保留 Goal、关键决策和最终责任。

## 6. Multi-repo First

真实业务系统很少永远只有一个 repo；Workspace 从一开始就是多仓库对象。

## 7. One Agent When Enough

Multi-Agent 是为了解决工作分离和并行问题，不是为了产品视觉效果。

## 8. Structured Handoff

Agent 之间传递工作事实，不传递无限聊天历史。

## 9. Progressive Disclosure

默认让用户看工作和结果；需要时再下钻到 Agent、Evidence 和 Runtime。

## 10. Automation with Governance

自动化继承相同的权限、验证和审计规则。

## 11. Runtime / Workbench Separation

产品体验可以快速演进，但可靠 Runtime 不被 GUI、需求管理和厂商 Integration 污染。

## 12. Local-first, Enterprise-ready Later

先解决个人真实工作，再扩展团队；先允许私有环境接入，再考虑中心化平台。

---

# 结语

Praxis 最初的问题是：

> **怎样让一个 AI Agent 在现实行动中能够被证据纠错，并在失败后仍然知道真实发生了什么？**

这产生了 Praxis Runtime。

当 Runtime 开始足够可靠，下一个问题自然变成：

> **怎样让多个这样的 Agent 真正进入一个工程师每天面对的需求、仓库、Git、测试、Review 和交付流程？**

这产生 Praxis Workbench。

Praxis 的最终产品不应该要求用户成为“Agent 调度员”。真正成熟以后，用户看到的应该只是：

```text
我有哪些重要工作？
现在做到哪里？
哪里需要我判断？
哪些改变已经验证？
哪些风险仍然存在？
```

而在背后，Work Graph 持续组织多个 Repository、Agent Run、Session、Tool、ChangeSet 和 Verification。

因此 Praxis 产品长期方向可以概括为：

> **从 Chat 驱动的 AI 编程，转向 Work 驱动的 Agentic Engineering。**

再进一步：

> **把“需求到交付”的软件生产过程本身，变成一个可执行、可观察、可恢复、可自动化的工作图。**

这将是 Praxis 从一个优秀 Agent Harness，发展为真正能够进入生产研发环境的产品平台的核心路径。

---

# 参考资料（截至 2026-08-28）

[1] OpenAI, *Introducing the Codex app* (2026-02-02)；Codex product pages.  
https://openai.com/index/introducing-the-codex-app/  
https://openai.com/codex/

[2] Cursor, *Meet the new Cursor* (2026-04-02)；*Multitask, Worktrees, and Multi-root Workspaces* (2026-04-24).  
https://cursor.com/blog/cursor-3  
https://cursor.com/changelog/04-24-26

[3] ZCode Docs, *ZCode Agent*；*Automations*；*GLM-5.3 Agentic Coding Guide*.  
https://zcode.z.ai/en/docs/agents  
https://zcode.z.ai/en/docs/automations  
https://zcode.z.ai/en/docs/welcome

[4] GitKraken, *Workspaces in GitKraken Desktop*；*Manage Git Worktrees in GitKraken Desktop*.  
https://help.gitkraken.com/gitkraken-desktop/workspaces/  
https://support.gitkraken.com/gitkraken-desktop/worktrees/

[5] Linear, *AI Agents*；*Assign and delegate issues*；*Agent Interaction Guidelines*；*Linear for Agents*.  
https://linear.app/docs/agents-in-linear  
https://linear.app/docs/assigning-issues  
https://linear.app/developers/aig  
https://linear.app/agents

[6] GitHub Docs, *About third-party coding agents*；*About custom agents*.  
https://docs.github.com/en/copilot/concepts/agents/about-third-party-coding-agents  
https://docs.github.com/en/copilot/concepts/agents/copilot-cli/about-custom-agents

[7] Linear, *Issue tracking is dead* (2026-03-24).  
https://linear.app/next
