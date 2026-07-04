# Praxis 重型化路线

## 定位

本文件是重型工作流 worktree 的方法与执行基线，目标是把任务执行从“口号”提升为可执行命令、可验证门禁、可追溯交付的生产实践中枢。

Praxis 的定位是：统一项目事实、方法论、需求契约、结构化索引、角色协作、门禁验证和知识沉淀；不替代 `Codex`、Claude Code、Cursor Agent 或 Copilot Agent。

## 方法论转译

| 层次 | 工程名 | 机制 |
| --- | --- | --- |
| 认识论 | evidence-first-practice-loop | inspect/index/query/evidence/context/verify/reflect |
| 辩证法 | contradiction-and-risk-routing | task classify、主要矛盾、风险分层、阈值升级 |
| 历史唯物论 | base-superstructure-consistency | 代码/数据库/测试事实与规则/Skill/脚本一致性检查 |
| 组织论 | role-division-and-controlled-evolution | 执行、质量、交付、知识、演化角色分离 |
| 工程控制层 | target-observation-feedback-control | 目标-观测-反馈：需求边界、上下文/索引观测、测试/门禁误差校正、交付复验 |

日常入口不使用口号化表达；所有方法论必须落为命令、结构化文件、状态机、门禁和复盘产物。

工程控制层承接马列毛方法论向工程动作的转译：以钱学森工程控制论和系统工程约束目标、边界、反馈、稳定性和扰动处理；以软件工程约束需求工程、配置管理、验证与确认、架构决策和交付复验。凡新增规则或流程，必须回答三问：目标清楚吗、系统看见了吗、反馈闭合了吗。

## P0（必须）

- `task` 是本 worktree 主入口；旧顶层命令仅保留兼容，不作为新文档和 AI 上下文首选。
- 所有入口动作均写明为 `task ...`，包括 req/project/context/etl/gate/delivery/system。
- 任务不可默认从业务外溢入口启动。

### 已落地任务命令

```bash
task req -- init <需求名> <用户原始需求原文>
task req -- iter <需求名> analysis|plan|progress <主题>
task req -- check <需求名>
task req -- index <需求名>
task req -- db-plan <需求名>
task project -- status|verify|run|shell|worktree|start <project> <args...>
task context -- --brief <project> <需求名>
task context -- <project> <需求名>
task etl -- init|subject|tree <args...>
task gate -- ready <project> <需求名>
task gate -- guard <project> <需求名>
task gate -- change-check <project> <需求名>
task gate -- migration-check <project> <需求名>
task gate -- validate-verdict quality|delivery <project> <需求名> <json-file>
task delivery -- status <project> <需求名>
task delivery -- finish <project> <需求名>
task delivery -- commit-split <project> <需求名> <结构化提交信息>
task delivery -- deliver <project> <需求名>
task delivery -- cleanup <project> <需求名>
task system -- check
task system -- index
task system -- praxis-profile
task system -- template-check
task system -- template-render rule <slug> <标题> <描述> <输出路径>
task system -- template-render skill <slug> <标题> <描述> <输出路径>
task system -- formalism-check
task system -- evolve propose
task system -- runtime-eval
task system -- command-audit
```

- `task system -- check`：校验 `.praxis/profile.toml`、本路线文件、方法论四层、M1-M4、命令契约和 Praxis profile。
- `task system -- index`：产出 `$PRAXIS_DIR/project-index.json`；Taskfile 默认 `$PRAXIS_DIR=.praxis/out/runtime`，仓库内 `.praxis/out/` 仅作为显式生成的参考快照。
- `task system -- praxis-profile`：校验 `.praxis/core.toml` 与 `.praxis/project-adapter.toml` 的通用平台/项目适配边界，并写出 `.praxis/out/profile.json`。
- `task system -- template-check`：校验 `.praxis/templates/`、`.rule/` 和 `.skill/` 的模板/规范契约，并写出 `.praxis/out/template-report.json`。
- `task system -- template-render`：从 `.praxis/templates/` 生成 rule 或 skill 骨架。
- `task system -- command-audit`：扫描规则/AGENTS/README，保证入口统一 `task`。
- `task context -- --brief`：产出 `$PRAXIS_DIR/context/<project>-<需求名>.json` 和低噪声恢复摘要；完整 `task context` 只在复杂/恢复/交接场景展开。
- `task gate -- validate-verdict`：校验结构化 PASS 结论。
- `task delivery -- commit-split` 与 `task delivery -- deliver/cleanup` 执行前，需满足相应 verdict 门禁。

## P1（重要）

### 分阶段执行

#### M1：覆盖现有 Praxis 工作流

- 已完成：读取 `.praxis/profile.toml`。
- 已完成：`Praxis` 主控入口重写为 `req/project/context/etl/gate/delivery/system` 七组。
- 已完成：旧命令保留兼容但非首选。

#### M2：本地事实与知识索引

- 已完成：`task index` 输出项目事实索引。
- 已完成：索引覆盖项目映射、规则、Skill、命令、角色、方法论层。

#### M3：角色调度与职责分离

- 已完成：Execution、Quality、Delivery、Knowledge、Evolution 角色落盘。
- 已完成：Quality 与 Delivery verdict 写入 `$PRAXIS_DIR/verdicts/`。
- 已完成：交付动作消费 PASS verdict，禁止单点越权提交/交付。

#### M4：受控自演化

- 已完成：`task system -- formalism-check`。
- 已完成：`task system -- evolve propose`，`canApplyAutomatically=false`。
- 已完成：`task system -- template-check` 校验 rule/skill 模板与现有文件规范。
- 已完成：`.praxis/templates/` 支持 rule/skill 代码生成骨架。
- 已完成：`.praxis/platforms/` 拆分 Codex 与 Claude 平台配置，`.codex/` 和 `.claude/` 只保留平台独有内容。

### 运行时评估（P1）

当前结论：控制面继续使用 `uv+Python`，前后端/uni-app 分析以 `Bun+TypeScript adapter` 为补充边界。

- 控制面主要处理 Git/worktree、TOML/JSON、需求文档、门禁与交付编排，当前稳定度足够。
- Web/PDA 生态适合 `TypeScript` 语法和路由/配置分析。
- 未见充分收益时不推进控制面整体重构。

## P2（持续优化）

- 形成统一的命令文案模板，减少每次写法偏差。
- 逐步细化 `runtime-eval` 触发条件，避免重复执行。
- 继续补齐未覆盖的可观察性指标（例如失败率、重跑率、上下文回填率）。

## 当前 worktree 边界

- 本 worktree 位于 `.worktrees/praxis/2026-06-18-Praxis架构提效-dev`，分支为 `codex/20260618-Praxis架构提效`。
- 本 worktree 已实现 Praxis 流程入口与命令收口；本需求允许本地自动阶段提交，但不执行远端推送、交付或 cleanup。
- 主工作区保留轻量结构化层改动；后续合并时应先决定主工作区轻量层与重型层的接入顺序。
