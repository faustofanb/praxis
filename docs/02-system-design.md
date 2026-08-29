# Praxis Harness v1 系统设计文档

**文档类型：实施级 System Design**  
**状态：Development Baseline**  
**目标读者：**实现 Core、Store、Provider、Tool、CLI 的工程师与 AI 编码 Agent。

> 本文描述“当前应该实现什么”。理论依据参见 `00-praxis-whitepaper.md`；设计原因参见 `docs/decisions/`。代码若与本文冲突，应先判断是代码缺陷还是本文已过时，再通过 ADR/文档变更明确解决，禁止默默分叉。

---

# 1. 系统目标

Praxis Harness 是一个以用户目标为最高目的、以外部现实为最终检验标准的 Agent Runtime。v1 必须做到：

1. 模型可以在有限上下文中提出工具行动；
2. 工具行动经过确定性 Runtime 权限检查；
3. 外部副作用有明确生命周期与失败语义；
4. 每个重要事实写入可重放 Event Store；
5. Session 可以在进程重启后恢复；
6. `UNKNOWN`/不确定副作用不会被错误重试；
7. Observation / Hypothesis / Plan / Challenge 可以显式记录；
8. Agent Loop 的行为可以通过确定测试替身完整集成测试；
9. 简单请求不强迫走复杂多 Agent/治理流程；
10. Core 不绑定 OpenAI、SQLite 之外的具体适配器实现（SQLite 也只在 adapter package）。

## 1.1 v1 非目标

本文设计**不要求**：

- 内建 Multi-Agent 调度系统；
- 实时“主要矛盾”AI 分类器；
- 独立 Critic/Judge Agent；
- 云端 App Server/IDE 协议；
- Workflow DSL；
- 自动修改系统宪法/Policy；
- 企业级分布式数据库；
- Exactly-once 外部副作用承诺；
- 长期自治生产运维。

---

# 2. 设计原则

## 2.1 Deterministic Core, Nondeterministic Edge

LLM 和外部环境允许不确定；以下内容必须确定：

- 状态机；
- Event append / replay；
- Capability 决策；
- Tool 生命周期；
- Session seq；
- `UNKNOWN` 语义；
- Context budget；
- Goal hard constraints；
- 关键状态转换。

## 2.2 One Fact, One Authority

同一个事实只有一个权威来源：

- 历史事实：Event Store；
- 当前状态：由 Event Stream 纯函数/受控 reducer 派生；
- 权限：CapabilityPolicy；
- 模型可见 Policy：从同一 Runtime state 投影；
- 外部副作用事实：Tool Result / Reconciliation Observation。

禁止出现：

```text
config=A
runtime=B
model believes=C
```

却没有明确谁是真实来源。

## 2.3 Commands Are Intent; Events Are Facts

`ExecuteTool` 是意图；`ToolSucceeded` 才是事实。Command 不允许直接写进 Verified Knowledge。

## 2.4 Fail Closed on Governance/Verification Failure

审批/验证机制不可用时，不得默认成功；高风险动作进入 paused/blocked，而不是绕过。

## 2.5 Start Simple, Escalate on Evidence

默认使用最低充分复杂度。只有真实 evidence 证明问题跨域、风险高或当前路径不足，才升级到完整 Praxis 流程。

---

# 3. 顶层架构

```text
┌─────────────────────────────────────────────┐
│                 Product Layer               │
│  apps/cli · Task Routing · Human I/O        │
└────────────────────┬────────────────────────┘
                     │
┌────────────────────▼────────────────────────┐
│                  Praxis Core                │
│                                             │
│  SessionRuntime                             │
│  AgentLoop                                  │
│  StateReducer                               │
│  ContextBuilder                             │
│  ToolRuntime                                │
│  CapabilityPolicy                          │
│  Extension Seams                           │
└───────┬──────────────┬──────────────┬───────┘
        │              │              │
        ▼              ▼              ▼
  EventStore      ModelProvider    Tool Providers
   (port)           (port)           (ports)
        │              │              │
        ▼              ▼              ▼
 SqliteStore      OpenAIAdapter    Local Tools
        │                             │
        └──────────────┬──────────────┘
                       ▼
                   Environment
```

所有外部实现都通过 `contracts` 中定义的 Port 接入。`core` 不能 import `openai`、`bun:sqlite` 或具体本地工具。

---

# 4. Workspace 与模块职责

## 4.1 `packages/contracts`

**定位：**系统公共协议与数据模型，原则上无 I/O。

职责：

- Branded IDs：`SessionId`, `EventId`, `TurnId`, `StepId`, `ToolExecutionId`；
- Event Envelope / Event Payload schema；
- `EventStore` port；
- `ModelProvider` port；
- `ToolDefinition` / `ToolHandler` port；
- `CapabilityPolicy` port；
- Goal / Constraint / Observation / Hypothesis / Plan / Challenge / Verification 类型；
- Tool effect class / execution result；
- runtime config schema；
- Extension hook contracts。

约束：

- 不得读文件、网络、数据库、环境变量；
- 不得 import 其他 workspace package；
- Zod 是唯一允许的核心 runtime dependency；
- schema 是持久化边界，变更需要 schema version 与 migration 策略。

## 4.2 `packages/core`

**定位：**确定性 Agent Runtime。

职责：

- `SessionRuntime`：启动/恢复 Session；
- `StateReducer`：Event -> DerivedState；
- `AgentLoop`：Turn/Step 生命周期；
- `ContextBuilder`：有限上下文投影；
- `ToolRuntime`：Tool proposal/authorization/execution/reconciliation 协调；
- `CompletionPolicy`：是否允许 Turn/Session 完成；
- Extension hook 执行；
- 取消/暂停/继续；
- 单 Session 单写者序列化。

约束：

- 只依赖 `contracts`；
- 不依赖 provider/store/tool adapters；
- 不读取 secrets；
- 所有 side effect 通过 Port；
- 重要状态改变必须产出 Event。

## 4.3 `packages/store-sqlite`

**定位：**Event Store 的本地 SQLite 实现。

职责：

- SQLite 打开与配置；
- migration；
- session metadata；
- append event transaction；
- `loadEvents(sessionId, afterSeq?)`；
- event ID/seq 唯一性；
- health/checkpoint；
- fixture DB 支持。

约束：

- 使用 Bun `bun:sqlite`；
- append-only：普通代码没有 UPDATE/DELETE event API；
- migration 必须单调版本号；
- schema 变更要有旧 fixture replay test；
- v1 不做自动 compaction 删除历史。

## 4.4 `packages/provider-openai`

**定位：**OpenAI ModelProvider adapter。

职责：

- 将 Praxis `ModelRequest` 转换为 OpenAI **Chat Completions** 请求（"OpenAI-compatible" 生态的事实标准 wire 格式，`finish_reason` 与 v1 完成原因一一映射；不采用 Responses API——兼容端点普遍未实现，理由与映射细节见 `docs/subsystems/provider-openai.md`，未来可在同一 Port 后新增 Responses adapter）；
- streaming 转换为统一 `ModelEvent`；
- Tool schema 映射；
- usage/finish/error 映射；
- cancel/timeout；
- provider-specific error taxonomy。

约束：

- Core 不知道 OpenAI SDK 类型；
- Provider-specific raw payload 可作为 telemetry debug data，但不可污染 Core state；
- API 变更仅在 adapter 内消化；
- 真实 API 测试属于 eval/e2e，默认 CI 使用 ScriptedModel。

## 4.5 `packages/tools-local`

**定位：**v1 本地工具实现。

首批工具：

1. `read_file`：read-only；
2. `write_file`：reconcilable write；
3. `bash`：高风险、需 capability；
4. 可选 `list_dir`：read-only。

职责：

- Tool schema；
- effect class；
- 参数校验；
- path policy；
- timeout/cancel；
- result normalization；
- reconciliation（能做时）；
- tool-specific telemetry。

约束：

- 工具不能自行修改 Session State；
- 只能返回结果，由 Core 追加 Event；
- shell 工具必须有 cwd、timeout、output truncation；
- v1 默认 workspace root 外读写受限。

## 4.6 `packages/testkit`

职责：

- `ScriptedModelProvider`；
- `FakeTool` / `IndeterminateTool`；
- in-memory EventStore；
- event fixture builder；
- crash injection points；
- replay assertion helpers；
- fake clock / deterministic IDs。

不进入生产依赖。

## 4.7 `apps/cli`

**定位：Composition Root。**

职责：

- parse args；
- load/validate config；
- load secrets；
- instantiate SQLite/OpenAI/tools/policy/core；
- human approval UI（v1 可最简）；
- stream events to terminal；
- session create/resume/list；
- exit codes。

CLI 不放领域逻辑。

---

# 5. 领域模型

## 5.1 Goal Stack

v1 保持轻量：

```ts
type GoalState = {
  need?: string;
  goal: string;
  constraints: readonly HardConstraint[];
  strategy?: string;
  mission?: string;
};
```

- `goal`：当前高层任务目的；
- `constraints`：不可由 local metric 覆盖；
- `strategy/mission`：可被新证据修改；
- v1 不把 Goal Stack 做成复杂树。

## 5.2 Observation

表示从 Tool/用户/Runtime 外部取得的事实材料（v1 实际契约，ADR-0012）：

```ts
type ObservationSource =
  | { kind: "tool"; toolExecutionId: ToolExecutionId }
  | { kind: "user" }
  | { kind: "system"; detail: string };

type Observation = {
  observationId: ObservationId;
  source: ObservationSource;
  claim: string;
  evidenceEventIds: readonly EventId[];
  observedAt: number; // envelope.occurredAt of the recording event; payload 不携带时间
};
```

Observation 不自动等于 Verified Claim。

## 5.3 Hypothesis

```ts
type HypothesisStatus =
  | "proposed"
  | "supported"
  | "falsified"
  | "superseded";

type Hypothesis = {
  id: HypothesisId;
  statement: string;
  status: HypothesisStatus;
  support: readonly EventId[];
  conflicts: readonly EventId[];
};
```

v1 不使用模型生成的浮点 confidence 作为真理依据；可选显示 confidence，但 reducer 不依赖其值做安全决策。

## 5.4 Plan

Plan 是**当前行动假设**，不是 TODO 清单（v1 实际契约，ADR-0012）：

```ts
type Plan = {
  planId: PlanId;
  goalRef: string;
  focus?: string;
  hypothesisId?: HypothesisId;
  nextAction: string;
  falsifiedIf?: string;
  status: "active" | "invalidated" | "superseded";
};
```

v1 无 `"completed"`：事件词汇表（§6.2）没有任何事件产生它，plan 的完成是 session 级事实（`SessionCompleted`）。新的 `PlanSet` 自动将旧 active plan 置为 `superseded`。

**证伪 → 失效的运行时决定**（M4-T003）：reducer 记录证伪事实但绝不自动失效（§6.2 法则）；`runTurn` 入口运行确定性 pass——active plan 的 hypothesis 已 falsified/superseded 即追加一条 `PlanInvalidated`（reason 引用假设 id 与状态）。决定不依赖模型自觉（白皮书 Core Rule："Evidence can invalidate plan"），幂等可重放；新计划由模型自己的 `PlanSet` 到来。

## 5.5 Challenge

```ts
type Challenge = {
  id: ChallengeId;
  targetType: "hypothesis" | "plan" | "completion" | "policy";
  targetId: string;
  claim: string;
  evidenceEventIds: readonly EventId[];
  status: "open" | "accepted" | "rejected" | "resolved";
};
```

Challenge 是一等事实，不要求存在 Critic Agent。

---

# 6. Event Store

## 6.1 Event Envelope

建议：

```ts
type SessionEvent<TType extends EventType, TPayload> = {
  id: EventId;
  sessionId: SessionId;
  seq: number;
  type: TType;
  schemaVersion: number;
  occurredAt: number;
  actor: EventActor;
  causationId?: EventId;
  correlationId?: string;
  payload: TPayload;
};
```

### 必须满足的不变量

- `(session_id, seq)` 唯一；
- `event_id` 全局唯一；
- seq 从 1 单调递增，不允许洞由正常 append 产生；
- Event immutable；
- replay 不执行外部副作用；
- 同一 event stream + 同一 reducer 版本必须得到确定 state（若迁移，先转换 schema）；
- Event timestamp 不决定顺序，`seq` 才决定顺序。

**版本窗口与迁移法则（M5-T003）**：加载持久化流是一等边界解析，不是类型断言。`@praxis/contracts` 提供 `parseReplayStream`/`parseReplayEvent`：先以 envelope 基 schema 校验身份，强制 `1 <= schemaVersion <= EVENT_SCHEMA_VERSION`——更高版本的流（更新运行时写入）在加载时 fail closed（`FutureSchemaVersionError`），绝不进入 reducer 静默折叠；再按连续递增的步进迁移表（`SESSION_EVENT_MIGRATIONS`，每步 `fromVersion: i+1`，缺步/跳步即 `InvalidMigrationTableError`）把事件从声明版本迁到当前版本，版本号由管线盖章而非 transform 自报；最后整体过 `SessionEventUnionSchema`。每次 schema 升级恰追加一步迁移，且全部历史 fixture 必须折叠到同一 derived state（迁移 drill 钉死于 `tests/contracts-replay.test.ts`）。回放 fixture 集合以 `tests/fixtures/replay/index.json` 清单为唯一权威：每条记录 file/schemaVersion/事件数/终态，replay 门逐条经缝隙加载、折叠到记录终态并双折叠一致，清单与目录双向完备；回归会话集合的开篇 fixture（`regression-long-session-v1.json`，493 事件）由确定性构造器再生并以规范化 JSON 相等 pin（文件本身经 biome 格式化，pin 比较规范化形式，任何字段漂移即破）。

## 6.2 v1 Event Vocabulary

建议首批：

### Session/Turn

- `SessionCreated`
- `SessionResumed`
- `TurnStarted`
- `TurnCompleted`
- `SessionCompleted`
- `SessionPaused`

### Goal / Epistemic

- `GoalSet`
- `ObservationRecorded`
- `HypothesisProposed`
- `HypothesisStatusChanged`
- `PlanSet`
- `PlanInvalidated`
- `ChallengeRaised`
- `ChallengeResolved`
- `VerificationRecorded`

### Model

- `ModelRequestStarted`
- `ModelResponseCompleted`
- `ModelRequestFailed`

### Tool

- `ToolProposed`
- `ToolAuthorized`
- `ToolRejected`
- `ToolStarted`
- `ToolSucceeded`
- `ToolFailed`
- `ToolIndeterminate`
- `ToolReconciled`

不要为每个 UI 动画、debug log 创造 durable event。

## 6.3 SQLite Schema

```sql
CREATE TABLE sessions (
  id TEXT PRIMARY KEY,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  head_seq INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL
);

CREATE TABLE events (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  seq INTEGER NOT NULL,
  type TEXT NOT NULL,
  schema_version INTEGER NOT NULL,
  occurred_at INTEGER NOT NULL,
  actor_json TEXT NOT NULL,
  causation_id TEXT,
  correlation_id TEXT,
  payload_json TEXT NOT NULL,
  FOREIGN KEY(session_id) REFERENCES sessions(id),
  UNIQUE(session_id, seq)
);

CREATE INDEX events_session_seq
  ON events(session_id, seq);
```

`head_seq` 是缓存/metadata，不是事件事实的替代；更新必须与 append 同事务。

---

# 7. State Reducer

Reducer 是 Pure Function：

```ts
reduce(state, event) -> nextState
```

不得：

- 访问网络；
- 读当前时间；
- 生成随机数；
- 写 DB；
- 调模型；
- 依赖环境变量。

所有不确定输入必须先作为 Event 进入。

Derived State 至少包括（v1 实际形状，ADR-0012——`observations`/`plans`/`challenges` 注册表是法则执行所需：id 唯一性、终态目标拒绝、Challenge 目标校验）：

```ts
type DerivedSessionState = {
  status: SessionStatus;
  headSeq: number;
  currentTurnId?: TurnId;
  goal?: GoalState;
  observations: ReadonlyMap<ObservationId, Observation>;
  hypotheses: ReadonlyMap<HypothesisId, Hypothesis>;
  plans: ReadonlyMap<PlanId, Plan>;
  activePlan?: Plan;
  challenges: ReadonlyMap<ChallengeId, Challenge>;
  openChallenges: readonly Challenge[];
  toolExecutions: ReadonlyMap<ToolExecutionId, ToolExecutionState>;
  lastVerification?: VerificationResult;
};
```

大 Session 后期可加 snapshot；v1 先 replay 全事件，使用 soak 数据决定是否需要。

---

# 8. Tool Runtime

## 8.1 Tool Definition

v1 实际契约（非泛型：输入经 `inputSchema` 从 `unknown` 解析，输出是 opaque JSON 事实，见 ADR-0011）：

```ts
type ToolEffect =
  | "read_only"
  | "idempotent_write"
  | "reconcilable_write"
  | "non_idempotent_write";

type ToolExecutionOutcome =
  | { status: "succeeded"; resultJson: string }
  | { status: "failed"; error: { message: string } }
  | { status: "indeterminate"; reason: string };

// 同一认知规则：succeeded/failed 断言外部效果确实发生/确实未发生；不足为证保持 indeterminate。
type ReconciliationOutcome = ToolExecutionOutcome;

interface ToolDefinition {
  name: string;
  description: string;
  inputSchema: z.ZodType<unknown>;
  effect: ToolEffect;
  parametersJson: string; // 广告给模型的 JSON Schema（Core 不解析）
  execute(ctx: ToolExecutionContext, input: unknown): Promise<ToolExecutionOutcome>;
  reconcile?(ctx: ToolExecutionContext, input: unknown): Promise<ReconciliationOutcome>;
}
```

约束（ADR-0006/0011，注册时由 `validateToolDefinitions` fail-closed 强制）：

- `reconcilable_write` 必须定义 `reconcile`，否则拒绝注册；
- `reconcile` 只做验证（查外部状态/比对），不得产生新的外部效果；
- `non_idempotent_write` 可定义 `reconcile` 用于澄清事实（供升级决策），但永不解锁自动重试——重试策略表见下。

每个效果类对应的恢复/重试规则是一个全函数（core `retryPolicyForEffect`，ADR-0011）：

| effect | retry policy |
| --- | --- |
| `read_only` / `idempotent_write` | `safe_to_repeat` |
| `reconcilable_write` | `repeat_only_after_reconciled_absence` |
| `non_idempotent_write` | `never_repeat`（重复执行是人工升级决策） |

`requiredCapability?: CapabilityRequirement` 随 M3-T002（Capability 机制，section 9）加入。

## 8.2 Tool Execution State Machine

```text
PROPOSED
   │
   ├── denied ──> REJECTED
   │
   ▼
AUTHORIZED
   │
   ▼
EXECUTING
  / | \
 /  |  \
▼   ▼   ▼
SUCCEEDED FAILED INDETERMINATE
                  │
             reconcile
               /   \
              ▼     ▼
        SUCCEEDED  FAILED
              \
               -> INDETERMINATE (仍未知)
```

硬规则：

- timeout **不是自动 FAILED**；
- request 已可能到达外部系统时，若无法判断结果，应 `INDETERMINATE`；
- `INDETERMINATE` 不允许盲目 retry `non_idempotent_write`；
- replay 不执行 `execute()`（也不调用 `reconcile()`——其结论已是 `ToolReconciled` 事实）；
- Tool 结果先作为事实 Event，再由 ContextBuilder 决定如何告诉模型；
- reconcile 结论落盘为 `ToolReconciled` 事件（payload 按 `outcome` 判别：`succeeded`+`resultJson` / `failed`+`message` / `indeterminate`+`reason`），仅可从 `INDETERMINATE` 追加，未定论前可多次 reconcile；经 reconcile 达到的 `SUCCEEDED`/`FAILED` 与执行达到的终态同样不可复活（ADR-0011）。

## 8.3 Reconciliation

优先级：

1. provider idempotency key；
2. 查询外部对象是否存在/状态；
3. 比较预期状态与现实状态；
4. 无法确认则保持 `INDETERMINATE` 并升级给用户/上层。

---

# 9. Capability / Policy

## 9.1 Capability 是 Runtime 强约束

Capability 不依赖 Prompt。模型可知道当前 capability，但不能自己授予。

示例：

```ts
type CapabilityRequirement = {
  name: "fs.read" | "fs.write" | "shell.exec" | string;
  scope?: CapabilityScope;
};
```

Policy 决策（M3-T002 起按实现校准；判序与拒绝理由见 `docs/subsystems/core.md` capability 章节）：

```ts
type CapabilityDecision =
  | { type: "allow"; via: { kind: "grant" } | { kind: "lease"; leaseId: CapabilityLeaseId } }
  | { type: "deny"; reason: string }
  | { type: "requires_approval"; request: ApprovalRequest };
```

`allow` 以 `via` 指名满足来源（常设 grant 或某个具体 lease），按 leaseId 引用而非内嵌 lease 副本——决策里的证据不会与 host 侧配置漂移。`requires_approval` 在 v1 无审批 UX 时由运行时 fail-closed 拒绝（ADR-0007），不存在"先放行再补批"。

## 9.2 Lease

写权限/高风险权限优先使用 lease：

```ts
type CapabilityLease = {
  id: CapabilityLeaseId;
  capability: string;
  scope?: CapabilityScope;
  issuedAt: number;
  expiresAt: number;
  reason: string;
};
```

过期后 Runtime 无条件拒绝（`now === expiresAt` 即已过期，零宽限），不由 LLM 判断"应该还能用"。

## 9.3 Sandbox

v1 能力边界优先两层：

1. CapabilityPolicy：逻辑授权；
2. Tool implementation：路径/root/cwd 限制。

OS 级 sandbox 是 v1.1/平台增强方向；在真正高风险自动化之前必须补齐，不能声称 v1 已具备企业级隔离。

---

# 10. Model Provider

统一 Port 不追求“抽象所有模型特性”，只抽取 Agent Loop 真正需要的最小集合：

```ts
type ModelProvider = {
  complete(request: ModelRequest, signal: AbortSignal): AsyncIterable<ModelEvent>;
};
```

`ModelRequest`：

- normalized messages/context fragments；
- tool definitions；
- model id；
- max output / provider options（通过有限 escape hatch）；
- correlation metadata。

`ModelEvent`：

- text delta；
- tool call start/delta/end；
- usage；
- completion；
- provider error。

原则：

- Core 不解析 provider-specific raw response；
- adapter 负责 provider retry，Core 只处理规范化失败；
- Provider API error 不自动等于 Session failure；根据错误种类决定 retry/暂停。

---

# 11. Agent Loop

## 11.1 Turn / Step

- **Turn**：一次用户输入/恢复指令触发的工作周期；
- **Step**：一次 model request 及其产生的 tool calls/results。

## 11.2 核心伪代码

```ts
async function runTurn(runtime: SessionRuntime, input: UserInput) {
  await runtime.append(turnStarted(input));

  while (true) {
    runtime.throwIfCancelled();

    const state = runtime.state();
    const context = await runtime.contextBuilder.build(state);

    const modelResult = await runtime.runModel(context);

    if (modelResult.toolCalls.length > 0) {
      for (const call of modelResult.toolCalls) {
        await runtime.toolRuntime.handle(call);
      }
      continue;
    }

    if (!runtime.completionPolicy.canComplete(runtime.state())) {
      await runtime.append(completionBlocked(/* reason */));
      continue;
    }

    await runtime.append(turnCompleted(modelResult.finalText));
    return modelResult.finalText;
  }
}
```

实际实现需避免“completion blocked 后无变化无限循环”，必须有可执行下一动作或 pause/ask-user。

## 11.3 Loop Guard

v1 内建确定性 guards：

- max steps per turn；
- max repeated identical tool call；
- max consecutive model failures；
- context budget；
- wall clock cancellation；
- no-progress detector（简单规则版）。

达到 guard：`SessionPaused` / `TurnFailed`，不无限循环。

---

# 12. Context Builder

Context 是**有限工作集**，不是历史数据库。

## 12.1 组成顺序

建议：

1. system/runtime identity；
2. Goal + hard constraints；
3. current plan/focus/open challenge；
4. active policy/capability summary；
5. recent conversational turns；
6. relevant observations/hypotheses；
7. relevant recent tool results；
8. tool schemas。

## 12.2 不可依赖自由摘要保留的信息

以下使用结构化 fragment：

- hard constraints；
- pending `INDETERMINATE` tool execution；
- open challenge；
- active plan；
- current mode；
- required verification state。

## 12.3 Budget

必须有 hard caps：

```text
max fragment bytes
max single tool result bytes
max active observations
max active hypotheses
max recent messages
max total estimated tokens
```

超限策略：

- tool output truncation + artifact/reference；
- old conversation 确定性压缩（deterministic compaction，M5-T002）；
- inactive hypothesis 不进入 active context；
- Event history 保留，不因 compaction 删除。

v1 先实现简单 deterministic projection；自动 semantic retrieval 与模型生成的 summarization 后置。

**双层组装法则（M5-T001）**：brief 分两层——不可压缩层（12.2 全部条目）逐行渲染、永不因字节压力被逐出，仅单行仍受 `maxFragmentBytes` 硬界；可压缩层（active hypotheses、observations，各自计数封顶、最新优先）按**整节**让位，让位必附诚实的 `…[+K brief lines omitted]` 计数。brief 总字节恒不超过 `maxFragmentBytes`；不可压缩层自身放不下时直接 `ContextBudgetExceededError`（fail closed），绝不静默丢弃治理状态。带 brief 的 system 组合片段超限时同样 fail closed；无 brief 时超长 prompt 仍按 v0 头截断。

**确定性压缩（M5-T002）**：滑出 `maxRecentMessages` 窗口的消息不再无声消失——`buildContext` 在组合 system 片段末尾（brief 之后）追加单一 `## Compacted history` 分节，一行按角色计数的诚实摘要（`N earlier messages compacted: U user, A assistant, T tool results`）。计数只来自被丢弃的 fitted 消息，无时钟/随机/模型生成文本；同一输入与 budget 永远渲染同一 recap。零丢弃时输出与 M5-T001 投影逐字节一致。recap 属 system 片段而非合成 history 消息（保字长窗口后缀性质）；计入 M5-T001 的 fail-closed 界。Event store 永远全量保留——压缩只约束工作上下文。

## 12.4 v1 实现（M4-T002、M5-T001、M5-T002）

- `projectEpistemicBrief(state, budget)`：纯函数渲染器，从 `DerivedSessionState` 生成结构化 brief——同一状态与 budget 永远渲染同一字符串；不读时钟/随机/环境。
- 分节优先级即 12.2 法则的落地顺序：goal + hard constraints → active plan（含 falsifiedIf 与 hypothesis 引用）→ open challenges → pending `INDETERMINATE` executions → latest verification（`inconclusive` 一等公民，原样呈现）→ active hypotheses（仅 proposed/supported；falsified/superseded 永不进入）→ observations（按 `maxActiveObservations` 截取最新 N 条，最旧先丢）。
- 每行独立过 `maxFragmentBytes` 截断（带 `…[+N bytes truncated]` 标记），单条病态 claim 无法挤掉后面的分节；组合后的 system 片段仍受整体 fitText 与 token 上限约束，超限 fail closed（`ContextBudgetExceededError`）。
- M5-T001 起 brief 按 12.3 双层法则组装：active hypotheses 以 `maxActiveHypotheses`（默认 8）取最新 N 条并附 `…[+K older active hypotheses omitted]` 计数；可压缩分节整节让位并计数；不可压缩层或组合 system 片段超限即抛 `ContextBudgetExceededError`。推论：需要单行截断的病态行约占满整个 cap，必然导致其分节让位（可压缩）或 fail closed（不可压缩）——诚实让位置于截断示人。
- brief 组合进**单一** system 片段（systemPrompt + 空行 + brief），不新增第二条 system 消息；`buildContext` 的 no-system-in-history 法则不变。
- M5-T002 起窗口丢弃触发确定性压缩：`buildContext` 内部对窗口与 token 循环做收敛迭代——每轮按当前窗口计算 recap 并组合 system 片段，仍超 token 上限则再丢一条并重算计数；丢弃数 > 0 时追加 `## Compacted history` 行（按角色计数），丢弃数为 0 时输出与 M5-T001 逐字节一致。recap 计入 fail-closed 组合界与 `maxFragmentBytes` 单行界。
- 认识论切片为空且无 pending indeterminate 时返回 `undefined`，brief 整体省略——无认识论事实的会话构建出与 M4 之前逐字节相同的上下文。
- `runTurn` 每步重新折叠流并重建 brief，turn 中途落地的认识论事实下一步即到达模型。
- v1 无 mode 字段，故 12.2 中的 "current mode" 在 v1 无对应分节（有意省略，非遗漏）。

---

# 13. Completion / Verification

v1 不强制所有任务都启动独立 Verifier Agent。

`CompletionPolicy` 根据模式和工具 effect 决定最低条件：

### Direct / read-only

- 无 pending tools；
- 模型输出完成；
- 无 open hard conflict。

### 写操作

- 所有 tool execution 非 `EXECUTING/INDETERMINATE`；
- required postcondition check 完成（若 tool 定义要求）；
- hard constraints 未违反。

### 显式 `VerificationRecorded`

用于高风险/复杂任务，可由 extension/worker/确定 checker 产生。

原则：Verifier 不可用时，若 policy 要求 verification，则 fail closed。

---

# 14. Challenge 与 Replan

Challenge 不需要 Critic Agent。

流程：

```text
Observation
   ↓
ChallengeRaised(target, evidence)
   ↓
Core marks open challenge
   ↓
Context contains unresolved challenge
   ↓
Model/extension resolves:
   ├─ accept -> PlanInvalidated / HypothesisFalsified
   ├─ reject -> ChallengeResolved(reason)
   └─ pause -> human/independent review
```

若 Challenge 指向 completion 且 policy 要求解决，Session 不能完成。

v1 的 policy 即法则本身，不引入可配置 policy 对象（`CompletionPolicy` 见 §13 未来工作）：

- 所有 `targetType === "completion"` 的 open challenge 阻断 `SessionCompleted`，reducer 在 fold 时拒绝并逐出全部阻断者的 id；
- 指向 hypothesis / plan / policy 的 challenge 不阻断完成（v1 只按 target 判定）；
- 任何 `ChallengeResolved` outcome（`accepted` / `rejected` / `resolved`）都解除阻断——reducer 不评价理由，理由进 Event 流；
- epistemic brief 渲染 `## Completion blocked` 分节，使模型知道完成为何不可用、需要先解决什么。

v1 不自动做复杂 appeal hierarchy；保留 `Challenge` + `SessionPaused` 足够。

---

# 15. Session Lifecycle

```text
NEW
 │
 ▼
IDLE
 │ user input
 ▼
RUNNING
 ├── needs user/unknown ──> PAUSED
 │                         │ resume
 │                         └──────> RUNNING
 ├── unrecoverable ───────> FAILED
 └── goal reached ────────> COMPLETED
```

- `FAILED` 表示 Harness 无法继续，而非某次 Tool Failed；
- Tool failure 通常仍可回到 RUNNING；
- `PAUSED` 是正常状态，用于 `UNKNOWN`、approval、guard；
- Completed session 允许 fork/resume-as-new-session，v1 后半段实现。

---

# 16. 单写者与并发

v1 原则：**Single Writer per Session**。

- 一个 SessionRuntime 串行 append durable events；
- Model streaming 与 Tool execution 可异步，但最终 Event commit 顺序由 runtime 序列化；
- 多 Worker（未来 extension）只能提交 Observation/Proposal，不直接写全局 state object；
- SQLite 多 session 可并发；同一 session 保证 seq serialization；
- 避免第一版实现 distributed consensus。

---

# 17. Crash Recovery

恢复步骤：

1. 打开 EventStore；
2. 加载 Session events；
3. schema migrate / validate；
4. reducer replay；
5. 检查 tool executions：
   - `EXECUTING` 无 terminal event -> 视为潜在 `INDETERMINATE`；
6. 对可 reconcile 的工具运行 reconciliation：以注册工具的 inputSchema 解析 recorded input，调用其 verification-only `reconcile`，结论落为 durable `ToolReconciled` 事实；不可解析、尝试失败或无定论 → 诚实 indeterminate 事实，绝不猜测；
7. 仍有 unresolved indeterminate → 先 `TurnCompleted`（若有 open turn）再 `SessionPaused`：升级为 durable 暂停，不得带着未定论的外部效果继续 turn；
8. 重建 Context；
9. 用户 resume（`SessionResumed`，唯一解锁；PAUSED 会话拒绝运行）后 runtime 重新进入恢复流程并重试 reconciliation；`ToolReconciled` 是关于历史执行的事实，不要求 open turn——否则人工解锁环在结构上不可能。

### 崩溃矩阵（M5-T004）

上述步骤按崩溃发生的关键边界落为可检验的矩阵（`tests/fault/crash-matrix.fault.test.ts` 逐格注入并断言四法则：前缀合法折叠、恢复事实诚实、危险工具 execute 计数不越过崩溃前值、恢复幂等；`tests/store/crash-recovery.bun.test.ts` 在真实 SQLite 关闭/重开后走"before result append"皇冠格）：

| 崩溃边界 | 持久化前缀终止于 | 恢复事实 | execute 计数 |
| --- | --- | --- | --- |
| before append（ToolProposed 未落盘） | ModelResponseCompleted（tool-call 意图已持久，执行未成事实） | 无——无 dangling 执行，模型被重新询问 | 0 |
| before execute · 提案中 | ToolProposed（dangling PROPOSED） | `ToolRejected`（abandoned at proposal） | 0 |
| before execute · 授权后 | ToolAuthorized（dangling AUTHORIZED） | `ToolRejected`（abandoned at authorization） | 0 |
| after side effect（executor 崩溃，结果未知） | ToolStarted，运行时当回合落 `ToolIndeterminate` | 下一入口 reconciliation 落 `ToolReconciled` | 1（verify-only） |
| before result append（结果在手，落盘崩溃） | ToolStarted（dangling EXECUTING） | 恢复落 `ToolIndeterminate` → reconcile 落 `ToolReconciled`；绝不采信死进程的内存结果（未验证的 `ToolSucceeded` 不得出现） | 1（verify-only） |
| after result append（终态已落盘） | 终态事实 | 无——恢复零追加，事实已 durable | 1 |

矩阵同时钉死：混合 dangling（同一崩溃留下一个 PROPOSED + 一个 EXECUTING）按插入序先 reject、后 indeterminate、再 reconcile；第 9 步人工解锁环全流程（未定论 → `SessionPaused` → PAUSED 拒绝运行 → `SessionResumed` → 重试 reconciliation → 落定后继续 turn，计数全程不变）。

### 绝对禁止

- 因为没有 result event 就假设工具没执行；
- replay 时重执行历史 tool；
- crash 后直接清空 pending state；
- `INDETERMINATE` 默认 retry 非幂等操作。

---

# 18. Configuration 与 Secrets

v1：

```text
praxis.config.json
.env / process env (secrets only)
```

Config 使用 Zod 验证。

示例：

```json
{
  "model": {
    "provider": "openai",
    "model": "<model-id>"
  },
  "workspace": {
    "root": "."
  },
  "limits": {
    "maxStepsPerTurn": 32,
    "toolTimeoutMs": 120000
  }
}
```

API key 不写入 config/event/model context；telemetry 必须 redaction。

---

# 19. Extension API

v1 Extension 目标：让 Plan UI/Multi-Agent/Emergency/Audit 后续接入，但不把 Core 变成 Event Bus framework。

只提供少量 seam：

```ts
type PraxisExtension = {
  name: string;
  onTurnStart?(ctx: ExtensionContext): Promise<void>;
  contributeContext?(ctx: ContextContributionContext): Promise<ContextFragment[]>;
  beforeModel?(ctx: ModelHookContext): Promise<void>;
  afterModel?(ctx: ModelResultHookContext): Promise<void>;
  beforeTool?(ctx: ToolHookContext): Promise<ToolHookDecision | void>;
  afterTool?(ctx: ToolResultHookContext): Promise<void>;
  onEvent?(event: SessionEvent): Promise<void>;
  onTurnEnd?(ctx: ExtensionContext): Promise<void>;
};
```

约束：

- hook 数量不随每个新需求增长；
- extension 不能绕过 CapabilityPolicy；
- extension 自己的 durable state 必须以 Event 或独立显式 storage 管理；
- extension failure 是否阻断主循环由 hook contract 明确；默认 telemetry extension 不阻断，security/policy extension fail closed。

---

# 20. 生产模式

## 20.1 Direct Mode

简单、低风险、无需复杂 tool lifecycle 的任务。

```text
Request -> Model/Read-only Tool -> Response
```

可以共用 provider，但不需要完整 epistemic state。

## 20.2 Praxis Mode

复杂/需要工具/需要恢复的正常模式：

```text
Goal -> Context -> Model -> Tool -> Event -> Context -> ... -> Complete
```

Observation/Hypothesis/Plan/Challenge 可用。

## 20.3 Emergency Mode

**v1 只预留 mode/capability lease 机制，不实现完整 emergency extension。**

未来 extension 可以临时修改：

- capability lease；
- context instruction；
- approval latency；
- selected tool set；

但 hard constraints 和 Event recording 不可关闭。

---

# 21. Telemetry

Event Store 是业务/Agent 事实；Telemetry 是运维数据，二者分离。

Telemetry 至少：

- session/turn/step IDs；
- provider latency/usage；
- tool duration/result class；
- authorization outcome；
- event append latency；
- context size；
- retry/reconciliation count；
- loop guard hit；
- crash recovery outcome。

禁止把秘密、完整敏感 Tool output 无条件写 telemetry。

---

# 22. Error Taxonomy

错误必须分层，避免“一切 throw Error”：

```text
ConfigurationError
ContractValidationError
ModelProviderError
ToolExecutionError
ToolIndeterminateError
AuthorizationError
PersistenceError
ReplayError
InvariantViolation
CancellationError
```

每类定义：

- 是否 retryable；
- 是否 session-fatal；
- 是否产生 durable event；
- 是否需要 human escalation；
- 是否可以安全显示给模型。

---

# 23. 安全边界

v1 的安全声明必须克制：

- Capability + workspace path policy 是逻辑边界；
- 不宣称已经完全 sandbox；
- shell 默认最小权限；
- workspace root 外 write 默认拒绝；
- secrets 不进 model context；
- external network 默认由 Provider/Tool 显式拥有，而非所有 shell 随意联网；
- 后续 OS sandbox 作为高风险自动化前置里程碑。

---

# 24. 关键不变量

以下进入 Core 测试：

1. `seq` 单调、唯一；
2. replay 无外部副作用；
3. reducer 确定；
4. `UNKNOWN != FAILED`；
5. pending `INDETERMINATE` 在要求 resolve 的策略下阻止完成；
6. expired capability 不授权；
7. Tool 未 `AUTHORIZED` 不得进入 `STARTED`；
8. Tool terminal state 不可被同 execution 再次覆盖；
9. hard constraint 不可由 Plan/Event 非授权路径修改；
10. required verification 不满足时不得 `SessionCompleted`；
11. Context 有硬上限；
12. extension 不得绕过 capability；
13. Session load 对未知 schema version fail explicit；
14. Event append 与 head seq 更新事务一致；
15. crash/recover 不自动重执行 non-idempotent Tool。

---

# 25. 首批架构决策（需要建 ADR）

建议初始化时建立：

- ADR-0001：Bun + TypeScript v1 runtime；
- ADR-0002：Event Sourcing + SQLite；
- ADR-0003：Single Writer per Session；
- ADR-0004：Deterministic Core / Adapter Ports；
- ADR-0005：Tool `INDETERMINATE` 状态；
- ADR-0006：Capability Core, UI approval outside core；
- ADR-0007：Multi-Agent 不进入 v1 Core；
- ADR-0008：Exact dependency pinning。

---

# 26. 可演进边界

只有真实实践出现以下信号才升级设计：

| 信号 | 才考虑的设计 |
|---|---|
| replay 明显变慢 | snapshot/compaction |
| SQLite 成为实际瓶颈 | 新 Store adapter |
| 单写者成为主要瓶颈 | session actor/并发模型 |
| provider 差异难以隔离 | 扩展 ModelProvider contract |
| 多任务真实需要并行实践 | Worker/Multi-Agent extension |
| capability policy 难表达 | scoped policy language |
| 高风险自动化要上线 | OS sandbox/isolated executor |
| Direct/Praxis 路由频繁误判 | 智能 Task Router |

没有 evidence 不提前实现。
