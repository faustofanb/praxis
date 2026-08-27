# Praxis Harness：从实践认识论到可验证智能体运行时

## 理论总账、系统设计与 V1 工程封版

**版本：V1 设计基线（2026-08-27）**

---

## 目录

1. 第一篇　理论总账：我们最终得到了什么
2. 第二篇　理论收束：从二十章概念压缩成 V1
3. 第三篇　Praxis Harness 的最终系统理论
4. 第四篇　V1 软件架构
5. 第五篇　工程质量与 Runtime 不变量
6. 第六篇　V1 数据结构与接口规格
7. 第七篇　Agent Loop 与运行流程
8. 第八篇　MVP 实现顺序
9. 第九篇　V1 明确不做
10. 第十篇　待实践验证的问题
11. 第十一篇　代码落地基线

---

## 摘要

Praxis Harness 的出发点不是“如何让大模型一次性想得更聪明”，而是一个更朴素、更严格的问题：**怎样建立一种使模型能够接触现实、形成暂时认识、采取受约束行动、接受现实反馈，并在错误暴露后真正修正自身的智能体运行时。**

本文把前期对马克思、恩格斯、列宁、毛泽东及布站若干理论文章的讨论，与工程控制论、软件工程质量理论以及 DeepSeek Harness、OpenAI Codex、Pi 三套现实 Agent Harness 的架构经验结合起来，最终收束为一个有限的 V1 方案。

本文拒绝两种极端。一种是把 Harness 简化为 `Prompt → Model → Tool → Answer`，把模型的主观判断直接等同于现实；另一种则是把所有哲学概念都工程化，堆叠 Planner、Critic、Judge、Drift Agent、Coalition Agent 等层层中介，最终让治理本身压倒生产。

Praxis Harness 的 V1 原则可以压缩为一句话：

> **以用户需要为目的，以现实反馈为最终检验，以确定性 Runtime 管理非确定性模型和工具，在最小充分治理下完成可靠生产。**

工程上，V1 将采用：

- **Pi 式小核心**：核心功能克制，Multi-Agent、Plan Mode、紧急指挥等尽量外置为扩展；
- **DeepSeek 式事件化**：单一 Event Store（事件存储）承载可回放历史，其他“账本”只是逻辑投影；
- **Codex 式强边界**：Agent Loop 简单明确，权限、沙箱、上下文上限、集成测试等由 Runtime 和工程纪律强制；
- **Praxis 自身的少量实验性机制**：Observation / Hypothesis 显式分层、Challenge 一等事件、可证伪的 Plan。

V1 不追求哲学完备，也不追求功能完备。它的目标是建立一个可运行、可测试、可恢复、可审计的最小闭环，然后让真实工程实践决定下一轮理论发展。

---

# 第一篇　理论总账：我们最终得到了什么

## 1. 从“模型正确”转向“系统可纠错”

最早的问题是：LLM 为什么容易出现幻觉、错误判断和错误行动？如果把目标设成“让模型永远不犯错”，系统就会无休止地增加 Prompt、Reflection（反思）、Debate（辩论）和 Judge（裁判）。但实践认识论提供了另一条道路：

> **允许形成错误假设，但必须使假设能够低成本接触现实、被现实证伪，并推动下一轮认识。**

因此可靠性的中心不再是“一次推理正确率”，而是：

```text
实践 → 观察 → 认识 → 行动 → 验证 → 矛盾 → 修正 → 再实践
```

对应 Agent：

```text
Observe → Model → Hypothesize → Act → Verify → Revise → Repeat
```

这里最核心的变化是：**错误不是异常路径，而是运行时需要正常处理的一种认识状态。**

---

## 2. 实践论：认识必须接触客观环境

从马克思《关于费尔巴哈的提纲》到毛泽东《实践论》，可以抽取出三条直接的 Harness 原则：

第一，模型输出首先是主观认识，不是事实。第二，知识必须来源于实际材料，而不是语言系统内部的自循环。第三，认识必须重新进入实践，通过行动后的现实结果接受检验。

因此，Praxis 必须区分：

- **Observation（观察）**：工具、环境、用户或 Runtime 直接提供的材料；
- **Inference（推断）**：由观察推出的解释；
- **Hypothesis（假设）**：尚待检验的关于现实的可证伪判断；
- **Verified Claim（已验证判断）**：在明确条件和证据范围内得到支持的认识；
- **Falsified Claim（被否定判断）**：已被可靠证据反驳的假设。

V1 中，真正需要显式实现的是 Observation 与 Hypothesis 的区分，以及 Hypothesis 能被支持或否定。没有必要建立复杂知识图谱。

---

## 3. 真理检验：一次成功不是普遍真理

“实践检验真理”不能机械理解成“一次测试通过，所以理论永远正确”，也不能理解成“一次失败，所以整体理论全部错误”。任何实践都有具体条件、范围、测量能力和历史阶段。

对应工程：

```text
Test Passed
≠
Universal Truth
```

更准确的是：

```text
Claim C
在条件 S 下
被 Evidence E 支持
```

因此 V1 的验证结果应该能够表达范围，而不是只有 `verified: true`。对简单任务可以省略显式范围；对高风险、长期知识则应保留环境、版本、时间等条件。

同时，任何理论或 Plan 都必须回答：**什么事实出现以后，我愿意承认当前判断需要改变？** 这就是可证伪性在 Harness 中的最低形式。

---

## 4. 多次反复：新证据比更多内部独白重要

实践与认识之间需要多次反复，不只是因为模型“笨”，而是因为：

- 旧知识会影响对新材料的解释；
- 工具和观测手段有能力边界；
- 现实对象本身比当前模型丰富；
- 新行动会暴露之前隐藏的关系；
- 现实本身也会变化。

因此 Critic 的真正价值不应是“发表另一种意见”，而是**帮助设计能够区分假设的实验**。这形成一条工程原则：

> **New Evidence > More Internal Monologue。新证据通常比更多内部推理更有价值。**

V1 不需要独立 Critic Agent。Worker 可以提出 Challenge，Verifier 可以要求新的外部验证。

---

## 5. 《矛盾论》：失败之前先判断“是什么问题”

普通 Harness 常见逻辑是：

```text
Failure → Retry
```

Praxis 要求先分类：

```text
Failure → Identify Contradiction → Select Method
```

V1 只保留三种最实用的冲突类型：

1. **Epistemic Conflict（认识冲突）**：模型预测 X，现实显示 Y。处理方式是调查、实验、修正认识。
2. **Tunable Tension（可调节张力）**：例如速度与验证深度、探索与执行。处理方式是根据风险和阶段调整比例。
3. **Hard Conflict（硬冲突）**：两个要求在当前约束下不能同时成立，例如“不得外传数据”与“上传第三方服务分析”。处理方式是按硬约束裁决、升级给 Goal Owner，或者改变客观条件。

“主要矛盾”在 V1 中不实现成引擎。它只是 Plan 中的 `focus`：当前认为最阻碍 Goal 的问题。这个判断本身也是假设，需要允许修改。

---

## 6. 群众路线与领导方法：分布感知，集中综合

《关于领导方法的若干问题》可以抽象为两组同构循环：

```text
个别实践 → 一般认识 → 个别验证 → 修正一般认识
```

和：

```text
分散实践 → 集中综合 → 统一策略 → 分散执行 → 新反馈
```

对 Multi-Agent 最有价值的结论不是“多个 Agent 投票”，而是：

> **Diversity of Practice > Diversity of Opinions。实践面的多样性比意见数量更重要。**

多个 Agent 如果只是阅读同一 Context 然后发表意见，可靠性提升有限。真正有价值的是 Code Worker、Runtime Worker、Database Worker、Browser Worker 分别接触不同现实面，再把 Evidence 汇入同一 Session。

然而 V1 不内建 Multi-Agent。它只保证 Extension 能够创建 Child Session / Worker，并通过 Event 向主 Session 返回 Observation、Proposal 或 Challenge。

---

## 7. 领导权与关系分析：不要相信角色名，要看状态转换权

“Planner”“Worker”“Verifier”都只是声明角色。真正的系统角色取决于：

- 谁能看到原始 Evidence；
- 谁能分配任务；
- 谁能执行高风险操作；
- 谁能把 Hypothesis 升级成 Verified；
- 谁能阻止 `RUNNING → SUCCESS`；
- 谁能写长期状态；
- 谁能修改 Policy。

因此：

> **Declared Role ≠ Effective Role。声明角色不等于实际角色。**

V1 不实现复杂 Control Graph（控制关系图）或 Effective Role Analyzer（实际角色分析器）。真正进入 Core 的只有：**Capability（能力权限）检查、状态转换权限和 Event 审计。**

复杂关系分析以后可以通过 Event Store 离线完成。

---

## 8. 再生产与长期漂移：每个任务也在生产下一轮 Agent

长期 Agent 的危险不只是外部攻击。系统内部会不断积累：

- Memory；
- 权限；
- 例外；
- 路径依赖；
- Planner/Worker 能力差异；
- 验证习惯；
- 局部 Reward。

上一轮的结果会变成下一轮的前提：

```text
Result(t) → Preconditions(t+1)
```

因此每个任务实际上产生两类结果：

1. **任务结果**：外部世界发生了什么变化；
2. **结构结果**：Session、Memory、权限、规则和依赖发生了什么变化。

V1 不实现 AI 驱动的 Drift Engine（漂移引擎）、Coalition Analyzer（联盟分析器）或 Relation Reproduction Analyzer（关系再生产分析器）。进入 Core 的只是能够支持未来审计的基础事实：所有重要权限、策略、Challenge、Tool Execution 都进入 Event Store；临时 Capability 有期限；长期状态可版本化和回放。

---

## 9. 《资本论》社会总循环：局部正确不等于全局可持续

Multi-Agent 系统不能只看每个 Agent 的局部性能。即使 Planner、Worker、Verifier 都“工作正常”，也可能因为比例失衡而系统性堵塞：

```text
Evidence 产生率 > 综合能力
Plan 产生率 > 执行能力
Execution 产生率 > Verification 能力
Memory 写入率 > Memory 维护能力
```

这对应软件系统中的 Backpressure（背压）、Bottleneck（瓶颈）和 Capacity Imbalance（能力失衡）。

V1 不实现复杂 Global Cycle Coordinator（全局循环协调器）。但工程上必须有**有界队列、上下文上限、并发上限和单 Session 写入序列化**。这是成熟软件的基础，不需要 AI 来判断。

---

## 10. 多主体目标动力学：局部合理不会自动产生整体合理

不同 Agent 即使没有恶意，也可能因为局部目标互相强化而形成偏离全局目标的稳定行为。例如 Planner 与 Executor 都偏向吞吐，而 Verifier 偏向正确性，长期可能形成“快速通过、弱化验证”的实际路线。

这带来三条最终原则：

- `Reward != Goal`：奖励指标不是最终目标；
- 局部目标必须处于全局 Goal 和 Invariant 之下；
- Hard Constraint 不能与普通 Objective 一起简单加权。

V1 不实现实时目标联盟分析。它只需要 **Goal Stack（目的栈）** 和 **Hard Constraints（硬约束）**。

---

## 11. 政体、安亭与异议机制：监督必须在被监督者不同意时仍然有效

“允许发表意见”不等于拥有纠错能力。对 Agent 来说：

```text
Worker: “Planner 的 H1 和 E31 冲突。”
Planner: “收到，继续。”
```

这种 `can_challenge = true` 是形式监督。

V1 将 Challenge 设计成一等事件，至少包含：

```text
Target + Claim + Evidence References + Conflict Description
```

Planner 可以接受并 Replan；如果拒绝，治理扩展可以进入独立复核。高风险场景可以临时 Action Hold。Verifier 则拥有对“是否完成验证”的真实否决权。

V1 不实现无限层级的 Judge / Reviewer of Reviewer，也不实现完整政治式申诉体系。

---

## 12. 《论持久战》：长期目标可以持久，反馈周期必须短

长期任务具有阶段性。Praxis 只保留三个简单阶段：

- **stabilize（稳定）**：控制风险、取得可观测性；
- **learn（积累）**：实验、排除假设、降低不确定性；
- **converge（收敛）**：集中行动、完整验证、清理临时状态。

重要原则是：

> **Long horizon, short feedback。战略周期可以长，反馈周期必须尽量短。**

V1 中 `phase` 只是可选 State，不需要 Phase Manager Agent。阶段变化由 Planner 建议、Event 记录；真实数据以后再决定是否需要自动判断。

---

## 13. 生产问题与简单需求：治理必须服从生产

Harness 不是目的。它主要是组织模型、工具和环境能力完成用户需要的生产关系。

因此最重要的工程原则之一是：

> **Start simple, escalate on evidence。从简单生产方式开始，由证据推动复杂化。**

最终产品层至少区分：

- **Direct**：简单稳定问题直接模型/简单工具；
- **Praxis**：复杂、不确定、需要验证的任务进入完整闭环；
- **Emergency**：高紧迫、高耦合任务临时压缩指挥链。

Task Router 属于 Product Layer，不属于 Agent Loop Core。V1 初期甚至可以只实现 Direct / Praxis 两条路径，Emergency 作为扩展。

---

## 14. “战争是政治的继续”：手段不能反过来成为目的

Goal、Strategy、Mission、Action 必须形成明确从属：

```text
Need → Goal → Strategy → Mission → Action
```

Tool、Test、Reward、Benchmark、Memory、Autonomy 都只是手段。它们没有重新定义上层 Goal 的主权。

V1 的 Goal Stack 至少包含：

- `goal`：用户真正要求达到的状态；
- `invariants`：不可由普通 Plan 覆盖的约束；
- `strategy` / `mission` 可以在 Plan 中表达；
- `action` 由 Tool Runtime 执行。

如果用户要求自身存在硬冲突，系统应暴露冲突并升级给 Goal Owner，而不是悄悄重写其中一个条件。

---

## 15. 前敌委员会、博古—李德与四渡赤水：集中不是问题，封闭才是问题

紧急环境中，决策延迟本身可能成为主要矛盾，因此允许临时压缩指挥链。但真正危险的不是“少数主体最终拍板”，而是：

- Evidence 无法进入；
- 异议不能改变决定；
- 核心假设被反证后仍不 Replan；
- 决策者控制自己的认证；
- 紧急权限没有退出条件。

因此 Praxis 的理想不是“永远分散”或“永远集中”，而是：

> **Distributed sensing, centralized commitment。感知分布，行动承诺可以集中。**

Emergency Mode（紧急指挥模式）如果以后实现，必须使用有范围、有期限、有审计的 Capability Lease（权限租约）。它是 Extension，不进入 V1 Core。

---

## 16. 工程控制论：Harness 是闭环控制器

控制论把此前哲学语言变成了可测量工程问题：

- **Observability（可观测性）**：是否有足够工具和信号判断真实状态；
- **Controllability（可控性）**：现有 Capability 是否足以把现实推向 Goal；
- **Stability（稳定性）**：多轮反馈以后系统是否收敛，而不是振荡或发散；
- **Feedback Delay（反馈时延）**：行动以后多久才能知道结果；
- **Saturation（饱和）**：Token、Context、Tool、队列和人工审批都有上限；
- **Robustness（鲁棒性）**：模型、工具和环境扰动下仍能保持可接受行为。

因此 V1 的质量中心不在“模型多聪明”，而在**状态是否一致、反馈是否可靠、故障是否显式、系统是否可恢复**。

---

## 17. 软件工程质量：最高风险是状态失真

Harness 最危险的 Bug 常常不是模型答错，而是：

- Tool 已经产生副作用，但 Runtime 认为失败并重复执行；
- Crash 后恢复丢失执行状态；
- Context 压缩丢掉 Goal Invariant；
- Verifier 失败以后默认 SUCCESS；
- Capability 过期后仍可调用；
- Event Schema 变化导致旧 Session 无法恢复。

因此 V1 必须有：

- 显式状态机；
- `SUCCESS / FAILURE / UNKNOWN` 三态执行结果；
- 幂等或 Reconciliation（调和查询）；
- append-only Event Store；
- deterministic replay（确定性重放）；
- Context hard bounds（上下文硬上限）；
- integration / replay / fault injection / compatibility 测试。

---

## 18. DeepSeek、Codex、Pi 的现实校准

三套成熟 Harness 给 Praxis 的工程取向可以总结为：

- **Pi**：核心应该尽可能小，Plan Mode、Subagent、TODO、复杂 UI 不必内建；
- **DeepSeek Harness**：事件、Session、运行时 Policy 和扩展应可组合、可重放；
- **Codex**：核心 Agent Loop 要清楚，Sandbox、Approval、Context bound、Integration Test 属于强工程边界。

Praxis V1 因此选择：

> **Pi 的核心尺寸 + DeepSeek 的事件结构 + Codex 的安全和质量纪律。**

Praxis 自己只保留少数值得实验的认识论机制：Observation/Hypothesis 分层、Challenge Event、可证伪 Plan。

---

# 第二篇　理论收束：从二十章概念压缩成 V1

## 19. 理论到工程的四种归宿

所有前期理论成果最终只能进入以下四种状态：

1. **Core Mechanism（核心机制）**：V1 必须写代码；
2. **Core Rule（核心规则）**：必须成为 Runtime 不变量或数据字段，但不单独造服务；
3. **Extension / Later（扩展或后续）**：Core 留出接缝，V1 不实现完整能力；
4. **Design Lens Only（仅设计视角）**：用于分析和复盘，不进入 API 和状态模型。

只要一个概念无法说明自己属于哪一类，就不允许进入 V1。

---

## 20. 理论成果总映射表

| 理论来源/问题 | 最终工程原则 | V1 形式 | V1 状态 |
|---|---|---|---|
| 实践论 | 认识来自环境并返回环境检验 | Tool Observation + Verification | **Core Mechanism** |
| 感性/理性认识 | 观察与推断不能混淆 | Observation / Hypothesis | **Core Mechanism** |
| 实践检验的条件性 | Verification 有范围 | Evidence refs / optional scope | **Core Rule** |
| 多次反复 | 旧认识可以被新证据推翻 | Hypothesis status / replan | **Core Mechanism** |
| 矛盾特殊性 | 不同失败不同处理 | conflict type | **Core Rule** |
| 主要矛盾 | 当前只聚焦最关键问题 | `plan.focus` | **Core Rule** |
| 群众路线 | 分布实践、集中综合 | Worker Event → Main Session | **Extension / Later** |
| 领导权 | 权限看实际状态转换权 | Capability enforcement | **Core Mechanism** |
| “法权/差别”分析 | 专业分工不等于无限权力 | Role via capability, not name | **Core Rule** |
| 继续革命/漂移 | 初始正确不保证长期正确 | Event history + lease expiry | **Core Rule** |
| 阶级关系分析 | 关系优先于标签 | offline event analysis | **Design Lens Only** |
| 再生产理论 | 任务会改变下一轮条件 | Event history / structural events | **Core Rule** |
| 社会总资本循环 | 上游产出必须匹配下游能力 | bounded queues / context bounds | **Core Mechanism** |
| 多主体局部目标 | Reward 不等于 Goal | Goal Stack + Invariants | **Core Mechanism** |
| 政体问题 | 最高原则与治理形式分离 | Policy / Capability | **Core Mechanism** |
| 安亭/监督 | 异议必须能启动纠错 | Challenge Event | **Core Mechanism** |
| 少数意见 | 未采纳假设可保留 | Hypothesis status | **Core Rule** |
| 论持久战 | 阶段不同，策略不同 | optional `phase` | **Core Rule** |
| 生产问题 | 简单任务走最小路径 | Product Router | **Extension / Product Layer** |
| 战争与政治 | Action 必须可追溯到 Goal | Goal Stack | **Core Rule** |
| 不可调和冲突 | 硬约束不能加权交换 | Invariants / constraints | **Core Mechanism** |
| 前敌委员会 | 紧急时可压缩指挥链 | Emergency extension | **Extension / Later** |
| 博古李德 | 地图不能压倒现实 | Evidence can invalidate plan | **Core Rule** |
| 四渡赤水 | Goal 稳定、Plan 可快速改变 | falsifiable Plan | **Core Mechanism** |
| 工程控制论 | 闭环必须可观测、可控、稳定 | telemetry / bounds / recovery | **Core Mechanism** |
| 软件工程 | 状态必须可重建，副作用安全 | Event Store / Tool lifecycle | **Core Mechanism** |
| DeepSeek | 事件化、可替换、Policy 可重放 | typed Event / seams | **Core Mechanism** |
| Codex | 小 Agent Loop + 强执行边界 | Core loop + sandbox/capability | **Core Mechanism** |
| Pi | 小核心、Extension-first | optional features outside Core | **Core Rule** |
| 联盟漂移 | 观察实际长期取舍 | offline analytics | **Design Lens Only** |
| 实际路线/关系再生产 | 看长期 Event 而非角色名 | audit query | **Design Lens Only** |
| 自动“自我革命” | 不依赖模型自觉，靠可撤销状态 | replay / invalidation | **Core Rule** |

这张表构成 V1 的理论边界。后续开发中，任何新功能如果无法映射到核心问题和质量目标，不进入 Core。

---

# 第三篇　Praxis Harness 的最终系统理论

## 21. 定义

**Praxis Harness 是一个以用户真实需要为最高目的，以外部现实为最终检验标准，通过有限上下文中的模型推理、受约束的工具行动、可重建的事件历史以及可推翻的假设和计划，组织 AI 完成现实生产任务的运行时。**

它不是“让模型说更多话的编排器”，也不是“多个 Agent 开会的平台”。它主要负责五件事：

1. 保持目标和约束不被局部行动偷换；
2. 把现实 Observation 与模型 Hypothesis 分开；
3. 安全执行 Tool，并准确知道副作用发生到了什么状态；
4. 使 Evidence 能够否定当前 Plan；
5. 把完整重要历史保存为可回放事件，使 Crash、分支和审计成为正常能力。

---

## 22. 五个概念域，而不是十几个微服务

理论上可以用五个概念域理解系统：

### 22.1 认识域

维护 Goal、Observation、Hypothesis、Verification。

回答：我们知道什么？为什么相信？什么还只是猜测？

### 22.2 问题与计划域

维护 `focus`、Plan、Replan、Challenge。

回答：现在最该解决什么？当前计划建立在哪个假设上？什么事实可以让它失效？

### 22.3 执行域

维护 Tool、Execution、Result、UNKNOWN、Reconciliation。

回答：我们实际上改变了什么？这个副作用到底发生了吗？

### 22.4 治理域

维护 Capability、Policy、Invariant、Authorization。

回答：谁能做什么？什么绝不能突破？谁能阻止状态转移？

### 22.5 历史与质量域

维护 Event、Replay、Session、Context Projection、Telemetry。

回答：为什么系统现在处于这个状态？崩溃后如何恢复？过去的决策能否重建？

这五个域是认知模型，不对应五个独立服务。

---

## 23. 系统的根本运动

```text
                    User Need / Goal
                           │
                           ▼
                ┌────────────────────┐
                │   Runtime Invariant │
                │  Goal / Capability  │
                └──────────┬─────────┘
                           │
                           ▼
                     Observe Reality
                           │
                           ▼
                  Observation Events
                           │
                           ▼
                Hypothesis / Plan State
                           │
                    propose Action
                           │
                           ▼
                   Capability Check
                           │
                           ▼
                      Tool Runtime
                           │
                           ▼
                       Environment
                           │
                           ▼
                  Result / New Evidence
                           │
            ┌──────────────┴─────────────┐
            ▼                            ▼
        supports                       conflicts
            │                            │
            ▼                            ▼
       continue / finish          falsify / challenge
                                         │
                                         ▼
                                      replan
```

这里没有独立 Critic，也没有独立 Judge。现实结果、Verifier、Challenge 与 Runtime 规则共同完成纠错。

---

## 24. 三种运行模式

### 24.1 Direct：直接生产

适用于稳定、简单、低风险需求。

```text
Request → Model / Simple Tool → Result
```

它可以仍然写最基本 Session 历史，但不启动复杂 Hypothesis / Plan / Governance。

### 24.2 Praxis：实践闭环

适用于复杂、不确定、需要真实工具和验证的任务。

```text
Goal → Observe → Hypothesis → Plan → Authorize
     → Act → Verify → Replan / Complete
```

这是 V1 的主要开发对象。

### 24.3 Emergency：紧急指挥

适用于延迟本身造成重大、持续损害的高耦合任务。特点是分布感知、小型集中决定、短反馈、临时权限和事后审计。

V1 只预留 Mode / Capability Lease 接口，不实现完整 Emergency Extension。

---

# 第四篇　V1 软件架构

## 25. 总体分层

```text
┌───────────────────────────────────────────┐
│               Product Layer               │
│ CLI / UI / Task Router                    │
└────────────────────┬──────────────────────┘
                     │
┌────────────────────▼──────────────────────┐
│                 Praxis Core               │
│                                           │
│ Session / Event Store                     │
│ State Reducer                             │
│ Agent Loop                                │
│ Context Builder                           │
│ Tool Runtime                              │
│ Capability / Policy                       │
└──────────────┬──────────────┬─────────────┘
               │              │
               ▼              ▼
             Model           Tools
                               │
                               ▼
                          Environment

┌───────────────────────────────────────────┐
│              Extension Layer              │
│ Worker/Subagent · Plan UI · Approval UI   │
│ Emergency Mode · Audit · Domain Tools     │
└───────────────────────────────────────────┘
```

设计取向：**核心尺寸偏 Pi，Agent Loop 偏 Codex，Session/Event 偏 DeepSeek，执行边界偏 Codex/DeepSeek。**

---

## 26. Core 模块

### 26.1 `session`

职责：Session 生命周期、Event append、Replay、Fork/Branch、Schema Version。

不负责：业务判断、LLM Prompt、Tool 实现。

### 26.2 `state`

职责：纯函数式 reducer，将 Event Stream 推导为 `DerivedState`。

必须满足：给定同一 Event Stream，产生同一 State。

### 26.3 `agent-loop`

职责：构建当前上下文，请求模型，处理 Tool Call，驱动 Step / Turn 直到完成、中断或失败。

原则：足够简单，核心控制流可以在一屏或少量文件内读懂。

### 26.4 `context`

职责：从 Event / State 中构建有硬边界的 Model Context。

Event Store 是历史数据库；Context 只是当前工作集。

### 26.5 `tools`

职责：Tool Schema、effect semantics（副作用语义）、执行生命周期、timeout、cancel、幂等、Reconciliation。

### 26.6 `policy`

职责：Capability、硬约束、授权。安全检查属于 Core；“如何向人询问审批”可以是 Extension。

### 26.7 `extensions`

职责：提供少量稳定接缝，不提供“任意修改 Core 内部对象”的能力。

初始 seam 建议：

- `turn:start` / `turn:end`
- `context:contribute`
- `model:before` / `model:after`
- `tool:before` / `tool:after`
- `event:appended`

---

## 27. 单一 Event Store

V1 物理上只有一个账本。Evidence、Objective、Structural Audit 都是 Event Projection（事件投影）。

事件必须区分 **Command（意图）** 和 **Event（已发生事实）**。模型说“准备发送邮件”绝不能等同于 `EmailSent`。

建议事件按领域分组：

- Session / Turn
- Goal / Policy
- Model
- Tool
- Epistemic（Observation/Hypothesis）
- Plan / Challenge
- Verification
- Extension custom events

Event Schema 必须有版本号，并对旧 Session 做兼容测试。

---

## 28. 单 Session 单写者

V1 坚持：**Single Writer per Session（单 Session 单写者）**。

多个 Worker 可以并行观察、运行隔离实验，但不能直接并发修改 Global State。Worker 只能向主 Session 发 Observation、Proposal、Challenge 等事件，最终由单一 reducer 顺序提交。

这样可以避免第一版就处理复杂的分布式一致性、冲突合并和 split-brain（脑裂）。

---

# 第五篇　工程质量与 Runtime 不变量

## 29. 软件质量优先级

Praxis 的质量排序是：

> **状态正确 > 功能数量；可恢复 > 表面智能；副作用安全 > 自动重试方便；Runtime 强约束 > Prompt 自律；集成测试 > Demo 能跑。**

V1 重点质量属性：功能正确、可靠性、安全性、可维护性、性能效率、灵活性和 Safety（高风险失败进入安全状态）。

---

## 30. 不变量

以下不变量必须由 Runtime 或类型/状态机保证，而不是靠 Prompt：

1. `UNKNOWN != FAILED`；
2. 未满足 required verification，不能进入 `COMPLETED`；
3. 过期 Capability 不能授权执行；
4. Event Replay 不重新执行真实副作用；
5. Verifier/Approval unavailable 时不能默认通过；
6. Goal Invariant 不能被普通 Plan 修改；
7. Raw historical Event 不能被 Planner 改写；
8. Context 有硬边界，不允许无限增长；
9. Tool 的副作用类型必须声明；
10. Session Replay 必须确定性得到同一 Derived State。

---

## 31. Tool 执行状态机

```text
PROPOSED
   │
   ▼
AUTHORIZED
   │
   ▼
EXECUTING
  /   |    \
 ▼    ▼     ▼
SUCCESS FAILURE UNKNOWN
                  │
             reconcile
              /     \
             ▼       ▼
          SUCCESS  FAILURE
```

`UNKNOWN` 表示请求已经可能到达外部系统，但 Runtime 无法确定副作用是否发生。不能自动转成 `FAILURE` 再盲目重试。

每个 Tool 必须声明：

- `read_only`
- `idempotent_write`
- `reconcilable_write`
- `non_idempotent_write`

如果是写操作，要说明：如何安全 Retry、如何查询现实状态、Cancel 意味着什么、Crash 后如何恢复。

---

## 32. Crash Recovery

对关键副作用，Runtime 必须在执行前持久化 Intent/Started 事件。进程恢复后，如果只存在 `ToolStarted` 而没有终态 Event，进入 `UNKNOWN` 并尝试 Reconciliation。

不宣称不存在共享事务边界时的“Exactly Once”。更现实的目标是：

- at-least-once 请求 + idempotent effect；或
- unknown + reconciliation。

---

## 33. Context 规则

Event Store 保存完整重要历史；Model Context 是有限投影。

以下内容不能仅靠自由文本压缩保存：

- Goal / Invariants；
- Pending UNKNOWN executions；
- Unresolved Challenge；
- Active Capability / Mode；
- Current Plan 的 focus / falsification condition；
- 当前需要的工具定义。

其余旧 Conversation、Tool 输出可以摘要、截断或从 active context 移出。

---

## 34. 测试体系

V1 建立七类测试：

1. **Unit Test**：纯 reducer、风险分类、路由和规则；
2. **Contract Test**：Model/Tool/Store/Extension 接口；
3. **State Machine Test**：合法与非法状态转移；
4. **Property-Based Test**：生成大量随机输入验证不变量；
5. **Integration Test**：fake model + fake tools 跑完整 Agent Loop；
6. **Fault Injection**：在关键边界主动 crash、timeout、Store failure；
7. **Replay / Soak / Compatibility**：真实 Session 回放、长时间运行、旧 Schema 迁移。

真实 LLM Eval 与 Runtime Test 分离。大部分 CI 不依赖真实模型。

---

## 35. CI Quality Gate

建议按改动类型追加测试门槛：

- 普通纯逻辑修改：format + lint + typecheck + unit；
- Agent Loop 修改：+ integration + state/replay；
- Tool Runtime 修改：+ timeout + UNKNOWN + idempotency + crash recovery；
- Capability/Policy 修改：+ adversarial bypass test；
- Event Schema 修改：+ migration + backward compatibility + historical replay；
- Context Builder 修改：+ invariant retention + hard-bound test。

---

# 第六篇　V1 数据结构与接口规格

## 36. 基础 ID

```ts
export type SessionId = string & { readonly __brand: "SessionId" };
export type EventId = string & { readonly __brand: "EventId" };
export type TurnId = string & { readonly __brand: "TurnId" };
export type ToolExecutionId = string & { readonly __brand: "ToolExecutionId" };
export type ObservationId = string & { readonly __brand: "ObservationId" };
export type HypothesisId = string & { readonly __brand: "HypothesisId" };
```

V1 可以使用 UUID/ULID；brand 只是避免把不同 ID 在 TypeScript 中错误混用。

---

## 37. Event 基类

```ts
export interface EventBase<T extends string, P> {
  readonly id: EventId;
  readonly sessionId: SessionId;
  readonly seq: number;
  readonly schemaVersion: 1;
  readonly type: T;
  readonly occurredAt: string;
  readonly payload: P;
}
```

所有 Event append 后不可原地修改；“纠正历史”通过新增 Event 表达。

---

## 38. Goal

```ts
export interface GoalState {
  readonly goal: string;
  readonly invariants: readonly string[];
  readonly owner: "user" | "system";
}
```

后续可以增加结构化 constraint，但 V1 不构建复杂 Goal DSL。

---

## 39. Observation 与 Hypothesis

```ts
export interface Observation {
  readonly id: ObservationId;
  readonly source:
    | { readonly kind: "tool"; readonly executionId: ToolExecutionId }
    | { readonly kind: "user" }
    | { readonly kind: "runtime" };
  readonly statement: string;
  readonly scope?: Record<string, string>;
}

export interface Hypothesis {
  readonly id: HypothesisId;
  readonly claim: string;
  readonly evidence: readonly ObservationId[];
  readonly status: "proposed" | "supported" | "falsified" | "stale";
  readonly falsifiedIf?: string;
}
```

不要让模型生成任意“fact”字段。已验证知识是 Hypothesis/Claim 经 Event 状态转换后的结果。

---

## 40. Plan

```ts
export interface PlanState {
  readonly goal: string;
  readonly focus?: string;
  readonly hypothesisId?: HypothesisId;
  readonly nextAction?: string;
  readonly falsifiedIf?: string;
  readonly phase?: "stabilize" | "learn" | "converge";
}
```

Praxis Plan 不是 TODO List，而是当前行动假设。TODO 可以由 Extension 自行实现。

---

## 41. Challenge

```ts
export interface ChallengePayload {
  readonly target:
    | { readonly kind: "hypothesis"; readonly id: HypothesisId }
    | { readonly kind: "plan" }
    | { readonly kind: "verification" };
  readonly claim: string;
  readonly evidence: readonly ObservationId[];
  readonly conflict: string;
}
```

Challenge 只是提出结构化异议，不自动获得无限 Veto。

---

## 42. Tool Contract

```ts
export type ToolEffect =
  | "read_only"
  | "idempotent_write"
  | "reconcilable_write"
  | "non_idempotent_write";

export interface ToolDefinition<I, O> {
  readonly name: string;
  readonly effect: ToolEffect;
  readonly capability: string;
  readonly inputSchema: unknown;

  execute(input: I, ctx: ToolExecutionContext): Promise<O>;

  reconcile?(
    execution: ToolExecutionRecord,
    ctx: ToolExecutionContext,
  ): Promise<"succeeded" | "failed" | "indeterminate">;
}
```

`reconcile` 不是每个 Tool 必须实现；无法安全重试也无法查询的写操作，在 `UNKNOWN` 时应停止自动继续。

---

## 43. Capability

```ts
export interface CapabilityGrant {
  readonly capability: string;
  readonly scope?: Record<string, string>;
  readonly grantedAt: string;
  readonly expiresAt?: string;
  readonly reason?: string;
}
```

核心只判断 Capability 是否存在、范围是否匹配、是否过期。Approval UI 可以由 Extension 提供。

---

## 44. Derived State

```ts
export interface DerivedState {
  readonly sessionId: SessionId;
  readonly status: "running" | "completed" | "failed" | "interrupted";
  readonly goal: GoalState;
  readonly plan?: PlanState;
  readonly observations: ReadonlyMap<ObservationId, Observation>;
  readonly hypotheses: ReadonlyMap<HypothesisId, Hypothesis>;
  readonly pendingTools: ReadonlyMap<ToolExecutionId, ToolExecutionRecord>;
  readonly unresolvedChallenges: readonly ChallengePayload[];
  readonly capabilities: readonly CapabilityGrant[];
}
```

State 只由 Event reducer 产生，不允许 Agent 直接 mutate。

---

# 第七篇　Agent Loop 与运行流程

## 45. Core Agent Loop 伪代码

```ts
async function runTurn(sessionId: SessionId, userInput: UserInput) {
  await events.append(userMessageReceived(sessionId, userInput));

  while (true) {
    const state = await sessions.derive(sessionId);
    const context = await contextBuilder.build(state);

    const response = await model.generate(context, tools.visibleTo(state));
    await events.append(modelResponseReceived(sessionId, response));

    if (response.toolCalls.length > 0) {
      for (const call of response.toolCalls) {
        const stateNow = await sessions.derive(sessionId);
        const decision = policy.authorize(stateNow, call);

        if (!decision.allowed) {
          await events.append(toolDenied(sessionId, call, decision.reason));
          continue;
        }

        await executeToolWithLifecycle(sessionId, call);
      }
      continue;
    }

    if (response.final) {
      const stateNow = await sessions.derive(sessionId);
      const verification = await verifier.checkIfRequired(stateNow);

      if (verification.status === "passed") {
        await events.append(turnCompleted(sessionId));
        return response.final;
      }

      if (verification.status === "needs_more_work") {
        await events.append(verificationRequestedMoreWork(sessionId));
        continue;
      }

      throw new Error("verification unavailable must not default to success");
    }
  }
}
```

真正实现时会拆分函数、处理 cancel/timeout/streaming，但主控制流不应比这个复杂很多。

---

## 46. Tool 生命周期伪代码

```ts
async function executeToolWithLifecycle(
  sessionId: SessionId,
  call: ToolCall,
) {
  const executionId = newToolExecutionId();

  await events.append(toolProposed(sessionId, executionId, call));
  await events.append(toolAuthorized(sessionId, executionId));
  await events.append(toolStarted(sessionId, executionId));

  try {
    const output = await toolRuntime.execute(call, executionId);
    await events.append(toolSucceeded(sessionId, executionId, output));
  } catch (error) {
    const classification = toolRuntime.classifyFailure(error);

    if (classification === "indeterminate") {
      await events.append(toolIndeterminate(sessionId, executionId));
      return;
    }

    await events.append(toolFailed(sessionId, executionId, serialize(error)));
  }
}
```

恢复时扫描无终态 execution，按 Tool effect 和 `reconcile()` 进入恢复流程。

---

## 47. Direct 路径

Direct 不需要强制建立 Hypothesis / Plan。产品层可以：

```text
Request
  │
  ├─ stable knowledge / no side effect → direct model
  │
  ├─ one simple read tool             → light tool path
  │
  └─ uncertain / state-changing       → Praxis Session
```

第一版 Router 不需要 AI 复杂编排。可以先由调用方显式选择或用很少的规则判断。

---

## 48. Praxis 路径

Praxis 路径要求：

- side-effect Tool 经过 Capability；
-重要 Observation 可以进入显式状态；
- Plan 可记录 `focus` 和 `falsifiedIf`；
- Challenge 可以成为事件；
- required verification 未通过不完成。

不是每一步都必须生成 Hypothesis。简单可确定操作不强迫哲学仪式化。

---

## 49. Emergency 路径

V1 Core 只需要能够表达：

```text
ModeChanged(normal → emergency)
CapabilityGranted(with expiry)
ModeChanged(emergency → normal)
```

完整的 Mission Command Cell、临时审批链、事后审计 UI 延后。安全关键点是：紧急权限有期限，不允许自动永久写回 Policy。

---

# 第八篇　MVP 实现顺序

## 50. Milestone 0：工程骨架

目标：建立 repository、CI、TypeScript strict、lint、test runner、SQLite migration。

验收：空 Event Store 能 append/replay，旧 schema fixture 能加载。

---

## 51. Milestone 1：最小可运行闭环

实现：

```text
User Message
→ Model Provider
→ read-only Tool
→ Tool Result
→ Model Final
→ Event Store
→ Restart
→ Resume Session
```

必须有：

- Session / Event；
- reducer；
- Agent Loop；
- Context Builder；
- Model Provider adapter；
- read-only Tool；
- Integration Test；
- Replay Test。

这一步完成以后，就已经是可用 Harness，不等后面所有理论功能。

---

## 52. Milestone 2：安全副作用

新增：

- Capability Core；
- 写 Tool；
- ToolEffect；
- UNKNOWN；
- idempotent / reconcile；
- Crash recovery；
- timeout/cancel；
- adversarial capability test。

验收重点：在每个关键边界 crash 后，不能重复产生危险副作用或错误宣布完成。

---

## 53. Milestone 3：Praxis 认识层

新增：

- Observation Event；
- Hypothesis Proposed/Supported/Falsified；
- Plan State（focus / falsifiedIf）；
- Challenge Event；
- Verification interface。

这一步才真正验证 Praxis 与普通 Agent Loop 的差异。

---

## 54. Milestone 4：Extension API

新增少量 seam；实现第一个外部 Extension，例如 Plan UI 或 Worker/Subagent。

如果为了扩展一个功能必须修改大量 Core，说明 seam 设计不足；如果每一个内部函数都暴露成 hook，说明过度插件化。

---

## 55. Milestone 5：产品路由与性能

新增 Direct/Praxis Router，建立简单任务开销基线，确保复杂治理不会污染简单路径。

这一步以后再讨论 Emergency、Multi-Agent 和长期 Memory。

---

# 第九篇　V1 明确不做

## 56. 功能冻结清单

以下内容即使理论上有价值，也明确不进入 V1 Core：

- 不内建 Multi-Agent 调度器；
- 不内建 Critic Agent；
- 不内建 Judge Agent；
- 不内建“主要矛盾引擎”；
- 不做实时 Coalition/联盟分析；
- 不做 AI 驱动 Drift Engine；
- 不做关系再生产实时模型；
- 不做复杂 Workflow DSL；
- 不做 DeepSeek 式 everything-is-plugin；
- 不复制 Codex 完整 App Server / Cloud 产品体系；
- 不做企业级分布式 Event Bus；
- 不做跨机器一致性；
- 不做自动修改 Constitution / Goal Invariant；
- 不做长期无人值守生产运维；
- 不宣称 Exactly Once 外部副作用；
- 不把真实 LLM 放入大多数 Core correctness CI；
- 不把全部历史塞入 Model Context；
- 不因“理论完整”而新增没有真实故障证据的模块。

Extension Layer 可以试验 Multi-Agent、Plan Mode、Emergency Mode、Audit Dashboard，但这些试验不得反向污染 Core。

---

# 第十篇　待实践验证的问题

## 57. 认识论机制是否真的有收益

V1 必须通过真实任务回答：

1. Observation / Hypothesis 显式分层，是否减少“模型把自己猜测当事实”的失败？
2. `falsifiedIf` 是否能减少无效 Retry 和错误 Plan 固守？
3. Challenge Event 是否比普通对话式 Critic 更能提前阻止错误行动？
4. 少量 Epistemic State 是否值得增加 Context 和实现复杂度？

如果无明显收益，应删减，而不是因为理论漂亮继续保留。

---

## 58. Event Sourcing 是否值得

需要测量：

- Replay/Recovery 实际捕获了多少问题；
- Event Store 的 Schema 演化成本；
- Session 重放性能；
- Event 数量、磁盘和投影复杂度。

如果长期发现完整 Event Sourcing 过重，也允许退回更简单的 append log + snapshot，只要不破坏可重建性和副作用安全。

---

## 59. Direct/Praxis 路由是否有效

要测：

- 简单任务增加了多少额外延迟；
- 有多少任务被错误升级为复杂模式；
- 有多少复杂任务因为过早走 Direct 而缺少验证。

路由器本身不能成为新的复杂 Agent。

---

## 60. Capability Core 是否足够小

真正需要实践验证：

- Scope 怎样表达才够用；
- Tool delegation 是否造成间接越权；
- Sandbox 与 Capability 如何组合；
- Approval UI 应该多大程度进入 Extension。

V1 优先保护清晰边界，不追求一开始支持所有企业策略。

---

# 第十一篇　代码落地基线

## 61. 推荐技术栈

V1 推荐 **TypeScript + Node.js + SQLite**。

理由：

- TypeScript 适合快速验证 Agent API、Tool 和 Extension；
- DeepSeek/Pi 都提供大量可参考的 TypeScript 工程经验；
- JSON/Schema/Event 生态成熟；
- 开发速度高于第一版直接选择 Rust；
- 真正需要先验证的是 Harness 理论，不是极限性能。

但 Core 采用严格 TypeScript：`strict`、discriminated union（可辨识联合类型）、schema validation、exhaustive switch、尽量少 `any`。

---

## 62. 建议目录

```text
praxis-harness/
├─ packages/
│  ├─ core/
│  │  ├─ src/
│  │  │  ├─ agent-loop/
│  │  │  ├─ context/
│  │  │  ├─ events/
│  │  │  ├─ session/
│  │  │  ├─ state/
│  │  │  ├─ tools/
│  │  │  ├─ policy/
│  │  │  └─ extensions/
│  │  └─ test/
│  ├─ sqlite-store/
│  ├─ model-openai/
│  ├─ cli/
│  └─ testkit/
├─ examples/
├─ fixtures/
│  └─ sessions/
├─ docs/
│  ├─ architecture.md
│  ├─ invariants.md
│  └─ tool-contract.md
└─ package.json
```

初期不要 monorepo 过度拆包。如果实际维护发现 `core` 中模块边界仍然清楚，也可以从更少 package 开始。

---

## 63. 第一批 Commit

建议真正开工后按下面顺序提交：

1. `chore: initialize strict typescript workspace`
2. `feat: add versioned append-only session events`
3. `feat: derive deterministic session state from events`
4. `feat: add scripted model provider and minimal agent loop`
5. `feat: add read-only tool runtime`
6. `test: add session replay and loop integration fixtures`
7. `feat: add sqlite event store and resume`
8. `feat: add capability enforcement and tool lifecycle`
9. `feat: represent indeterminate tool outcomes`
10. `test: add crash recovery and idempotency scenarios`
11. `feat: add observation and hypothesis events`
12. `feat: add falsifiable plan and challenge events`

到第 6 个 commit 应该已经存在第一个可运行 CLI。不能等“架构全部完成”才产生第一份用户价值。

---

# 结语：从理论回到实践

Praxis Harness 的理论路线最终没有导向一个庞大的“哲学 Agent”。恰恰相反，理论越深入，最后要求的 Core 越小、边界越硬、事实越清楚。

实践认识论要求我们把模型认识和客观事实分开；《矛盾论》要求根据具体失败选择具体方法；群众路线提醒我们让 Evidence 来自分散实践而不是模型投票；领导权和再生产分析让我们关注实际状态转换权和长期结构变化；《论持久战》告诉我们长期目标和短反馈并不矛盾；生产问题则最终规定：**所有治理都必须服从用户需要和现实生产。**

工程控制论进一步把这些原则转成可观测性、可控性、稳定性、反馈时延和鲁棒性；软件工程则把“自我纠错”落成 Event、状态机、幂等、UNKNOWN、Replay、Crash Recovery、Context Bound 和 Integration Test。

DeepSeek、Codex、Pi 三套现实 Harness 最终又迫使我们做了第二次减法：成熟基础设施应该借鉴，不应重新发明；真正属于 Praxis 的实验空间只保留很少几个机制。

因此，V1 的最终工程判断是：

> **Core 不负责让模型永远正确；Core 负责让模型的认识和行动始终有机会被现实纠正，而且系统在失败、崩溃和长期运行中仍然知道自己真正做过什么。**

如果真实实现证明 Observation/Hypothesis、Challenge、可证伪 Plan 并没有带来可靠性提升，就删除它们。如果真实实现暴露出新的结构性失败，再重新打开理论讨论。

这不是理论工作的结束，而是理论第一次具备了接受实践检验的条件。

---

# 参考文献与工程资料

## A. 马克思主义经典

1. Karl Marx, *Theses on Feuerbach* / 《关于费尔巴哈的提纲》.
2. Karl Marx, *Capital*, Vol. I, II, III / 《资本论》第一、二、三卷.
3. Karl Marx, *Critique of the Gotha Programme* / 《哥达纲领批判》.
4. Karl Marx, *A Contribution to the Critique of Political Economy, Preface* / 《〈政治经济学批判〉序言》.
5. V. I. Lenin, *Materialism and Empirio-Criticism* / 《唯物主义和经验批判主义》.
6. V. I. Lenin, *What Is to Be Done?* / 《怎么办？》.
7. Mao Zedong, 《实践论》.
8. Mao Zedong, 《矛盾论》.
9. Mao Zedong, 《关于领导方法的若干问题》.
10. Mao Zedong, 《论持久战》.

## B. 布站/相关理论文章（本项目陪读主线）

1. 张角：《略论马列毛主义的哲学基础》.
2. 张角：《实践是如何检验真理的？》.
3. 张角：《实践与认识之间的多次反复是如何产生的？》（一、二）.
4. 张角：《论领导权与资产阶级法权——复辟与反复辟的理论依据》.
5. 张角：《“无产阶级专政下继续革命”的理论起源》.
6. 张角：《我们时代的阶级图景——马列毛主义的阶级学说》.
7. 张角：《我们时代的阶级斗争——马列毛主义的革命斗争理论》.
8. 张角：《〈社会主义政治经济学〉导言》.
9. 张角：《〈资本论〉体系诸公式说明》.
10. 张角：《略论无产阶级专政的政体问题》.
11. 赤眉：《简论安亭宪章》.

## C. 工程控制论与软件质量

1. Hsue-Shen Tsien, *Engineering Cybernetics*, 1954.
2. ISO/IEC 25010:2023, *Systems and software engineering — Systems and software Quality Requirements and Evaluation (SQuaRE) — Product quality model*.
3. Martin Fowler, “Event Sourcing”, https://martinfowler.com/eaaDev/EventSourcing.html
4. Google SRE Workbook, “Error Budget Policy”, https://sre.google/workbook/error-budget-policy/
5. Stripe API Documentation, “Idempotent Requests”, https://docs.stripe.com/api/idempotent_requests

## D. Agent Harness 工程参考（截至 2026-08）

1. DeepSeek AI, **DeepSeek Harness**: https://github.com/deepseek-ai/deepseek-harness
   - Architecture: https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/architecture.md
   - 核心取向：Cordis、Everything is a Plugin、typed events、可撤销 effects、session/runtime 可组合。
2. OpenAI, **Codex**: https://github.com/openai/codex
   - “Unrolling the Codex agent loop”: https://openai.com/index/unrolling-the-codex-agent-loop/
   - App Server: https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md
   - 核心取向：明确 Agent Loop、Thread/Turn/Item、强执行边界、上下文和工程质量纪律。
3. Earendil Works, **Pi**: https://github.com/earendil-works/pi
   - Coding Agent README: https://github.com/earendil-works/pi/blob/main/packages/coding-agent/README.md
   - Security: https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/security.md
   - 核心取向：minimal core、Extension-first、默认不内建 subagents / plan mode / permission popup。

---

**封版说明：** 本文是 Praxis Harness V1 的设计基线。V1 开始实现后，除非真实代码、测试、故障轨迹或用户任务提供反证，不再因新的理论类比增加一级 Core 模块。
