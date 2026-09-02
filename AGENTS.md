# Codex 项目规则

<!-- praxis:managed:start -->
## Praxis 工作流（自动管理）

- 工作空间：`praxis-next`（Praxis V3插件开发工作空间）
- 权威知识库：`知识库`；聊天记录不能替代需求文档。
- 最高优先级的显式绕过 Praxis：用户明确说‘绕过 Praxis’、
  ‘不使用 Praxis’或‘禁用 Praxis’时，本任务不适用下述 Praxis 规则；
  不调用 Praxis MCP/CLI，不登记需求、不创建 Praxis 工作树、
  不路由 Skill、不执行 Praxis 门禁或审计，直接回到宿主 Agent 的普通工作方式。
  每轮先判定是否命中本条；一旦命中，立即终止解析和执行下文的
  Praxis 规则。下文的 binding、worktree、retry budget、fail-closed、审计和
  状态流转限制全部不适用，不得再以它们为由停止任务。用户的明确表达
  本身就是足够且立即生效的授权；不得要求用户先修改 `AGENTS.md`、提供
  retry-reset/repair 命令或修复 Praxis 状态。若 Praxis 流程已开始，立即停止后续
  Praxis 调用，并从当前任务进度按普通工作方式继续。
  只有同时明确指向 Praxis 的绕过表达才能触发；例如‘给你绕过
  Praxis 的权限’、‘这次绕过 Praxis 继续’均应视为命中。
  “快速修复”“只改这里”“不要跑测试”不等于绕过，仍使用 Praxis 快速路径。
- 操作细则（fast_fix、RTK、TDD、命令预算、证据指纹缓存、subagent、investigate）
  以内置 `praxis-requirement-workflow` Skill 为唯一权威源，进入节点时按需加载；
  本文件只保留不随任务变化的指针与不变式。
- 不确定下一步时运行 `praxis guide` 获取当前状态对应的命令序列，
  错误码含义与恢复动作用 `praxis errors <CODE>` 查询。
- 入口：Praxis 操作优先使用已提供的 Praxis MCP；MCP 不可用时先执行
  `praxis doctor --json` 查看 CLI fallback.path 再使用可解析的 `praxis` CLI。
  DBX 调查只使用已提供的 DBX MCP 工具，不调用或回退到 DBX CLI。
- 新需求先登记并生成知识文档；需求知识目录使用 `<需求ID>__<简称>`，
  文档使用固定数字前缀；调查和计划阶段不要创建工作树。
- 只有确认需要改代码时，才在第一次代码编辑前创建绑定需求的 Worktrunk 工作树；
  先 `worktree preview` 固定工作空间、末级目录与分支，
  再 `worktree ensure --confirm <preview_id>`。工作树以仓库 `default_branch`
  为本地运行模板，先合并唯一 `origin/<template_branch>` 再从模板创建需求分支。
- 需求工作空间 `.worktrees/<需求ID>__<简称>`，仓库末级目录 `<需求ID>__<简称>__<仓库ID>`、
  分支 `praxis/<需求ID>__<简称>`；简称快照保持稳定，阶段名称不得进入目录或分支。
- 禁止在工作空间根目录或未绑定目录修改业务代码；
  pre-commit 在主仓库无 binding 且检测到业务代码改动时阻断，
  提示‘请走 praxis 工作树’。
- 功能、缺陷修复、重构和行为变更默认执行 TDD（RED→GREEN→重构），聚焦 TDD 授权
  不包含完整回归、lint、format、typecheck、覆盖率、构建或代码复核；
  TDD GREEN 后调用 `minimum-module-compile` 编译最小受影响模块。
- 完整回归、lint、typecheck、覆盖率、质量复核、reviewer/tester Agent 与收尾 Skill
  始终需要独立验证授权；“提交”“推送”“完成”“继续”不等于批准。
- 用户明确说“快速修复”“只改这里”“不要跑测试”等时，按 `praxis-requirement-workflow`
  Skill 的 fast_fix 例外处理并记录 `mode=fast_fix`；否则回到标准流程。
- 高风险改动（事务、锁、原生 SQL、并发、公共接口、共享服务、
  跨模块、结构迁移、高扇出）
  必须在编辑前调用 `codegraph-impact-analysis`；Plan Mode 无 binding 时用
  `praxis codegraph investigate <target> --project <项目>
  --purpose <目的>` 只读查询。
- 数据库调查必须从 context 已登记的 DBX 引用中显式选择连接，禁止默认库猜测；
  对结构或数据作出判断前先执行 `select current_database()` 核对目标库。
- 需求按 `in_progress → implemented → verifying → completed` 推进，
  `requirement advance` 一次只前进一个状态；
  状态流转与 `worktree create` 均 fail-closed，
  当前节点缺少 route、完成凭证或 gate 时必须停止，不得自动补路由或绕过。
- 产出物在代码稳定后登记，相同需求+路径 upsert；实施完成不等于验证通过，
  用户明确不执行某项验证时登记 decline receipt，不把 declined 或未执行投影为 passed。
- 需求从 verifying 回开发使用带原因的 `requirement reopen`。
- 所有外部命令先由 RTK 代理；普通文本搜索使用 `rg`，机器 JSON 用 `rtk proxy`。

### Skill 调用协议

1. 进入节点先运行 `praxis skill route-node --node <节点> --requirement <需求ID>`。
2. 对决定使用的 Skill 运行 `praxis skill invoke <Skill ID> --requirement <需求ID> --node <节点>`。
3. Skill 工作完成后，用返回的 invocation ID 运行 `praxis skill complete <调用ID>`。
4. 多 Skill 节点优先运行 `praxis lifecycle complete-node --requirement <需求ID>`
  并逐项传入 `--used-skill <id>=<result>:<outcome>`，例如
  `--used-skill 'skill-id=passed:结果说明'`（外层单引号，值内冒号用半角 `:`）。
5. `approval_missing` 只表示验证待批准，不能记录为 completed 或 passed。
6. `approval_required` Skill 只有获得本次用户明确批准后才能加 `--approved` 调用。

## 仓库模板分支

| 仓库 | 类型 | 路径 | 本地模板 | 上游模板 |
|---|---|---|---|---|
| `praxis-next` | `python-plugin` | `.` | `codex/praxis-v3-development` | `codex/praxis-v3-development` |

## 节点 Skill 策略

- `captured`：`praxis-requirement-workflow`（必需）
- `investigating`：`praxis-requirement-workflow`（必需）, `brainstorming`（必需）, `grilling`（必需）, `ponytail`（必需）, `codegraph-impact-analysis`（命中后必需）, `file-search`（条件）, `systematic-debugging`（条件）, `dbx-database-investigation`（条件）, `context-degradation`（条件）, `context-optimization`（条件）, `prompt-engineering`（条件）, `find-skills`（条件）
- `analyzed`：`praxis-requirement-workflow`（必需）, `ponytail`（必需）, `wayfinder`（必需）, `dbx-database-investigation`（条件）, `context-degradation`（条件）, `context-optimization`（条件）, `find-skills`（条件）
- `planned`：`praxis-requirement-workflow`（必需）, `ponytail`（必需）, `codegraph-impact-analysis`（命中后必需）, `wayfinder`（必需）, `java-coding-standards`（条件）, `karpathy-guidelines`（条件）, `context-degradation`（条件）, `context-optimization`（条件）, `prompt-engineering`（条件）, `find-skills`（条件）, `api-permission-migration`（条件）, `uniapp-api-generation`（条件）, `add-mom-magic-api`（条件）, `build-mes-pda-readonly-overview`（条件）
- `ready`：`praxis-requirement-workflow`（必需）
- `in_progress`：`praxis-requirement-workflow`（必需）, `ponytail`（必需）, `tdd`（必需）, `minimum-module-compile`（必需）, `codegraph-impact-analysis`（命中后必需）, `file-search`（条件）, `systematic-debugging`（条件）, `dbx-database-investigation`（条件）, `java-coding-standards`（条件）, `karpathy-guidelines`（条件）, `context-degradation`（条件）, `context-optimization`（条件）, `prompt-engineering`（条件）, `subagent-driven-development`（需批准）, `Testing Writing Guidelines`（需批准）, `api-permission-migration`（条件）, `uniapp-api-generation`（条件）, `add-mom-magic-api`（条件）, `build-mes-pda-readonly-overview`（条件）, `receiving-code-review`（条件）
- `implemented`：`praxis-requirement-workflow`（必需）, `Testing Writing Guidelines`（需批准）, `verification-before-completion`（需批准）, `code-quality-review`（需批准）
- `verifying`：`praxis-requirement-workflow`（必需）, `codegraph-impact-analysis`（命中后必需）, `systematic-debugging`（条件）, `Testing Writing Guidelines`（需批准）, `verification-before-completion`（需批准）, `code-quality-review`（需批准）, `api-permission-migration`（条件）, `uniapp-api-generation`（条件）, `add-mom-magic-api`（条件）, `build-mes-pda-readonly-overview`（条件）, `requesting-code-review`（需批准）, `receiving-code-review`（条件）
- `completed`：`praxis-requirement-workflow`（必需）, `verification-before-completion`（需批准）, `finishing-a-development-branch`（需批准）

## 项目规则与业务 Skill 来源

- `skills`

<!-- praxis:managed:end -->
