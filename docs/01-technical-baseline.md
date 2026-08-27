# Praxis Harness 技术选型与工程基线

**状态：Baseline / v1**  
**目标：**冻结进入开发前的技术栈、版本、依赖政策、编码规范、Git/提交规范和 CI 基线。

---

## 1. 选型原则

Praxis Harness 是一个长期运行、会产生真实副作用的 Agent Runtime。技术选型按以下顺序优化：

1. **状态正确性与可恢复性**高于短期性能；
2. **核心依赖少、边界清楚**高于功能堆叠；
3. **确定性核心**高于动态魔法；
4. **可测试和可回放**高于“框架体验”；
5. **精确锁定版本**，升级必须是显式工程任务；
6. 优先使用运行时/标准库能力，只有成熟组件明显降低风险时才引入依赖；
7. v1 不追求多运行时兼容，先把 Bun 路线做深；
8. 任何新依赖都必须说明：解决什么问题、为何标准库不够、许可证、维护状态、失败语义和移除成本。

参考成熟项目的经验：Pi 在仓库中检查依赖必须被固定并保持极简 Core；Codex 对 Agent 逻辑变更要求集成测试并限制大规模一次性改动；DeepSeek Harness 将架构规则、Agent Notes、测试层级和文档归属做成可检查约束。

---

## 2. v1 技术栈总览

| 类别 | 选择 | v1 锁定 | 说明 |
|---|---|---:|---|
| 开发工具管理 | mise | **2026.7.13**（CI/文档基线） | 统一工具安装与任务入口，提交 `mise.lock` |
| JS/TS Runtime + PM | Bun | **1.3.14** | 不直接采用刚发布且底层大改的 1.4.0；升级作为单独 ADR/兼容任务 |
| 语言 | TypeScript | **7.0.2** | ESM、strict、判别联合、无 `any` |
| Bun 类型 | `@types/bun` | **1.3.14** | 与 Bun 1.3.14 运行基线匹配 |
| Schema/运行时校验 | Zod | **4.4.3** | Event、配置、Provider/Tool 边界输入校验 |
| 测试 | Vitest | **4.1.11** | Pi/DeepSeek 均采用 Vitest；负责 unit/integration/replay |
| 覆盖率 | `@vitest/coverage-v8` | **4.1.11** | 与 Vitest 同版本 |
| 属性测试 | fast-check | **4.9.0** | reducer/state machine/invariant 属性测试 |
| 格式化+Lint | Biome | **2.5.10** | 单工具覆盖格式与主要 lint，避免 ESLint/Prettier 双栈 |
| 无用代码/依赖检查 | Knip | **6.32.2** | 防止 AI 开发长期积累死代码、无用 export/依赖 |
| Git hooks | Lefthook | **2.1.10** | 快、语言无关，pre-commit/commit-msg/pre-push |
| Commit 校验 | commitlint | **21.2.2** | Conventional Commits |
| Commit 配置 | `@commitlint/config-conventional` | **21.2.2** | 与 CLI 同版本 |
| 首个模型 Provider | `openai` | **7.5.0** | 仅在 Adapter package 中依赖；Core 不依赖 SDK |
| SQLite | Bun `bun:sqlite` | **随 Bun 1.3.14** | v1 不引入 ORM/`better-sqlite3`/Drizzle |
| ID | `crypto.randomUUID()` | Runtime 内建 | 不增加 nanoid 依赖 |
| CLI 参数 | `node:util.parseArgs` | Runtime 内建 | v1 不引入 Commander |
| Build | Bun/TypeScript 原生 | Runtime/TS 内建 | v1 不引入 tsdown/esbuild；发布需求出现后再评估 |

### 为什么不直接锁 Bun 1.4.0

Bun 1.4.0 是 2026 年 8 月最新版本，并包含底层从 Zig 到 Rust 的大规模重写。对于一个把“状态恢复、文件/进程、副作用语义”放在 P0 的新 Runtime，首批实现优先选经过数月使用的 1.3.14。待 M7 建立完整 crash/replay/soak 测试后，再开独立任务验证 1.4.x，并只有在全部兼容门通过后升级。

### 为什么不使用 ORM

Event Store 的数据模型非常小且有特殊约束：append-only、`(session_id, seq)` 唯一、事务内追加、严格 migration/replay。ORM 会增加抽象面并降低 SQL 可见性。v1 直接使用 `bun:sqlite` 和显式 SQL migration；只有查询模型显著复杂化后才重新评估。

---

## 3. 工具链锁定策略

### 3.1 `mise`

仓库提交：

- `mise.toml`
- `mise.lock`

建议：

```toml
[settings]
lockfile = true

[tool_config]
locked = true

[tools]
bun = "1.3.14"
```

CI 安装工具时使用锁定模式。`mise.lock` 负责解析版本、下载 URL 和支持时的校验信息。禁止运行 `bun upgrade` 改变 mise 管理的 Bun。

### 3.2 JavaScript 依赖

所有 `dependencies` / `devDependencies` **必须精确版本**：

```json
"zod": "4.4.3"
```

禁止：

```json
"zod": "^4.4.3"
"zod": "~4.4.3"
"zod": "latest"
```

提交 `bun.lock`；CI 仅允许冻结锁文件安装。

### 3.3 升级政策

依赖升级不是“顺手升级”，必须单独提交或至少单独 commit：

1. 写明升级原因；
2. 阅读 changelog / breaking changes；
3. 更新精确版本与 lockfile；
4. 跑 `mise run check:all`；
5. Core/Tool/Store 依赖升级额外跑 replay + fault tests；
6. Runtime（Bun）升级额外跑 soak + crash matrix；
7. 若升级引入额外 API 绕过，不得通过修改业务逻辑“迁就”错误类型。

---

## 4. 仓库形态

使用 **Bun Workspaces 单仓库**，但保持包数量有限：

```text
apps/
  cli/                    # composition root + CLI
packages/
  contracts/              # 协议、schema、IDs、ports；无 I/O
  core/                   # reducer、session runtime、agent loop、context builder
  store-sqlite/           # EventStore SQLite adapter + migrations
  provider-openai/        # ModelProvider adapter
  tools-local/            # read/write/bash 等本地 Tool adapters
  testkit/                # ScriptedModel/FakeTool/fixtures/helpers
docs/
.agents/
```

### 依赖方向

```text
                 contracts
               /    |     \
              /     |      \
          core   adapters   testkit
                   |          |
          store/provider/tools|
               \    |        /
                \   |       /
                  apps/cli
```

硬规则：

- `contracts` 不依赖任何其他 workspace package；
- `core` 只依赖 `contracts`，不得 import SQLite/OpenAI/本地工具实现；
- Adapter 可以依赖 `contracts`，不得互相依赖；
- `apps/cli` 是 composition root，可以依赖所有实现；
- `testkit` 不得成为生产代码依赖；
- 任何反向依赖必须先写 ADR。

---

## 5. TypeScript 基线

### 5.1 Compiler

启用至少：

```jsonc
{
  "compilerOptions": {
    "target": "ES2024",
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true,
    "useUnknownInCatchVariables": true,
    "noImplicitOverride": true,
    "verbatimModuleSyntax": true,
    "isolatedModules": true,
    "noEmit": true
  }
}
```

### 5.2 语言规则

- 禁止 `any`，除非对第三方边界做极小隔离且有注释；
- 边界输入必须是 `unknown` 后显式 parse；
- 禁止 TypeScript `enum`，使用字符串 literal union / `as const`；
- 禁止 namespace；
- 状态使用 discriminated union（判别联合）；
- 尽量让非法状态无法表示；
- `null` 与 `undefined` 不混用：API 缺省使用 `undefined`，持久化 schema 明确 `nullable` 时才用 `null`；
- Core 中不允许可变模块级全局状态；
- 时间统一保存 Unix 毫秒整数，展示层再转时区；
- 外部 ID 使用 `crypto.randomUUID()`；Event 顺序以每 Session 单调递增 `seq` 为准，而不是时间戳；
- public API 必须有稳定类型，内部实现不为“看起来漂亮”提前泛型化。

### 5.3 命名

- Command：祈使/动作语义，如 `ExecuteTool`；
- Event：过去式事实，如 `ToolStarted`、`ToolSucceeded`；
- Interface/Port：能力名，如 `EventStore`、`ModelProvider`；
- Adapter：实现名，如 `SqliteEventStore`、`OpenAIModelProvider`；
- `Error` 类型必须表明失败层级和是否可重试；
- 布尔字段必须可读：`isReplay`, `requiresVerification`，不用 `flag`, `ok2`。

---

## 6. 代码规模与可读性规则

参考 Codex 的“小而可审查变更”原则：

- 非机械变更：**建议 < 500 changed LOC，硬上限 800 changed LOC**；
- 超过上限必须拆成可独立验证的阶段；
- 单文件软上限 400 LOC，超过 600 LOC 必须说明原因或拆分；
- 单函数软上限约 50 LOC，核心状态转移函数可例外但必须保持分支可测试；
- helper 只有一个调用点且不提升语义时，优先内联；
- 注释解释“为什么/约束”，不翻译代码；
- 不允许“为了复用”提前造抽象层；有两个真实重复点后再判断是否抽象。

---

## 7. 格式化、Lint 与静态质量

### Biome

- `biome check --write`：本地格式化/自动安全修复；
- `biome ci .`：CI；
- warnings 在 CI 视为失败；
- 不使用 Prettier/ESLint，避免两套规则冲突。

### Knip

每个 PR/CI 检查：

- unused files；
- unused exports；
- unused dependencies；
- unlisted dependencies。

AI 很容易通过“加 helper/加包不删除”积累垃圾，Knip 是长期维护的硬约束。

---

## 8. 测试基线

使用 Vitest + fast-check。

### 测试分层

1. `unit`：纯函数、schema、reducer；
2. `property`：状态机、不变量、event replay；
3. `integration`：完整 agent loop + scripted model + fake tools；
4. `replay`：历史 session fixture；
5. `fault`：崩溃/timeout/UNKNOWN/reconcile；
6. `security`：capability bypass、路径逃逸、代理权限；
7. `soak`：长 Session、队列、lease 回收、内存增长；
8. `eval`：真实模型能力，**不作为 Core correctness CI 的替代**。

Agent Loop 行为变化必须有 integration test。Event schema 变化必须有 migration + replay test。Tool 生命周期变化必须有 UNKNOWN/幂等/故障测试。

### 覆盖率

- v1 初期不盲目追逐全仓 100%；
- `contracts`、`core/reducer`、`capability`、`store migration/replay` 目标 100% statement/branch 可达代码；
- Adapter 以关键失败路径覆盖为主；
- 任何为了覆盖率保留的无意义代码应删除而非编造测试。

---

## 9. Git 与分支策略

采用 **Trunk-Based Development**：

- `main` 始终可构建/可测试；
- feature branch 短生命周期；
- 不建立长期 `develop` 分支；
- 每个 PR 只解决一个清晰问题；
- AI 会话只操作本次任务涉及文件。

### 禁止命令（AI 默认）

除非用户明确要求，不得使用：

```text
git reset --hard
git checkout .
git clean -fd
git stash
git add .
git add -A
git commit --no-verify
```

提交前必须：

```text
git status
```

只 `git add <明确路径...>`。

---

## 10. Commit 规范

使用 Conventional Commits：

```text
<type>(<scope>): <subject>
```

允许类型：

- `feat`
- `fix`
- `refactor`
- `perf`
- `test`
- `docs`
- `build`
- `ci`
- `chore`
- `revert`

推荐 scope：

```text
contracts core store provider tools cli testkit docs build
```

示例：

```text
feat(core): add indeterminate tool execution state
fix(store): preserve session sequence on replay
refactor(contracts): separate command and event schemas
test(core): cover crash after external side effect
```

规则：

- subject 使用英文、祈使语气、小写开头、无句号；
- 建议 <= 72 chars；
- breaking change 使用 `!` 和 footer；
- 一个 commit 应可单独解释和尽量可测试；
- 机械 rename 与行为修改尽量分 commit。

Commitlint 在 `commit-msg` hook 和 CI 中执行。

---

## 11. PR / Review 规范

每个 PR 必须包含：

1. **Problem**：真实问题；
2. **Evidence**：为什么当前实现不足；
3. **Change**：最小解决方案；
4. **Non-goals**：本 PR 不做什么；
5. **Tests**：新增/修改哪些测试；
6. **Failure semantics**：涉及 Tool/Store/Provider 时如何失败；
7. **Docs/ADR**：是否更新当前事实和设计决策。

Core 变更 Review 必问：

- 是否新增不必要状态？
- 状态能否 replay？
- crash 窗口在哪里？
- 是否把 `UNKNOWN` 错当 `FAILED`？
- 是否让 LLM 决定本应由 Runtime 强制的规则？
- Context 是否无界增长？
- 是否增加隐式跨包依赖？

---

## 12. 文档治理

参考 DeepSeek Harness 的“一条事实一个家”：

- `docs/02-system-design.md`：当前架构地图，不写历史故事；
- `docs/subsystems/*`（进入开发后建立）：各子系统类型、语义、不变量；
- `docs/decisions/ADR-*`：为什么选择/放弃某设计；
- `AGENTS.md`：高频短规则，不塞教程；
- `.agents/skills/*`：情境化操作流程；
- Postmortem：故障证据和改进，不污染架构文档；
- 白皮书：理论来源，不作为当前 API 权威。

---

## 13. 第三方组件准入

新增依赖前必须回答：

```text
1. 具体解决哪个当前问题？
2. Bun/TS 标准能力为什么不足？
3. 是否有更小依赖？
4. 许可证是否兼容？
5. 最近是否维护？
6. 是否会进入 Core 热路径？
7. 失败时会不会破坏状态？
8. 如何替换/移除？
9. 是否需要 ADR？
```

Core runtime dependency 默认阈值：**越少越好，不设置为了凑数的数量目标**。

### v1 明确不引入

- ORM；
- DI container；
- Event Bus/Kafka；
- Workflow DSL；
- RxJS；
- 大型 Web framework；
- GraphQL；
- Vector DB；
- 通用 Agent framework；
- 多模型统一 SDK（先用自己的极小 Provider port）。

---

## 14. 建议的根命令

通过 `mise run` 统一入口：

```text
mise run format
mise run lint
mise run typecheck
mise run test
mise run test:coverage
mise run knip
mise run check:all

# 进入 M2/M3 后再增加：
mise run test:integration
mise run test:replay
mise run test:fault
```

CI 不调用“开发者电脑上碰巧有”的全局命令。

---

## 15. 版本来源快照（2026-08-27）

- Bun 最新为 1.4.0；项目选择 1.3.14 作为保守基线：https://bun.sh/ / https://github.com/oven-sh/bun/releases
- mise 近期稳定发布线：v2026.7.13：https://github.com/jdx/mise/releases
- TypeScript 7.0.2：https://www.npmjs.com/package/typescript
- Biome 2.5.10：https://www.npmjs.com/package/@biomejs/biome
- Vitest 4.1.11：https://www.npmjs.com/package/vitest
- Zod 4.4.3：https://www.npmjs.com/package/zod
- fast-check 4.9.0：https://www.npmjs.com/package/fast-check
- Knip 6.32.2：https://www.npmjs.com/package/knip
- Lefthook 2.1.10：https://www.npmjs.com/package/lefthook
- OpenAI SDK 7.5.0：https://www.npmjs.com/package/openai

版本是本项目的**基线快照**，不是“永远最新”。以后更新必须走依赖升级流程。
