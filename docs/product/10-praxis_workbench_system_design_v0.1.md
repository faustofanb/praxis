# Praxis Workbench System Design

## v0.1 系统设计基线

- 中文名：Praxis Workbench 系统设计
- 版本：v0.1
- 日期：2026-08-31
- 文档性质：System Design / Architecture Baseline
- 上位文档：01-09 Praxis Product Baseline
- 下一文档：11《Praxis Engineering Baseline v2》、12《Praxis Workbench Development Plan》

> 本文冻结 v1 系统逻辑边界、物理组件、Authority、State、Agent Runtime、Tool/Connector、Git/Worktree、Repository Intelligence、Environment/Deployment、AI Context、Resource/Security/Recovery 与 Desktop Technology Selection。exact dependency version 由 11 锁定。

## 目录

- 第一章 文档定位与系统设计目标
- 第二章 总体逻辑架构与权威边界
- 第三章 Durable State、Event History 与 Artifact Architecture
- 第四章 Agent Runtime：Run、Epoch 与可恢复执行
- 第五章 Tool、Connector、Plugin 与外部能力运行时
- 第六章 Git 与 Worktree Architecture
- 第七章 Repository Intelligence Architecture
- 第八章 Environment、Database、Runtime Host 与 Deployment
- 第九章 AI Provider、Routing、Context 与 Prompt Cache
- 第十章 Resource、Security、Sandbox 与 Recovery
- 第十一章 物理技术架构与 Runtime Language Allocation
- 第十二章 IPC、Protocol、UI Bridge 与版本协商
- 第十三章 State Store、Secret Store、Artifact Store 与文件布局
- 第十四章 Git、Search、Tree-sitter、Watcher 与 SSH 具体技术
- 第十五章 Platform Sandbox 与 Cross-platform 交付策略
- 第十六章 Packaging、Release、Update 与 Binary Compatibility
- 第十七章 Physical Component Map 与依赖方向
- 第十八章 Failure Model、Recovery Matrix 与 Reconciliation
- 第十九章 Performance、Backpressure 与大数据路径
- 第二十章 Architecture Conformance Baseline
- 第二十一章 Vertical Slice 到物理组件的映射
- 第二十二章 10.10 技术选型冻结结论与风险门
- 附录 A：当前技术研究快照（2026-08-31）
- 附录 B：Deferred Decisions 与下一阶段输入
- 附录 C：术语表

# 第一章 文档定位与系统设计目标

本文件是《Praxis Workbench System Design v0.1》的正式系统设计基线，承接 01-09 产品基线，职责是把已经冻结的产品边界落实成可实现、可测试、可恢复、可审计的物理系统结构。本文不再扩张产品概念，也不把当前任何不成熟 Praxis CLI 工作流、Skill 编排、固定需求文档或状态机搬进 Workbench。

Praxis v1 的系统目标是：在一个本地优先的桌面工作台中，让用户通过 Conversation 完成真实研发工作，而系统在后台可靠地连接 Multi-Repository、Git/Worktree、Repository Context、Database/DBX、Runtime Host/Logs、Deployment 与 Verification Evidence。长期事实由 Work 持有，交互由 Conversation 承载；AI 是不确定性执行边缘，不拥有最终状态、权限或秘密。

系统设计必须同时满足五个最高级约束：

- **Correctness before cleverness**：外部副作用不确定时保存 UNKNOWN，不猜测成功或失败。
- **Bounded by construction**：Token、内存、进程、磁盘、Tool Output、Child Run、Index、Diagnostics 均必须有界。
- **Recoverable by construction**：UI、Agent Worker、Connector、Indexer、Core 乃至整机异常均有明确恢复语义。
- **Authority is explicit**：模型只能提出 Intent；Core 授权；Operation Ticket 冻结动作；Worker 执行；Evidence 重新观察现实。
- **Simple Surface, Deep System**：系统内部可以严谨，但正常用户路径不能变成审批流、Agent 管理或状态管理仪式。

### v1 非目标

v1 不建设完整 IDE、完整 Fork 替代、完整数据库客户端、完整 SSH Terminal、通用 DevOps 平台、通用 Workflow Engine、重型 Work Graph Editor、AI 公司组织模拟、多 Agent 团队看板、全仓向量知识库或企业级 Team Server/RBAC。系统架构必须为后续扩展留接口，但这些能力不得进入 v1 Critical Path。

# 第二章 总体逻辑架构与权威边界

Praxis 采用“控制面与数据面分离”的本地多进程架构。逻辑组件如下：

```text
UI Renderer / Desktop Shell
            │
            ▼
      Praxis Core (praxisd)
      ├ Domain State / Policy
      ├ Operation Journal
      ├ Config Snapshot
      ├ Resource Governor
      └ Worker Coordination
            │
   ┌────────┼─────────┬──────────┬───────────┐
   ▼        ▼         ▼          ▼           ▼
Agent    Model      Native     MCP/DBX     Index
Worker   Gateway    Worker     Host        Worker
                    │
                    ├ Git / FS / Process
                    └ SSH / Artifact IO
```

### 核心权威模型

- **Core** 是 Praxis Durable Domain State 的唯一 Writer，拥有 Work、Run、Operation、Verification、Config Revision、Approval、Capability Lease、Resource Lease 等控制面事实。
- **UI** 是 Projection Client，不直接写 SQLite，不直接拿 Secret，不直接执行 Shell/Git/DB/SSH。
- **Agent Worker** 负责推理与 Agent Loop，不持有 Provider、DB、SSH Secret，不直接拥有任意文件系统或进程权限。
- **Model Gateway** 只拥有 Provider 网络与最小 Provider Credential，不拥有 Repo、Git、DB、SSH、Deploy 权限。
- **Native Worker / Connector Worker** 执行精确 Ticket 指定的现实操作，但不拥有 Policy 决策权。
- **Supervisor** 掌握 Worker 进程生命、Process Tree、Heartbeat、Resource Hard Limits，不做业务决策。

### 真相的四层

1. **Product State**：Work、Run、Config、Approval 等，由 Core 权威维护。
2. **External Reality**：Git、DB、Host、Deployment，由外部系统自己权威维护。
3. **Evidence / Observation**：Praxis 在某时刻对 External Reality 的不可变观察，必须带来源和时间。
4. **Projection / Cache / Index**：可删除重建，不拥有事实主权。

因此“Single Durable Writer”不意味着“Praxis 是世界的唯一真相”。Git、生产数据库和服务器可能被 IDEA、Fork、CLI、人工运维或其它系统随时修改。Praxis 必须重新观察，而不是假设所有变化都经过自身。

### Process & Authority Matrix

| Component | 写 Domain State | Repo Write | Git Mutation | Provider Network | DB/SSH | Secret | Spawn |
|---|---:|---:|---:|---:|---:|---:|---:|
| UI Renderer | 否 | 否 | 否 | 否 | 否 | 否 | 否 |
| Desktop Shell | 否 | 否 | 否 | 否 | 否 | 否 | 仅启动/连接 daemon |
| Praxis Core | **是** | 否 | 否 | 否 | 否 | Secret Ref / Broker | 通过 Supervisor |
| Supervisor | 否 | 否 | 否 | 否 | 否 | 否 | **是** |
| Agent Worker | 否 | 否 | 否 | 否 | 否 | 否 | 否 |
| Model Gateway | 否 | 否 | 否 | **是** | 否 | Provider Scoped | 否 |
| Native Worker | 否 | Scoped | Ticketed | Scoped | SSH 可 Scoped | Operation Scoped | 否 |
| MCP Host | 否 | 否 | 否 | Connector Scoped | Ticketed | Connector Scoped | 否 |
| Index Worker | 否 | Read Only | 否 | 默认否 | 否 | 否 | 否 |

### 本章硬不变量

1. UI、Agent、Worker 均不得绕过 Core 直接修改 Praxis Domain State。
2. Agent 不持有 Secret，不直接 Spawn Worker/Subagent。
3. 所有外部 Mutation 都必须先由 Core durable 记录授权意图，再 Dispatch。
4. UI 生命周期与 AgentRun 生命周期分离；UI 崩溃不能自动终止后台安全工作。
5. 进程隔离首先是 Failure/Resource Boundary；真正 Security Boundary 还必须由 Sandbox、Credential Isolation 与外部系统权限共同实现。

# 第三章 Durable State、Event History 与 Artifact Architecture

Praxis v1 不采用纯 Event Sourcing，也不采用 CRUD-only。正式持久化模式为：

> **Append-oriented Domain History + Transactional Current State + Content-addressed Artifact Store + Rebuildable Projections**

### 数据分层

| Layer | 示例 | 长期保存 | 可重建 | 物理位置 |
|---|---|---:|---:|---|
| Authoritative Domain State | Work / Run / Operation / Config / Verification | 是 | 否 | SQLite |
| Domain History | 关键状态迁移、授权、UNKNOWN、Reconcile | 是 | 否 | SQLite |
| Durable Artifact / Evidence | Diff snapshot、DB evidence、日志片段、测试报告 | 按策略 | 通常否 | Filesystem + SQLite metadata |
| Diagnostics | Tool stdout、MCP debug、worker logs | TTL/有界 | 可丢 | diagnostics |
| Index / Cache | Symbol、file metadata cache、graph cache | 否 | 是 | cache/index |
| Runtime | staging、stream、recovery mailbox | 否 | 是/短期 | runtime |

### SQLite 的职责

SQLite 只保存小型、事务性、可备份的 Product State，不保存大型 Tool stdout、Git object database、Repo 源码、完整服务器日志、Embedding 向量或构建二进制。Core 是唯一 Writer；Worker 不直接打开数据库写入。

一次 Domain Command 必须在一个 SQLite Transaction 内原子完成：

1. Append Domain Event / History Record；
2. Update Current State；
3. Update Operation / Run 等 critical record；
4. 更新必要的 Critical Projection revision；
5. Commit。

Domain Event 必须保持“小”。例如 Tool 完成事件只记录 operation_id、结果语义、exit code、duration、bytes、truncated、artifact refs，而不承载数百 MB stdout。

### Conversation 与 Domain Event 分离

Conversation 保存人和 Assistant 的最终语义消息以及 Tool/Artifact 引用，不保存逐 token stream、Provider frame、重复完整 Prompt、隐藏 Chain-of-Thought 或所有原始 Tool 输出。Conversation 可以很长，但 Context Builder 不等于“加载全部 Conversation”。

### Content-addressed Store

不可变 Blob 采用内容寻址，例如 SHA-256：

```text
artifacts/objects/sha256/ab/abcdef...
```

适合保存：Evidence snapshot、Log excerpt、DB query snapshot、Test report、Patch/Change Manifest、Screenshot。Work、Run、Operation 等有生命周期的领域对象仍使用稳定 ID，不采用 hash 作为身份。

### Artifact Promotion

Worker 所有输出先进入 bounded staging。只有满足以下价值之一时才 Promote 到 Durable Artifact Store：证明 Claim、支持未来复查、不可方便重建、用户明确要求保存、是重要外部观察。否则 TTL 后删除。

### Evidence

Evidence 不是独立 Ledger DB。Artifact 是“东西”，Evidence Binding 是这个 Artifact/Observation 对 Verification Claim 的 SUPPORTS/CONTRADICTS/CONTEXT 等关系。

### Operation Journal

DISPATCHED 必须在实际把 Ticket 交给 Worker 之前 durable commit。即使因此出现“数据库记录 DISPATCHED 但 Worker 尚未收到”的保守不确定，也优于先执行后记录。外部 Mutation 无法确定时进入 UNKNOWN，然后通过 Reconciliation 重新观察现实。

### Conversation Compaction

Compaction 必须从 authoritative Work State 重新补水：把长期有效的 Fact、Decision、Evidence、Current Change State 提升到结构化事实层，再减少旧 Conversation 对 Context 的占用。LLM Summary 可以作为导航辅助，但永远不能成为新 Truth。

### Storage GC

清理顺序固定为：runtime temp → expired diagnostics → rebuildable cache/index → expired unreferenced artifact。不得因为磁盘压力删除 authoritative state、仍被 Evidence 引用的 Artifact 或 dirty worktree。

# 第四章 Agent Runtime：Run、Epoch 与可恢复执行

AgentRun 不是一个无限长、必须常驻内存的“AI Session”。正式模型为：

> **AgentRun 是持久逻辑执行尝试，由多个有限、可恢复的 Run Epoch 组成；Agent Worker 是 Disposable Executor。**

```text
Work
├ Main Conversation
└ Assignment
    └ AgentRun
        ├ Epoch 1
        │  ├ ModelCall
        │  ├ ToolOperation
        │  └ Observation
        ├ Epoch 2
        └ ...
```

### 对象边界

- Work：长期工程事实。
- Conversation：长期交互历史，不属于某一个 Run。
- Assignment：明确责任、Goal、Scope、Completion Contract、Capability 上限。
- AgentRun：完成 Assignment 的一次逻辑执行尝试。
- Epoch：一次短暂激活窗口，有明确 Trigger 和 Hard Budget。
- ModelCall：一次模型调用。
- ToolOperation：独立外部现实操作。
- Provider Session Handle：缓存/Transport 优化，可丢弃，不是恢复依赖。

### Epoch Trigger

典型 Trigger：USER_MESSAGE、TOOL_RESULT、APPROVAL_GRANTED、CHILD_RESULT、RECOVERY、RESUME、RECONCILIATION_RESULT。Epoch 开始时冻结 Config Snapshot、Tool Catalog Revision、Route Candidate Set、Resource Envelope 和 Context Manifest。

### 等待时释放 Agent Worker

长时间 Build、DB query、审批、用户输入、Child Run 等不要求 Agent Worker 持续存活。Agent 发起 Operation 后，如果超过短 inline wait window，则 Epoch checkpoint，Run 进入 WAITING，Agent Worker 释放。Operation 完成后用新 Epoch 继续。

### Completion Contract

模型只能 `ProposeCompletion`。Core 检查 Assignment Completion Contract 后才可以将 AgentRun 置为 COMPLETED。Coding Run 的完成可要求产生 Candidate Revision + Change Summary；Investigation Run 可要求 Findings + Evidence + Remaining Unknowns；Review Run 可要求 Review Findings。AgentRun COMPLETED 仍不等于 Verification PASS、Work Accepted 或 Delivered。

### Run 状态

Terminal Outcome 保持少而明确：COMPLETED、BLOCKED、PAUSED、CANCELLED、FAILED、INTERRUPTED、SUPERSEDED。等待原因作为 `waiting_reason`，例如 APPROVAL、OPERATION、USER、CHILD、RECONCILIATION。

### Context Manifest 与 Resume Capsule

每个 Epoch 从 Work Truth、Current Reality、Recent Interaction 重新构造 Context。Resume Capsule 只保存可公开的进度摘要、假设、Unknown、Pending Operation 和引用，不保存隐藏 Chain-of-Thought。

### No-progress Guard

Runtime 使用 deterministic signal 检测“没有新 Evidence、没有新 Change、Unknown 未减少、重复 Action Fingerprint”等无进展循环。达到 soft threshold 时要求模型换策略，再无进展则结束 Epoch，PAUSED/BLOCKED，而不是无限烧 Token。

### Child Run

Child Run 仅在问题可独立描述、可独立验证、并行收益明显、不会产生共享写冲突时创建。默认 Read-only；预算从 Parent 剩余 Resource Envelope 分配；返回 Findings/Evidence/Hypotheses/Unknowns，而不是完整 Transcript。

### Worktree Writer

一个 Worktree 默认最多一个 Praxis Active Writer。需要并行实现时使用独立 Worktree，而不是两个 Agent 在同一个目录做复杂文件锁。

# 第五章 Tool、Connector、Plugin 与外部能力运行时

Tool 与 Connector 必须分离：

> **Tool 是 Agent 可以请求的稳定能力契约；Connector 是 Praxis 如何连接某类外部系统的实现适配层。**

例如 `database.query` 是 Praxis Tool，可以由 DBX MCP Adapter、未来 Native DB Connector 或企业插件实现。Agent 不应该知道 DBX MCP 内部 tool name。

### ToolSpec

每个 Tool 必须 versioned，并声明：input/result schema、effect_class、required capabilities、scope resolver、resource profile、timeout、retry/idempotency、output policy、sandbox profile、secret requirements、reconciliation support。

Effect Class 至少区分 OBSERVE、LOCAL_MUTATION、REMOTE_MUTATION、CONTROL/DESTRUCTIVE。最终风险还要乘以 Environment Risk、Target、Resource、Assignment Risk。

### Effective Tool View

Model 每次只看到当前 Assignment、Capability Lease、Repo Scope、Environment、Tool Health、Risk Policy 允许的 Tool Catalog。没有权限的 Tool 默认不进入 Tool Schema，而不是等模型调用后才拒绝。

### Filesystem 与 Process

本地文件修改优先使用结构化 `fs.apply_patch(path, expected_base_hash, patch)`。若 base hash 已变化返回 STALE_INPUT。通用 Process 默认使用 `argv[] + cwd_ref + env_refs + timeout`，避免任意 shell string。真正 Shell 模式属于更高权限能力。

### Repository Command Registry

Build、Test、Typecheck、Lint、Package 等稳定工程命令由 Repo Configuration 定义成 typed CommandDefinition。它只是 command metadata，不扩展成 Workflow Engine。

### MCP

MCP 是 Transport/Extension Protocol，不是 Authority Model。新发现 MCP tool 默认 QUARANTINED，必须映射到 Praxis ToolSpec 与 Capability 后才能暴露。MCP Server 视为不可信执行组件，运行在 Connector/Plugin Sandbox 中；Tool Schema 中途变化导致 TOOL_SCHEMA_CHANGED，新 Epoch 才可使用新 Registry Revision。

当前 MCP TypeScript SDK v2 已作为 2026-07-28 规范的 stable release line，并支持 Node.js、Bun、Deno；Praxis 采用专门 MCP Host 进程接入，而不是把 SDK 嵌入 Core。

### Retry 语义

OBSERVE 可有界重试。Mutation 在 Dispatch 前确定未执行可重试；Dispatch 后连接断开等情况为 UNKNOWN_EFFECT，禁止 Connector 隐藏重试。ToolSpec 必须声明 safe_before_dispatch、safe_after_dispatch、idempotency、reconciliation。

### Plugin

v1 Plugin 默认 Out-of-process，只能 receive ticket → execute → return Observation。Plugin 不能直接写 Core DB、任意读取 Secret、向模型注入不可审计 System Prompt 或自行扩大网络/文件权限。插件升级若新增 Capability 请求，需要重新授权。

# 第六章 Git 与 Worktree Architecture

Git 是 externally mutable durable reality。用户可在 IDEA、Fork、CLI 或其它工具中随时修改，Praxis 不能成为 Git 唯一控制者。

### Git 对象分层

```text
Repository          逻辑工程资产
RepositoryInstance  当前机器上的一个 Git clone/object store
Worktree            该 instance 的具体 checkout
```

Repository Identity 不绑定 Local Path 或单一 Remote URL；Remote 是独立 binding。

### Backend

v1 Primary Git Backend 使用官方 Git CLI，上层通过稳定 Git Domain Interface 隔离。原因是 Worktree、Hook、Filter/LFS、Credential、Signing、Merge/Rebase 和 Remote 行为最终都以 Git CLI 为兼容基准。机器读取优先 porcelain/plumbing、NUL-delimited、稳定 format，不解析面向人的本地化文本。

### Git Observation 与 Preconditions

Watcher 只是 staleness hint。任何 Git Mutation 都携带 expected RepositoryInstance、Worktree、HEAD、Branch、Working State/Fingerprint 等 preconditions，执行前重新观察；变化则返回 STALE_REPOSITORY_STATE。

### Worktree Lease

Praxis 自身一个 Worktree 同时只授权一个 Active Writer，多读者可并发。Lease 无法阻止用户在外部 IDE 修改，因此仍必须依赖 watcher、hash、Git precondition 重新发现现实变化。

Worktree v1 purpose 收敛为 PRIMARY、WORK、RUN、REVIEW、INTEGRATION。Implementation 默认 WORK Worktree。

### Exact Base Revision

Template Branch 是 Policy，真正创建 Worktree 时先 resolve exact OID，之后 Work Base 不随 develop/main 移动而漂移。

### Candidate Snapshot

Verification 不能绑定 mutable branch/working tree。使用 Temporary Git Index 创建 immutable Candidate Snapshot：read-tree → add -A → write-tree → commit-tree → hidden Praxis candidate ref。全过程不污染用户真实 Git Index，并在 snapshot 前后重新观察，发现 Race 则拒绝。

Candidate Revision 保存 base OID、tree OID、candidate commit OID、working fingerprint；Verification 绑定 Candidate Revision。正式 Commit metadata 改变但 tree content 相同，不要求无意义地重新验证业务行为。

### Multi-Repo ChangeSet

ChangeSet Revision 是一组精确 Repository Candidate Revision，不创建 super-repo。Integration 使用各仓 INTEGRATION Worktree materialize 精确 Candidate Set；Integration PASS 不等于 Merge、Push、Deploy 或 Delivered。

### Git Hooks / Filters

Git Hook、filter、external diff、textconv 都视为潜在 executable surface。Git Worker 必须运行在 Sandbox/Policy 约束下，不能无条件继承 Praxis 环境或 Secret。

### Remote Operation

Fetch 是 Network + Local Mutation；Push 是 Remote Mutation。底层不把 `git pull` 当原子领域操作，而拆成 Fetch + Integration Strategy。Push Ticket 必须绑定 local OID、expected remote OID、remote ref。Push 断网可能 UNKNOWN，通过 ls-remote reconcile。

### Cleanup

Dirty Worktree 永远不自动删除。Remove Worktree、Delete Local Branch、Delete Remote Branch 是三个独立治理操作。

# 第七章 Repository Intelligence Architecture

Praxis v1 不建设“AI 语义代码知识库”，而建设可解释、渐进式、可删除重建的 Repository Intelligence Layer。

### 四层 Intelligence

- **L0 Repository Facts**：Git identity、HEAD、build/package manifests、language hints、modules、instruction sources、ignore/config files。
- **L1 File & Text**：file tree、path/name search、ripgrep-grade exact/regex search。
- **L2 Symbols**：轻量 parser 提取 definitions/imports/exports/rough references。
- **L3 Deep Language Intelligence**：按需 LSP/compiler/language analyzer，不是 Repository 可用性的前提。

Cold Start 即使完全没有 index，也必须可以 list/rg/read/Git search；Index 是 acceleration，不是 availability gate。

### Base Snapshot + Worktree Delta

同一个 Repo 的多个 Worktree 不重复全量索引。Base Index 绑定 Git Tree/OID；Worktree 仅维护 changed/new/deleted overlay。Tracked clean file 优先使用 Git Blob OID 作为 content identity；dirty/untracked 用内容 hash。Parse Cache 可按内容复用，但 Path/Module/Classpath semantic context 不能错误合并。

### Search/Mutation 边界

Search Hit 必须带 repository、worktree/snapshot、path/range、match type、content hash、freshness provenance。真正 Mutation 前必须直接重新 read 当前文件，验证 expected hash；Index 帮助定位现实，不是写入前最终真相。

### Incremental / Crash-safe Index

File watcher 只是 invalidation hint。大量 checkout/rebase/generator change 时采用 batch reconcile。Index build 使用 staging → validate → atomic publish，不能暴露半构建 snapshot。Index/Cache 全部属于 rebuildable data，不进入核心 backup。

### Impact Funnel

1. Workspace metadata / repo classification；
2. cheap lexical search；
3. structural search：definition/import/module/API client；
4. selective deep resolve；
5. 模型最后做 semantic interpretation。

No Evidence 不等于 Unaffected。Indexer 只提供可检索 Evidence Candidate，不能自己把搜索结果升级成业务影响事实。

### v1 Technology Boundary

v1 默认不要求 Persistent Full-text DB、Embedding/Vector DB、通用 Knowledge Graph。自然语言检索先通过 Model Query Reformulation 生成多个 lexical/symbol query，再使用 deterministic ranking。只有真实 Pilot 证明这些不足时才引入向量层。

### Trust Type

Repository instruction source、source code、document content、external content 必须保持不同 Context Trust Type。只有显式配置/识别为 instruction 的文件才进入 Instruction Context；普通 README、源码注释、日志中的“指令文本”都只是内容。

# 第八章 Environment、Database、Runtime Host 与 Deployment

Environment 不是 DEV/TEST/PROD 字符串，而是一个稳定 operational boundary。Site 与 Stage 是组织维度；Environment 自身拥有 stable ID 与 Risk Class。

```text
Site
└ Environment
   ├ DatabaseResource
   ├ RuntimeTarget
   │  └ Host/Node
   ├ LogSource
   └ DeploymentTarget
```

### Environment Context

Active Environment Context 只是当前 Work/Conversation 的默认资源解析焦点，不是 Capability Grant。同一个 Work 可以同时观察 TEST 与 PROD，每个 DB Observation、Log Observation、Deployment、Verification 都必须绑定自己精确的 Environment ID。

### Database Resource

Agent 使用 logical resource id，不看到 connection string/password。Connector 建立连接后必须验证实际 database/catalog/schema/read-only identity；配置宣称 TEST 但实际连到 PROD 时必须 RESOURCE_IDENTITY_MISMATCH fail closed。Production read 优先通过真实 read-only credential/session从底层保证，并附 timeout、row、bytes budget。

### RuntimeTarget 与 Host

RuntimeHost 是机器/SSH endpoint；RuntimeTarget 是用户有业务意义的运行目标，例如“MOM Backend / Zhongxin PROD”，可包含多个 node。这样未来可以替换 SSH Host 为 container/Kubernetes/service，而 Agent 上层仍调用 runtime.health/logs。

### LogSource

日志应作为一等配置资产，绑定 RuntimeTarget、node scope、provider、path/selector、query limits。Praxis 不建设全量 log archive，只保存与当前 Work/Verification 相关的 bounded observation/evidence。

### DeployableUnit 与 Artifact

Repository 与 DeployableUnit 分离：一个大型 backend repo 可以产生多个可交付单元。Build 后 Promote 的 Artifact 必须 immutable，身份由 hash + candidate/source provenance 决定；可变化的 `target/foo.jar` 只是来源路径，不是 artifact identity。

### Recipe / Target / Intent

- Deployment Recipe：怎么部署，有限 typed steps，不是 workflow engine。
- Deployment Target：部署到哪里，关联 Environment、RuntimeTarget、nodes。
- Deployment Intent：Exact Artifact + Recipe Revision + Target Revision + strategy。
- Deployment Attempt：实际执行一次副作用。
- Deployment Observation：重新观察到的真实 version/health/node state。

Execution exit 0 不直接证明 Deployment 成功。多 node 必须允许 IN_SYNC、PARTIALLY_APPLIED/MIXED、DRIFTED、UNKNOWN。v1 多 node 默认 serial，先一个节点 upload/activate/health/version 成功后再继续，避免一次性扩大故障面。

### UNKNOWN 与 Rollback

远程命令 Dispatch 后断线进入 UNKNOWN_EFFECT，先执行 read-only version/health/process/log reconcile，不自动重跑。Rollback 是新的 Deployment Intent，指向已知旧 Artifact，不改写历史；涉及 DB migration 时必须明确 rollback risk，不能假设旧 jar 能恢复数据库现实。

### Production Approval

Approval 必须绑定 exact Artifact、Recipe、Target、node set、重要 migration risk；任一重大变化使旧 Approval 失效。Environment Hard Policy 只能被下层进一步收紧，Work/Agent不能降低 Production minimum risk。

# 第九章 AI Provider、Routing、Context 与 Prompt Cache

AI Runtime 采用三分法：Routing Engine 决定“用哪个模型”，Context Builder 决定“模型能看到什么”，Model Gateway 决定“怎样调用 Provider”。

### Provider / Model / Profile

Provider Definition 管 endpoint、credential、network/proxy/TLS、data policy、health；Model Definition 管 provider model name、capabilities、context/output limits、cost/latency metadata；Model Profile 是用户和 Agent 引用的能力抽象，例如 fast、standard、coding、strong-coding、review、independent-review、vision。

### Deterministic Routing

v1 不使用 LLM Router。顺序固定为：Data Policy Eligibility → Required Capability → Environment/Governance → Profile Candidate Set → Health → Budget → Cost/Latency preference → deterministic tie break。数据政策是 Hard Filter，不能先选“最强模型”再尝试删除敏感输入。

### Typed Context

Canonical Context 内部保持 SYSTEM_POLICY、WORKSPACE_INSTRUCTION、REPOSITORY_INSTRUCTION、ASSIGNMENT_INSTRUCTION、USER_INTENT、DOMAIN_STATE、SOURCE_CODE、DOCUMENT_CONTENT、EXTERNAL_OBSERVATION、ASSISTANT_DERIVED、TOOL_SCHEMA 等 trust type。代码、日志、DB内容永远不会因为文本里写“忽略规则”而升级为 Instruction。

### Canonical Manifest → Provider Materialization

Context Builder 先生成 provider-neutral Context Manifest，再由 Provider Adapter materialize 成不同厂商的 system/user/tool/image/cache 表达。切换 Provider 不重新决定“该看哪些事实”，只改变协议表现。

### Exposure Manifest

每个 Model Call 记录 provider/model、context classification、source categories、production data 是否暴露、secret material 是否为 false、bytes/tokens 等元数据，用于回答“这次把什么类别数据给了哪个 Provider”，但不复制原始 Context。

### Secret 与 Data Eligibility

Secret 默认 NOT MODEL ELIGIBLE，不是“最高密级所以只有本地模型能看”。User Message、Repo 文件中可能出现 credential，Context Guard 使用已知 Secret exact match 和高置信 pattern 防止暴露。必需 Evidence 若不允许发送给当前 Provider，不得静默删除后继续回答；Routing 必须换合格 Route，否则 PAUSE/BLOCK。

### Context Budget

有效输入预算小于 Provider advertised context，必须预留 output、tool schema、protocol overhead、安全余量。Hard Policy、Objective、Capability、关键 UNKNOWN、Latest User Input 优先级最高，不能为了塞更多源码被 truncation 静默删除。

### Cache 三层

1. Praxis Content Cache：本地内容寻址，Provider 无关。
2. Context Materialization Cache：Canonical Segment 对某 Provider Family 的格式化缓存。
3. Provider Prompt/Session Cache：外部性能优化，必须服从 Data Policy，全部失效也不能影响正确性。

稳定前缀应尽量保持 System Policy → Tool Protocol → Workspace/Repo Instruction → Assignment Protocol/Objective；动态 Work State、retrieved code/evidence、conversation tail、latest trigger 放在后部。无意义 request UUID/current time 不进入稳定前缀。

### Model Result

Provider raw response 归一化为 ModelResult：assistant text、tool requests、structured output、usage、finish reason、provider metadata ref。Partial streamed tool call 不能边生成边执行，必须完整组装并 schema validate 后进入 Agent Protocol。隐藏 Chain-of-Thought 不持久化。

### Retry / Fallback / Escalation

Transport Retry、Transport Fallback、Capability Escalation、Independent Review 是四种不同语义。Independent Review 创建新 Assignment/Run，可要求不同 provider family 与独立 context；Agent 可请求 escalation，但不能直接指定具体 provider/model 来扩大预算或数据访问。

# 第十章 Resource、Security、Sandbox 与 Recovery

Praxis 的安全模型明确假设 Model、Repository Content、DB/Logs、MCP/Plugin 都可能错误、被注入甚至恶意。因此安全不能依赖“AI 会听话”。正式防护链为：Typed Context → Agent Intent → Core Capability/Policy/Resource → Operation Ticket → Supervisor → Sandboxed Worker → Scoped Credential → External Reality → Bounded Observation。

### 四层防线

1. Domain/Capability Policy；
2. Exact Operation Ticket；
3. Process/Resource Sandbox；
4. External System Native Security（read-only DB user、Host key、Git remote protection 等）。

### Sandbox Profile

Agent、model-gateway、indexer、build、git、db connector、ssh/deploy、plugin 使用不同 profile。Agent Worker 最贫穷：无 workspace fs、无 arbitrary process/network、无 secret。Model Gateway 只允许 provider network + provider credential。Indexer 默认无网。Build/Test 被视为执行不可信 project code，而不是天然安全读操作。

### Filesystem 与 Environment

Worker 只获得 explicit read/write roots、staging、tool caches；Home 不是默认 root。子进程使用 minimal environment，不继承 Core/GUI 的所有变量。Maven/pnpm cache 可以作为显式 Shared Tool Cache 挂载，但不属于 authoritative evidence。

### Credential Broker

Secret Store 通过 Credential Broker 按 Operation/Resource 最小化 materialize，优先 OS Keychain/Credential Manager/SSH Agent/handle/fd，而不是长期 env string。必须兼容 env 的 CLI 也只能在单次 Operation 最小环境中使用。所有输出经过 Sensitive Output Guard；当前 materialized secret 值可用于 exact redaction。

### Resource Envelope

统一覆盖 Wall Time、CPU priority、Memory、Process Count、Temp Disk、Diagnostics Disk、Tool Output、Model Calls、Input/Output Token、Cost、Child Runs、Concurrency、Network Transfer、Artifact Promotion。预算层级为 Application → Workspace → Work → Run → Epoch → Operation，子层不得超出父级剩余预算。Spawn/Child/高成本 operation 前先 reservation，而不是执行后才发现预算不足。

### Global Pressure

Resource Governor 观察整机 NORMAL/PRESSURE/CRITICAL。压力升高时优先停止后台 index、关闭 idle deep language session、暂停 child/background、收缩 buffers，再限制新非关键 operation。正在执行且难中断的 production mutation 不能因为“占内存最多”就随意 kill；OperationSpec 必须标明 interruptibility。

### Disk Pressure

State、Artifact、Diagnostics、Cache、Runtime、Worktree 分别计量。Soft pressure 清 temp/expired diagnostics/cache；Hard pressure 暂停大型 index、低价值 artifact promotion；Critical 禁止新大型 build/worktree create，但保留 emergency state capacity 以持久化 UNKNOWN/recovery 状态。Dirty Worktree 永远受保护。

### Process Tree

Supervisor 必须按 operation 管理完整 process tree；PID 之外还需要 instance id、spawn nonce/start time 防 PID reuse。重新启动后检测 orphan worker/process，依据 effect semantics terminate/reconcile。

### Sleep/Resume

Machine Resume 使 Provider/SSH/DB transient session 失效，外部 observation stale，重新评估 timeout 与 health。远程 mutation 跨 sleep 默认 UNKNOWN，除非存在可靠 external operation id 可查询。

### Core Recovery

启动顺序：profile lock → storage/schema/integrity → WAL/recovery mailbox → unresolved operation → interrupted run → orphan worker → invalidate transient session → rebuild critical projection if needed → recovery mode → safe reconciliation → normal mode。UI 可以较早 attach 并显示 Recovery，不要求整个应用黑屏等待。

### Database Corruption / Upgrade

核心 SQLite integrity 异常 fail closed 到 Recovery UI，禁止悄悄创建空数据库。Schema migration 前生成恢复 snapshot，失败不进入正常写模式。应用升级不得在安全关键 remote mutation 正在执行时后台重启。

### Kill Switch

分别支持 Stop New AI Work、Stop New Mutations、Revoke Production Authority、Stop Background Workers、Emergency Shutdown。Live hard overlay 只能收紧当前权限，不能作为中途扩大 Run 权限的旁路。

# 第十一章 物理技术架构与 Runtime Language Allocation

10.1-10.9 已经把逻辑边界冻结，10.10 的技术选型遵循一个原则：**Rust 承担安全、持久化、进程/OS、Git/SSH/Index 等稳定系统边界；TypeScript/Bun 承担高速变化的 Agent、Provider 与 MCP 生态。**

### 正式物理组件

```text
praxis-desktop        Tauri + React/TypeScript
       │ local bridge
       ▼
praxisd               Rust authoritative daemon
       │
       ├ praxis-native-worker   Rust multi-role operation worker
       ├ praxis-index-worker    Rust disposable index worker
       ├ praxis-agent           TypeScript/Bun epoch worker
       ├ praxis-model           TypeScript/Bun model gateway
       └ praxis-mcp-host        TypeScript/Bun MCP/DBX host
```

所有 sidecar/binary 以同一 Praxis Release Manifest 版本化和签名；Core 根据 protocol compatibility 拒绝不兼容 worker。

### Desktop Shell：Tauri 2

v1 选择 **Tauri 2.x**，当前研究快照中 Tauri core 2.11.5（2026-07-01）。Tauri 提供 WebView capability/permission 机制，可限制前端可调用命令；2.11.1 还包含远程 origin ACL 相关安全修复，因此工程基线必须 pin 到经过测试的最新安全 patch，而不是长期停留旧版本。

选择 Tauri 而非 Electron 的主要原因：Praxis 极度重视内存/磁盘/后台 worker 隔离；业务 Core 已独立成 daemon，不需要把 Node 权限放在桌面主进程；Tauri 让 desktop shell 更薄，并把安全/OS 边界自然放在 Rust。Electron 仍保留为 fallback shell：当前 Electron 44 已在 2026-08-25 stable，且 utilityProcess 很适合隔离 CPU/crash-prone Node worker，但其 bundled Chromium footprint 与 Praxis 的资源目标不如 Tauri 合适。

**Shell Swap Gate**：在 Alpha 前必须用真实 Workbench UI 做 CJK IME、Monaco/diff、大型虚拟列表、drag/drop、clipboard、多窗口、WebView memory、GPU/缩放测试。若系统 WebView 导致不可接受且不可修复的功能/性能差异，可将 shell 切换到 Electron；因为 authoritative Core/Worker 全部在 `praxisd` 外部，这个切换不重写系统内核。

### UI：React + TypeScript + Vite

选择 React 作为 Workbench Renderer，主要用于成熟的复杂桌面前端生态、虚拟列表、编辑/差异视图、可访问性原语与长期组件维护。最终 Design System、视觉组件库、具体像素稿仍不在 System Design 冻结；禁止为了图省事直接把通用卡片模板当 Praxis 视觉基线。

Monaco 作为 v1 Code/Diff Viewer 的首选，但必须 lazy load；Praxis 不做完整 IDE，因此编辑能力保持受控。Log/Tool Output 优先自研虚拟化 viewer，不因“有 SSH”就引入完整 Terminal/PTY 作为 v1 前提。

### Rust Core：Rust Stable + Tokio

`praxisd` 使用 Rust stable；2026-08-31 研究快照为 Rust 1.98.0（2026-08-20）。异步 I/O 使用 Tokio，工程基线优先选择当时仍受支持的 LTS minor line，而不是追逐每月 minor。Core 中所有 domain mutation、policy、operation journal、resource governor、supervisor、artifact metadata 与 IPC control plane 均在 Rust。

### TypeScript/Bun Sidecars

Agent Worker、Model Gateway、MCP Host 使用 TypeScript，默认 runtime 选择 Bun。2026-08 Bun 1.4.0 已发布，支持 macOS/Linux/Windows、单文件 executable、subprocess/IPC，并在 Linux 支持将子进程加入 cgroup。由于 1.4 刚经历大规模内部重写，**System Design 只冻结 Bun 作为默认 JS runtime，不在本章锁死具体 patch；11 Engineering Baseline 必须经过 worker crash/memory/provider/MCP soak test 后 pin exact version。**

AI 包的业务代码尽量保持 Node-compatible，避免把 Agent 语义绑定在大量 Bun-only API 上，保留 Node LTS 作为工程逃生通道。

### MCP

采用官方 Model Context Protocol TypeScript SDK v2 stable line（对应 2026-07-28 spec），运行在 `praxis-mcp-host`，不嵌入 Core。DBX 作为专用 Database Connector Adapter，Generic MCP 新 tool 仍须进入 Tool Registry/Capability 过程。

# 第十二章 IPC、Protocol、UI Bridge 与版本协商

Praxis 采用本地 RPC，不使用 localhost TCP 作为默认控制面。Unix 使用 Unix-domain/local socket，Windows 使用 Named Pipe/local socket abstraction。Rust 侧优先采用 Tokio + `interprocess` 类跨平台 local socket abstraction。

### Protocol 原则

- Control Plane 消息小型、typed、versioned、可调试。
- v1 wire format 选择 **length-prefixed JSON control envelope**；IDL 以 versioned JSON Schema 为 source of truth，并生成 Rust/TypeScript type/validator。
- 大型 Diff、Tool stdout、DB result、image、artifact 不走 Core JSON RPC；通过 bounded stream、artifact ref、spool token 等 Data Plane 获取。
- 所有请求携带 request_id、correlation_id、causation_id、work/run/operation id（适用时）、config revision。

### UI Bridge

WebView 不直接连接 daemon socket。Tauri Rust shell 只暴露极小的 daemon bridge：attach、request、subscribe、open-in、安全窗口/系统能力。Tauri capability 文件限制 WebView 可调用范围。UI 启动后：Get Snapshot(revision N) → Subscribe(after N)；发现 revision gap 直接 reload snapshot，不做复杂 patch 修复。

### Local Authentication

Unix socket 文件权限 / Windows Pipe ACL 限定当前用户，并叠加 per-profile local auth/challenge。协议 Ticket 本身 audience-bound、short-lived、scope-bound，不依赖“能连上 socket 就有所有权限”。

### Worker Protocol

Worker 启动时先握手 binary/protocol version、role、instance id、capabilities；Core 返回 worker session 与 resource/sandbox profile。版本不兼容直接拒绝。Worker 不允许自行改变 role。

### Protocol 演进

Release Manifest 声明 daemon protocol、worker protocol、storage schema、config schema、plugin API。Minor 版本允许 backward-compatible 新字段；breaking change 必须显式版本迁移，不允许通过“忽略未知错误”猜测执行高风险操作。

# 第十三章 State Store、Secret Store、Artifact Store 与文件布局

### SQLite

正式选择 Rust `rusqlite` 作为 Core SQLite binding；当前研究快照 rusqlite 0.40.2（2026-08-08），SQLite upstream 3.53.4（2026-07-24）。使用 bundled SQLite 以保证跨平台行为一致，不依赖用户系统 SQLite。单 writer DB actor/connection 执行 mutation，WAL 支持并发 read projection。Durability pragma 具体值在 Engineering Baseline 通过 crash test/benchmark 冻结，关键要求是 Operation Journal 的已提交 DISPATCHED 不能在普通 crash 中轻易丢失。

不引入 ORM。Schema 使用显式 SQL migration，Core 启动进行 schema_version / migration_history / integrity 检查。Backup 使用 SQLite-aware backup/snapshot，不在写入时简单 copy database file。

### Secret Store

Credential Broker 使用 OS native credential store。Rust 侧采用 `keyring-core` + 对应平台 native store，避免把 Secret 放进 `.praxis`、SQLite 普通表或 Provider Prompt。当前 keyring-rs 4.2.0 已提供 macOS、Windows 与 *nix native store 适配，但 exact crate/features 仍由 11 baseline pin。

### Artifact Store

Durable Artifact 使用 filesystem content-addressed store，SHA-256 作为跨工具一致的持久 hash。写入流程：runtime staging → hash/size/metadata → atomic rename/promote → SQLite metadata commit。Text diagnostics/large excerpts 可按策略 zstd compress，但 hash identity 基于定义好的 canonical/raw bytes 语义，避免压缩算法变化改变对象身份。

### 推荐数据目录

```text
profile/
├ state/
│  └ praxis.sqlite
├ artifacts/
│  └ objects/sha256/...
├ diagnostics/
├ cache/
│  ├ repository/
│  ├ parse/
│  └ model/
├ runtime/
│  ├ staging/
│  ├ recovery/
│  └ sockets/
└ locks/
```

Workspace Worktree 不强制放在 profile 数据目录，可由 Machine Config 指定，但所有权/清理遵守 Worktree Policy。

# 第十四章 Git、Search、Tree-sitter、Watcher 与 SSH 具体技术

### Git

使用用户机器的官方 `git` executable，不 bundle 一套独立 Git。Workspace Health 验证版本、worktree、credential、LFS/签名等能力；最低版本在 11 baseline 冻结。所有调用以 argv + structured porcelain/plumbing 方式执行，并由 Supervisor 管理 process tree。

### Text Search

Praxis bundle 一个已验证版本的 `ripgrep` sidecar 作为内部 deterministic search engine，避免依赖用户 PATH 上是否存在 rg。高层 `repo.search` 隐藏具体 CLI，结果分页/限量。

### Tree-sitter

基础 Symbol Parser 选择 Tree-sitter Rust binding。Tree-sitter 官方定位就是增量 parsing library，并可在语法错误场景保持有用 parse tree；query system 适合实现轻量 symbol/import pattern。v1 bundle 必需 grammar（Java、JavaScript、TypeScript/TSX、JSON、YAML/TOML 等），Vue/UniApp 使用 adapter 处理 SFC embedded region。Deep Semantic Resolution 仍通过 optional LSP/compiler adapter，不让 Tree-sitter承担它做不到的 type resolution。

### File Watcher

Rust `notify` stable line作为 cross-platform watcher hint；当前 stable 8.2.0。Watcher event 始终 debounce/coalesce，然后用 hash/Git reality reconcile，不把 event 本身当真相。

### SSH

v1 `SshBackend` 接口的首选实现为 Rust `ssh2` crate/libssh2，当前 0.9.6 支持 client、agent 等成熟接口且跨 Windows/macOS/Linux；它运行在独立 Connector/Native Worker 中，阻塞 API 不影响 Core async runtime。必须实现 strict host key validation、password/key/agent authentication、bounded command output、SFTP/upload、timeout、session cleanup。

SSH backend 被接口隔离；若 Alpha spike 证明 ProxyJump、新加密算法、Windows credential、host-key 或长期 session 等关键能力存在缺口，可替换为 pure-Rust Russh 或 platform OpenSSH backend，而不改变 RuntimeTarget/Tool Contract。

### PTY

v1 不以交互式 PTY Terminal 为核心路径。Build/Test/Git/SSH 默认 non-interactive pipes，便于 deterministic timeout、output budget 与 cancellation。完整 Terminal/PTY 作为后续能力。

# 第十五章 Platform Sandbox 与 Cross-platform 交付策略

三个桌面 OS 无法用完全相同的原语实现强隔离，因此 Praxis 明确报告 Security Capability Tier，而不是假装 `sandbox=true`。

### Windows

Alpha 第一优先平台。Supervisor 使用 Windows Job Objects 管完整 process tree、process count、memory/cpu-ish limits 与 kill-on-job-close；Worker 采用 minimal environment、明确 cwd/root、Credential Broker。Restricted Token/AppContainer 等更强 filesystem/network sandbox 作为 Tier 2 spike，不在未验证前宣称强隔离。

### Linux

优先利用 cgroup v2 做 memory/pids/cpu control；在可用内核上使用 Landlock 收紧 filesystem。Network namespace/seccomp 属 Tier 2 增强。Bun 本身支持 spawn 加入已有 cgroup，但资源控制仍由 Rust Supervisor 创建/授权，而不是 JS Worker自行决定。

### macOS

使用 process group、rlimit、minimal env、Credential Broker 和逻辑 root。由于稳定公开的 per-operation filesystem sandbox 能力不像 Linux cgroup/Landlock 那样直接，v1 不依赖私有 Seatbelt/sandbox-exec 作为产品安全承诺。更强隔离通过后续平台 spike 或 Remote Executor 实现。

### Security Tier

- Tier 0：仅逻辑 Capability/Policy；
- Tier 1：process/resource/env + 部分 filesystem containment；
- Tier 2：更强 filesystem/network sandbox；
- Tier 3：独立 VM/container/remote executor。

Workspace Health 显示当前机器真实 Tier。高风险 Policy 可以声明所需 minimum tier；能力不足时 fail closed 或降级，而不是显示“Fully sandboxed”。

### Platform Priority

v1 开发顺序：**Windows 11 x64 优先完成真实 MOM/MES Vertical Slice；macOS Apple Silicon 作为第二 Tier-1 桌面目标；Linux 保持可编译、可运行但不作为首个 Alpha 阻塞平台。** Cross-platform protocol、worker abstraction 和 filesystem path model 从第一天保持可移植，避免后期重写。

# 第十六章 Packaging、Release、Update 与 Binary Compatibility

Tauri Bundler 打包 desktop shell、`praxisd`、Rust native/index worker、Bun compiled sidecars、bundled ripgrep、Tree-sitter grammar/runtime 及前端静态资源。Bun 1.4 支持 single-file executable，Agent/Model/MCP sidecar 不要求用户单独安装 Node/Bun。

### Atomic Release Set

所有官方 binary 属于同一 release set：

```text
release-manifest.json
  app_version
  daemon_protocol
  worker_protocol
  storage_schema_supported
  config_schema_supported
  binary hashes
```

Core 启动前验证 official sidecar hash/version；不能让 desktop 已升级而 daemon/worker 留在不兼容版本继续做 Production Mutation。

### Update

可使用 Tauri bundler/updater 作为 distribution mechanism，但更新只负责“下载并准备新 release”，真正 restart 必须在安全点：无未解决的关键 remote mutation，或用户明确选择进入 controlled recovery。禁止后台 auto-restart 打断 Production deploy。

### Plugin 更新

Plugin 不跟官方 binary trust 混合。Plugin manifest/version/capabilities/hash 单独治理；新版请求更多权限需要重新授权。

### Crash Reporting

默认本地-first，结构化 `tracing`/worker diagnostics 有界保存并统一 redaction。v1 不默认向第三方 SaaS 上传完整 crash/log；用户导出 Diagnostic Bundle 时进行 secret/path/data redaction。可选 telemetry 以后单独设计。

# 第十七章 Physical Component Map 与依赖方向

推荐代码层依赖方向如下，实际 monorepo package 名在 11 Engineering Baseline 冻结：

```text
                    contracts / protocol
                           ▲
             ┌─────────────┼──────────────┐
             │             │              │
          praxisd     native-worker    js workers
             ▲             ▲              ▲
             │             │              │
       desktop shell   index/git/ssh   agent/model/mcp
             ▲
             │
          React UI
```

### Rust 侧逻辑模块

- `domain`：纯领域类型、状态转换、不依赖 OS/SQLite/Tauri。
- `store-sqlite`：rusqlite、migration、transaction。
- `core`：command handler、policy、config snapshot、operation/run scheduler。
- `supervisor`：process/resource/recovery。
- `ipc`：local RPC、auth、subscription。
- `artifact`：content store、staging/promotion/GC。
- `native-worker`：fs/process/git/ssh operation executor。
- `index`：rg/tree-sitter/notify intelligence。
- `desktop-shell`：Tauri bridge；不得反向成为 domain owner。

### TypeScript/Bun 侧

- `agent-worker`：Agent protocol、semantic loop、resume capsule、model/tool intent。
- `model-gateway`：provider adapters、materializer、usage/cache telemetry。
- `mcp-host`：MCP v2 client、generic quarantine、DBX adapter。
- `ui`：React Workbench。

### 依赖约束

Domain/Core 不依赖 Tauri/React/Provider SDK/MCP SDK。Provider/MCP sidecar 不依赖 SQLite。UI 不依赖 native DB layout。Worker 不引用 Product DB schema 进行写入。所有边界通过 versioned contracts/operation ticket/observation envelope。

# 第十八章 Failure Model、Recovery Matrix 与 Reconciliation

Praxis 把 Failure 视为正常输入，不把“崩溃”统一投影为 FAILED。

| 故障 | 结果 |
|---|---|
| WebView/UI crash | Core/Run继续，UI重连 snapshot + revision |
| Agent Worker crash | 当前 Epoch INTERRUPTED；新 Epoch RECOVERY |
| Model Gateway crash | ModelCall失败/可安全 transport retry；Core不受影响 |
| Index Worker crash | index stale/rebuild，无 domain data loss |
| Local read-only Tool crash | known failure，按 policy retry |
| Local Mutation Worker crash | 依据 precondition/actual state判断 known/unknown effect |
| DB read connector lost | Observation failed，通常可重试 |
| SSH/Deploy worker lost after dispatch | UNKNOWN_EFFECT → reconcile |
| Git push lost connection | inspect remote ref reconcile |
| Core crash | Supervisor/restart，Operation Journal + Recovery Mailbox + external reality reconcile |
| Whole machine crash | durable state恢复，所有 transient session失效，unresolved mutation优先 reconcile |

### Operation 两维模型

不能只用一个 `status`。应同时表达 Execution Outcome（COMPLETED/REJECTED/INTERRUPTED 等）与 Effect Knowledge（NO_EFFECT/KNOWN_EFFECT/UNKNOWN_EFFECT），再叠加领域结果（Git CONFLICTED、Deploy MIXED 等）。

### Cancellation

Cancellation 是 Intent，不是 rollback 证明。ModelCall/本地可杀 process 可以 CANCELLED；远程脚本已发出后停止观察，可能仍是 UNKNOWN。

### Reconciliation 优先级

Production unresolved mutation > foreground operation > active run > test reconciliation > background index/cache。Recovery Scheduler 也受 concurrency/rate limit，不能重启后同时对几十台生产服务器发起 SSH。

### Authority / Reality 不确定性

- **Authority uncertainty → DENY**。
- **External effect uncertainty → UNKNOWN**。

这两条是整个系统 Fail-closed 的核心，不允许互换。

# 第十九章 Performance、Backpressure 与大数据路径

Praxis 必须避免所有“默认无限队列/无限 stream/无限 session”。

### Control Plane vs Data Plane

Core 只处理小型 control metadata。Maven 300MB stdout、Git 1GB diff、SSH log stream、DB 20万行结果不通过 Core → SQLite → UI 链路。Worker 输出进入 bounded stream/spool；Core只记录 status、bytes、truncated、summary/artifact refs。

### Queue / Stream

所有跨进程 queue 有界。Stream 使用 credit/window/backpressure；消费者跟不上时执行 pause、sample、truncate、bounded spool，绝不让内存 queue 无限制增长。

### 优先级

P0 人类交互与安全关键恢复；P1 foreground Work；P2 Verification/Deployment；P3 background index；P4 diagnostics/GC。整机压力时先降级后台工作。

### Repository

Diff API 分 Repo Summary → File List → File Diff → Hunk/Range。Binary 只传 metadata/blob ref。Search 默认返回 refs/excerpt，不一次读取几十个完整文件。

### Agent

长期 Work 通过 Epoch 短激活实现；等待不占 Agent Worker；Context 只加载 Work Truth + relevant evidence/code + recent tail。Child result 返回结构化摘要和引用。

### Diagnostics

每 Run/Operation/Worker 都有 soft/hard quota；达到 hard limit 停止 retention，但在安全情况下继续 operation。Unbounded Session Accumulation 是 P0 defect。

# 第二十章 Architecture Conformance Baseline

以下规则必须转化成自动化架构门禁、contract tests、failure injection tests 或 code review rules，而不是只停留在文档：

### Authority / State

1. 只有 Core 可写 authoritative domain state。
2. Domain history 与对应 current state transition 原子提交。
3. UI/Worker 不直接写 SQLite。
4. Agent 不持有 Secret，不直接 Spawn Worker。
5. 所有 remote/local mutation 先 durable authorize/dispatch，再执行。
6. Model completion 只是 proposal；Run completion/Verification/Acceptance 分离。
7. Runtime 配置 snapshot 冻结；live hard policy 只能收紧。

### Operation / Recovery

8. UNKNOWN remote effect 禁止盲重试。
9. Cancellation 不等于 rollback。
10. Crash 后先 reconcile operation，再恢复依赖它的 Run。
11. Recovery Mailbox 输入必须验证 ticket/worker/schema/size。
12. Git/DB/Host 等 external reality observation 必须带 freshness。
13. External tool/manual change 只能记录 observation，不能伪造 Praxis operation history。

### Resource

14. 所有 queue/stream/staging 有界。
15. Raw tool/model stream 不进入 Domain Event Store。
16. Token/Cost/Output/Memory/Process/Disk/Child/Concurrency 均有 Resource Envelope。
17. Child budget 是 parent remaining budget 子集。
18. Global pressure 优先降级 index/background。
19. Dirty worktree 永远不被自动 GC。
20. State DB 有 emergency capacity 处理 critical recovery metadata。

### Security

21. Capability + Ticket + Sandbox + Credential least privilege 四层并存。
22. Source/DB/Log/MCP content 永远不能升级成 instruction。
23. Secret 默认不允许进入模型。
24. Production data provider eligibility 在发送前检查。
25. Host identity mismatch fail closed。
26. Plugin/MCP install 不等于 capability grant。
27. Tool schema change 不在当前 Epoch 静默生效。
28. Shell 是比 argv process.exec 更高权限能力。
29. Build/Test 视为 project code execution。

### Git / Worktree

30. Git 是外部可变现实，所有 mutation 带 precondition。
31. 一个 Worktree 默认一个 Praxis writer。
32. Candidate Snapshot 不污染用户 index，并检测 race。
33. Verification 绑定 immutable candidate，不绑定 branch。
34. ChangeSet 是 exact candidate set，不是 super-repo。
35. Push 等 remote mutation 断线必须 remote reconcile。
36. Hook/filter/external diff 都在 sandbox/policy 下执行。

### Repository Intelligence

37. Cold start 无 index 仍可工作。
38. Index/Cache 可删除重建。
39. Base snapshot 可跨 Worktree 复用，overlay 增量化。
40. Mutation 前直接 read + expected hash；Index不是最终写入真相。
41. No Evidence 不等于 Unaffected。
42. v1 不依赖 persistent vector DB。

### Environment / Deployment

43. Environment 是 stable ID + risk class，不是名字字符串。
44. Environment Context 不授予权限。
45. DB resource identity mismatch fail closed。
46. RuntimeTarget 与 Host分离。
47. Build Artifact immutable。
48. Recipe 与 Target分离。
49. Deploy Attempt 与 Observed State分离。
50. Multi-node允许 MIXED/PARTIAL/UNKNOWN。
51. Rollback 是新 operation。
52. Production approval 绑定 exact artifact/target/recipe/risk。

### AI / Context

53. Routing、Context、Gateway 分离。
54. Routing deterministic，data/capability hard filter first。
55. Provider-neutral manifest before provider materialization。
56. 必需 Context 不可发送时不能静默删除继续。
57. Cache 失效不影响 correctness。
58. Partial tool call 不执行。
59. Transport retry/fallback/escalation/review不同语义。
60. Provider Session 不是恢复/真相依赖。
61. Hidden chain-of-thought 不持久化。
62. Run provenance记录实际 model/provider/adapter/context/tool versions。

# 第二十一章 Vertical Slice 到物理组件的映射

09 冻结的唯一核心 Vertical Slice 映射如下：

1. **打开真实 MOM Workspace**：desktop → praxisd → Repository Registry → Git/Intelligence L0/L1。
2. **输入真实需求/问题**：Conversation durable message → Work/Assignment → Agent Epoch。
3. **定位 Repository**：repo.search/metadata/symbol → Impact Funnel → Candidate Repo Scope。
4. **调查 Test DB**：Agent intent → Core capability → DBX MCP host → database.query observation。
5. **创建隔离 Worktree**：Git Worker exact base OID → WORK worktree → write lease。
6. **AI 修改代码**：Agent → fs.apply_patch ticket → native worker → hash/precondition。
7. **Git Diff/Candidate**：Git CLI structured diff → temporary index candidate snapshot。
8. **本地 Verification**：Repository Command Definition → sandboxed process → bounded observation。
9. **Build Artifact**：candidate-bound build → immutable artifact promotion。
10. **Deploy TEST**：Artifact + Recipe + Target → Operation Ticket → SSH/native worker。
11. **Runtime Logs/Health**：RuntimeTarget/LogSource → safe observation。
12. **DB 结果验证**：DBX observation → Evidence Binding。
13. **PASS / FAIL / UNKNOWN**：Verification Engine 根据 Claim + exact revision/environment/evidence 记录结果。

如果这条链无法在真实 MOM/MES 工程上稳定完成，v1 不成立；不得用 Work Graph、Automation、更多 Agent 等旁支功能掩盖主链问题。

# 第二十二章 10.10 技术选型冻结结论与风险门

### 正式选型结论

| Area | v1 选择 | 备注 |
|---|---|---|
| Desktop Shell | **Tauri 2.x** | Shell 可替换，Core 独立；Alpha 前做 WebView Compatibility Gate |
| UI | **React + TypeScript + Vite** | Design System/组件库后续基线，不冻结视觉稿 |
| Core / Supervisor | **Rust stable + Tokio** | authoritative daemon、policy、state、process/resource |
| State DB | **SQLite + rusqlite bundled** | single writer、WAL、无 ORM |
| Artifact | **Filesystem CAS + SHA-256** | SQLite metadata，atomic promotion |
| Secret | **OS native keyring via Rust** | Credential Broker，不进 prompt |
| Agent Worker | **TypeScript on Bun** | per Epoch disposable；Node-compatible source |
| Model Gateway | **TypeScript on Bun** | Provider SDK/route materialization，独立 credential scope |
| MCP / DBX | **MCP TS SDK v2 on Bun** | Out-of-process host，DBX specialized adapter |
| Git | **System official Git CLI** | porcelain/plumbing，typed Git Domain API |
| Search | **Bundled ripgrep** | no persistent full-text requirement |
| Symbol | **Tree-sitter Rust** | lightweight index；deep LSP optional |
| Watcher | **notify stable** | hint only，hash/reconcile truth |
| SSH | **ssh2/libssh2 behind SshBackend** | cross-platform first choice；strict host key；Alpha spike gate |
| IPC | **Local socket/named pipe + versioned JSON control protocol** | high-volume out-of-band |
| Packaging | **Tauri bundle + official sidecars as atomic release set** | exact pins in 11 |
| Update | **signed whole-release update at safe point** | no hot sidecar drift |
| Sandbox | **OS-specific capability tiers** | Windows-first; strong remote executor later |

### 为什么不是 Electron-first

Electron 44 在 2026-08 已是成熟 stable，并提供 utilityProcess 等适合隔离 crash-prone Node worker 的机制；如果 Praxis 是一个 Node-centric 单进程桌面产品，Electron 会很合理。但 Praxis 已经明确需要独立 authoritative daemon、Rust OS/security/resource layer 和多个 sidecar，继续附带完整 Chromium/Node 主进程带来的资源成本收益比降低，因此 Tauri 为默认。

### 为什么不是 TypeScript-only Core

Core 要承担 durable operation ordering、SQLite single writer、OS process tree、sandbox/resource、secret broker、Git/SSH native worker、crash recovery。TypeScript 可以实现业务逻辑，但把这些安全/OS边界也交给 JS runtime 会扩大 crash/secret/process 权限面，并降低跨平台系统调用控制；因此 TypeScript 留在 AI 快速变化层，Rust承担稳定边界。

### 为什么不是 Rust-only

Provider SDK、MCP、模型协议与 Agent 生态变化速度远高于本地系统边界。强行用 Rust 重写所有 Provider/MCP adapter 会显著拖慢迭代，也更容易长期追不上生态。TypeScript/Bun sidecar 的权限很低，崩溃可重启，因此非常适合放 Nondeterministic Edge。

### 关键技术 Spike / Kill Criteria

在 11/12 进入完整开发前必须完成以下 spike：

1. **Tauri UI Gate**：CJK IME、Monaco 100k+ lines / large diff、虚拟列表、drag/drop、clipboard、多窗口、WebView memory。失败且无法修复则切 Electron Shell。
2. **Bun Worker Soak**：Agent/Model/MCP worker 连续启动/停止、内存回收、IPC、provider streaming、crash loop。若 1.4.x 不稳定，回退经过验证的 Bun patch 或 Node LTS，不改变 contracts。
3. **SSH Gate**：Windows/macOS/Linux password/key/agent、host key、SFTP upload、command timeout、disconnect → UNKNOWN/reconcile。ssh2 不满足则换 backend。
4. **SQLite Crash Gate**：authorized/dispatched operation 在 kill -9 / power-loss simulation 后不会错误回到“未执行”；WAL/pragma 由数据确定。
5. **Git Candidate Gate**：temporary index candidate 不污染真实 index，race/precondition/commit/push reconcile 在真实 repo 通过。
6. **Repository Scale Gate**：真实 backend + 多 worktree 的 rg/tree-sitter base+overlay 不产生重复全量索引或不可接受 RAM/Disk。
7. **Output Bound Gate**：模拟 1GB stdout / log stream，UI/Core/Agent memory 不随输入线性失控，hard cap可执行。
8. **Recovery Gate**：UI/Core/Agent/Connector/whole-machine-style crash injection 后，未解决 mutation进入 UNKNOWN/Reconcile而不盲重试。

### 版本策略

10.10 冻结“技术族与边界”，**不把今天的最新 patch 直接等同于开发基线**。11《Engineering Baseline v2》必须对每个依赖做 exact pin、checksum/lockfile、MSRV/runtime compatibility、security advisory、license、smoke test 后才正式锁版本。

# 附录 A：当前技术研究快照（2026-08-31）

以下仅用于解释 10.10 选型背景；真正 exact version 由 11 Engineering Baseline v2 锁定。

| 技术 | 研究快照 | 设计使用 |
|---|---|---|
| Tauri | core 2.11.5（2026-07-01） | 默认 Desktop Shell；capabilities/permissions |
| Electron | 44.0.0 stable（2026-08-25） | shell fallback 对照 |
| Rust | 1.98.0 stable（2026-08-20） | Core / Native Worker |
| SQLite | 3.53.4（2026-07-24） | Durable State engine |
| rusqlite | 0.40.2（2026-08-08） | Rust SQLite binding |
| Bun | 1.4.0（2026-08） | JS/TS sidecar candidate runtime |
| MCP TS SDK | v2 stable，2026-07-28 spec | MCP/DBX host |
| Tokio | 1.53.1 current；1.51.x LTS 到 2027-03 | Rust async runtime，baseline优先稳定/LTS |
| interprocess | 2.4.2 | Cross-platform local socket abstraction candidate |
| keyring-rs | 4.2.0 | native secret store candidate |
| notify | 8.2.0 stable | filesystem watcher hint |
| Tree-sitter | incremental parser/query architecture | lightweight symbols |
| ssh2 | 0.9.6 | SSH backend candidate |

### 公开资料

- Tauri releases: https://tauri.app/release/
- Tauri capabilities: https://v2.tauri.app/security/capabilities/
- Electron releases/schedule: https://releases.electronjs.org/
- Rust releases: https://blog.rust-lang.org/releases/latest/
- SQLite: https://www.sqlite.org/
- Bun: https://bun.sh/
- MCP TypeScript SDK v2: https://ts.sdk.modelcontextprotocol.io/v2/
- Tree-sitter: https://tree-sitter.github.io/tree-sitter/
- rusqlite: https://docs.rs/rusqlite/
- interprocess: https://docs.rs/interprocess/
- keyring: https://docs.rs/keyring/
- notify: https://docs.rs/notify/
- ssh2: https://docs.rs/ssh2/

# 附录 B：Deferred Decisions 与下一阶段输入

以下事项有明确接口边界，但不在 10 v0.1 继续展开：

- Exact Rust/Bun/Tauri/React/SQLite/crate/npm version 与 checksum；进入 11。
- React Design System、状态库、router、Monaco wrapper 等 frontend implementation detail；进入 11/真实 UI 实现。
- SQLite synchronous/page/cache 参数；以 crash/benchmark 进入 11。
- Windows AppContainer、Linux Landlock/seccomp、macOS stronger sandbox 的最终 Tier 2 实现；以平台 spike 决定。
- SSH backend 是否长期采用 ssh2、Russh 或 system OpenSSH；完成 Alpha gate 决定。
- Deep Java/TS/Vue Language Server 与 cross-worktree reuse；不是 v1 availability gate。
- Vector DB / Embedding / semantic reranker；只有真实 search failure evidence 才打开。
- Remote Executor；v1 保留 Operation/Worker protocol compatible extension point。
- Full Terminal/PTy、Full DB Client、Full Fork Feature Set；均不阻塞 v1。
- Team Server/RBAC/remote collaboration；不属于个人本地 v1。

### 对 11 Engineering Baseline v2 的冻结输入

11 必须把本文件变成 exact 工程约束：

1. Monorepo / Cargo + Bun workspace layout；
2. exact toolchain / dependency pins；
3. generated contracts / protocol compatibility；
4. CI build matrix与Windows-first acceptance；
5. architecture dependency rules；
6. worker/sandbox test harness；
7. failure injection / crash/reconcile suite；
8. security/secret/output redaction tests；
9. performance benchmark corpus（真实 backend/web/PDA repos）；
10. release packaging/signing/update baseline。

完成 11 和 12 后必须进入 Vertical Slice，不继续无证据扩张系统设计。

# 附录 C：术语表

- **Core / praxisd**：本地 authoritative daemon，唯一写入 Praxis Domain State。
- **Desktop Shell**：Tauri 宿主，负责窗口/OS UI 与 daemon bridge，不拥有业务状态。
- **Operation Ticket**：Core 对一项精确现实操作签发的不可扩大权限授权。
- **Capability Lease**：Run 在某 Scope/时间内最多允许请求的能力上限。
- **Resource Lease**：执行前预留的进程/内存/token/disk 等资源额度。
- **Observation**：对外部现实在某一时刻的带 provenance 观察。
- **Evidence**：Observation/Artifact 对 Verification Claim 的支持关系。
- **UNKNOWN_EFFECT**：外部副作用是否发生无法证明，需要 Reconciliation。
- **Run Epoch**：AgentRun 的一次短、有限、可恢复激活窗口。
- **Context Manifest**：模型调用使用了哪些本地 Context Fragment 的可审计清单。
- **Exposure Manifest**：某次 Provider 调用暴露了哪些数据类别/来源的元数据清单。
- **Candidate Revision**：Git 中 immutable、可验证的精确代码候选。
- **Environment Context**：当前交互所选 operational context，不等于权限。
- **RuntimeTarget**：用户有业务意义的运行目标，可包含多个 Host/Node。
- **Deployment Intent / Attempt / Observation**：想部署什么、执行了一次什么、现实最终观察到什么三个不同对象。
- **Rebuildable Intelligence**：可删除重建的 search/symbol/index/cache，不拥有业务 Truth。

