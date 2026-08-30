# Architecture Current State（as-built, M8）

本文是 **v1 实现现状的地图**：实现成的包图、port→实现对应、各包公共 API 面、
机器执法清单、文档索引。它只链接与汇总，不重述任何法则（一条事实一个家）：

- 设计权威（为什么这样划分）：`docs/02-system-design.md`
- 符合性规范（MUST/MUST NOT）：`docs/07-architecture-conformance.md`
- 机器边界：`.praxis/architecture.yaml`
- 实现层细节：`docs/subsystems/*.md`
- 决策记录：`docs/decisions/*`（ADR-0001…0013）

API 面摘自各包 `src/index.ts`（阅读日期 2026-08-30）；变更以代码为准，本文随后更新。

## 1. As-built 包图

```text
                contracts  （durable 契约 + ports，唯一 zod 运行时依赖）
                    ↑
                   core   （reducer / agent-loop / context / capability / extensions host）
        ┌─────────┬───────┴────────┐
 provider-openai  store-sqlite   tools-local      （adapters：实现 contracts 的 ports）
        └─────────┴───────┬────────┘
                     apps/cli            （composition / UX，无第二套 runtime state）

  dev-side：testkit（over contracts+core，ScriptedModel/事件工厂/内存 store）
            extensions（standing-orders、telemetry —— core host 的可选观察者/命令贡献者）
```

依赖方向由 `tests/boundaries.test.ts`（ADR-0002 + 精确锁定的依赖方向断言）与
`mise run test:architecture`（import graph 扫描）机器执法；`ai:guard` 按任务
合同逐 commit 检查改动边界。

## 2. Port → 实现对应

| Port（contracts） | 实现 | 说明 |
| --- | --- | --- |
| `EventStore` | `store-sqlite.openSessionStore(path)` → `SqliteEventStore` | 单事务乐观并发 append、逐行 schema 重校验、WAL；损坏/恢复策略见 `docs/11` |
| `ModelProvider` | `provider-openai.OpenAIChatProvider` | Chat Completions 流式 adapter；逃逸法则（§10）+ `providerOptions` 透传（M7-T011）+ 同 id tool 事实合并（M7-T012） |
| `ToolDefinition` | `tools-local.localReadTools / localWriteTools` | read（list_dir/read_file）与 write（write_file/bash，capability 强制 + reconciliation 钩子） |
| Extension host | `core.extensions` + `extension-telemetry` / `extension-standing-orders` | 只读观察 / fail-closed 操作员命令贡献（ADR-0013） |

测试侧等价物：`testkit.ScriptedModelProvider`（确定性模型脚本）、
`testkit.inMemoryEventStore`、`testkit/session-events` 事件工厂——全部走
production ports，无平行实现语义。

## 3. 公共 API 面（per package）

### `@praxis/contracts`
- Durable 词汇：`sessionEventSchema` + `SessionEvent`/`SessionEventUnion`（Session/Turn/Model/Tool/Epistemic 全集，`EVENT_SCHEMA_VERSION`）；信封 `EventEnvelopeBaseSchema`
- Ports：`EventStore`（append/readStream/listSessions/close）、`ModelProvider`（唯一流式 `complete`）、`ToolDefinition`（含 `requiredCapability`、reconcile 钩子）、`ModelRequest`（含 `providerOptions`）
- 词汇/常量：`TOOL_EFFECTS`/`ToolEffectSchema`、`ToolExecutionStatus`、branded ids（`asEventId`/`asTurnId`/`asToolExecutionId`…）、`EMPTY_STREAM_HEAD_SEQ`
- 能力模型：capability requirement/decision 类型
- 唯一运行时依赖：zod（`docs/09` 事实表）

### `@praxis/core`
- Loop：`runTurn`（唯一 turn 执行器；`AgentLoopDeps`、`DEFAULT_TURN_GUARDS`、`providerOptions` 透传 M7-T011）
- State：`foldSessionEvents`（唯一转换权威）、派生投影 `projectConversation`/`projectEpistemicBrief`
- Context：`buildContext` + `DEFAULT_CONTEXT_BUDGET`（六 cap、确定性压缩、fail closed）
- Capability：`capabilityAuthorizer`、`capabilityPolicyConfig`/`capabilityDecision`/`capabilityPolicySummary`
- 恢复：`invalidatePlansFalsifiedByHypotheses`、reconciliation/recovery 报告类型（§17 编排）
- 工具运行时：`validateToolDefinitions`、`retryPolicyForEffect`/`EffectRetryPolicy`
- `providerOptions` 语义见 run-turn 文档注释（请求个性化；runtime 法则永不依赖）

### `@praxis/provider-openai`
- `OpenAIChatProvider`（`options: { apiKey, baseUrl?, fetchImpl?, maxRetries?, initialRetryDelayMs?, timeoutMs? }`）、`FetchLike`、`OpenAIChatProviderOptions`

### `@praxis/store-sqlite`
- `openSessionStore(path)` → `SessionStore`（`EventStore` + `SessionSummary` 元数据投影）；`bun:sqlite` 惰性绑定（Node 下导入安全，开库需 Bun）

### `@praxis/tools-local`
- `localReadTools(root)` / `localWriteTools(root)`、单件 `readFileTool`/`listDirTool`/`writeFileTool`/`bashTool`、`truncateContent`、options 类型

### `@praxis/testkit`（dev）
- `ScriptedModelProvider`（`ScriptItem` 脚本：每次 `complete` 消费一个流脚本）、`inMemoryEventStore`、`session-events` 工厂、`TEST_SESSION_ID`

### `@praxis/extension-*`（可选）
- `extension-telemetry`：只读 observer（usage/step 事实 → 消费者回调）
- `extension-standing-orders`：fail-closed 操作员命令贡献

### `apps/cli`
- `run` / `sessions` 命令；脚本文件 provider 与 `--model` 真实端点；组合层（快速上手见 M8-T002 的 quickstart）

## 4. 机器执法清单

| 执法 | 机器 | 出处 |
| --- | --- | --- |
| 依赖方向 + deep-import + 环 | `test:architecture`（import graph 扫描） | docs/07 §3.1、architecture.yaml |
| 包依赖 allowlist + 精确锁 | `tests/boundaries.test.ts` | ADR-0002 |
| 任务改动边界 | `ai:guard`（Task Contract allowed/forbidden paths） | docs/06 |
| 质量门 | format/lint/typecheck/unit/integration/property/replay/fault/security/build/knip + store/cli（mise check:all） | `.praxis/quality-gates.yaml` |
| Core 覆盖地板 | `test:coverage` thresholds（`packages/core/src/**` stmts ≥95 / branches ≥90） | M7-T010 |
| 死代码/幽灵导出 | knip（零发现） | M7-T006 |
| 规模 tripwire | soak：context 恒界、注册表恰好线性、每事件折叠成本 ≤10× | M7-T003、docs/10 |
| 对抗面 | fault 27（崩溃矩阵/逃逸法则/工具与扩展故障）+ security 40（密钥禁锢/capability 绕过/bash 边界） | M7-T002 等 |
| 运行时法则 | reducer 拒绝非法转换（Command≠Event、verification 不 fail-open、indeterminate≠failed、完成阻断）——由 property/fault/replay 套件钉死 | docs/02 §24 |

## 5. 文档索引（哪类事实住在哪）

| 文档 | 持有 |
| --- | --- |
| `docs/01`（概览）/ `docs/02` | 设计目标与法则权威 |
| `docs/03` | 里程碑计划与质量门勾选（现状进度） |
| `docs/04`（仓库指南）/ `AGENTS.md` | 协作与standing orders |
| `docs/05-acceptance-strategy` | 验收制度 |
| `docs/06-ai-development-control-plane` | 控制面命令与 AI 开发循环 |
| `docs/07-architecture-conformance` | 符合性规范（MUST/MUST NOT） |
| `docs/08-ai-model-development-strategy` | 开发模型选型与 eval 轴 |
| `docs/09-dependency-inventory` | 依赖五事实表 + 允许清单（drift guard） |
| `docs/10-memory-context-growth` | 增长模型报告 |
| `docs/11-sqlite-corruption-recovery` | 损坏/恢复策略 |
| `docs/12`（本文） | as-built 地图 + API 面 + 执法清单 |
| `docs/subsystems/*` | 各包实现层细节 |
| `docs/decisions/*` | ADR-0001…0013 |
| `docs/acceptance/*` | 里程碑验收合同（M0–M8） |
| `evals/development-models/BASELINE.md` | 正式 eval 矩阵 + 基线记录 |
