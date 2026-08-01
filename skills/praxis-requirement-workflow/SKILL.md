---
name: praxis-requirement-workflow
description: 管理 Praxis 需求从登记、知识文档、调查计划到隔离开发和交付的完整边界。用于任何新增功能、缺陷修复、重构或其他可能修改代码的工程需求，也用于检查需求文档、工作树和人工批准是否齐备。
---

# Praxis 需求工作流

## 核心顺序

严格按“先登记和调查，确认改代码后再建工作树，开发默认执行 TDD，完整验证另行获批”的
顺序执行。任何一步失败都停止，不在根工作区补做后续步骤。

## Praxis 入口解析

- 优先使用当前会话已提供的 Praxis MCP。
- MCP 不可用时才检查可解析的 `praxis` CLI。
- 会话启动或 coder context 必须注入当前入口诊断；MCP 缺失时先运行
  `praxis doctor --json`，从 `entrypoints.fallback.path` 取得 CLI 回退路径，不要把
  “MCP 会话缺失”误判为“Praxis 不可用”。
- 项目包装脚本只有在当前工作区明确声明且文件存在时才允许调用；禁止凭历史上下文推断
  `scripts/codex/task.py` 或其他仓库相对入口。
- DBX 调查只使用已提供的 DBX MCP 工具，不调用或回退到 DBX CLI。
- 任何入口都不可用时停止并报告缺失能力，不得伪造 Skill 调用、门禁或需求记录。

## 风险驱动 fast_fix 例外

- 用户明确说“快速修复”“只改这里”“不要走标准流程”“就加个注解”“不要跑测试”或
  “别写测试脚本”时，先把这些表达作为执行约束，不得先运行标准流程命令再解释。
- 已明确根因、只有一个已跟踪业务文件、修改仅为注解、空值判断、条件或参数调整，且不涉及
  数据库结构、API 契约、公共接口、权限、事务、锁或并发时，进入 `fast_fix`。自动记录
  `mode=fast_fix`、`tests=declined_by_user`、`compile=not_requested`、
  `scope=target_file_only`。
- fast_fix 的关键路径只包含：查看目标代码及一个相似写法、修改目标文件、一次与实际风险直接
  相关的检查、汇报未执行验证。不得逐项执行 reopen、route、invoke、complete、gate、
  artifact、record 或 advance；收尾统一使用一次 `praxis fix record`。
- 每条命令执行前必须明确要消除的风险、成功和失败分别改变的决策、是否已有等价证据，以及是否
  有更小直接检查。成功和失败都不改变下一步时禁止执行。
- 禁止为满足 TDD 门禁创建只验证实现形状的测试：不得用反射证明注解存在，不得读取或正则匹配
  源码冒充行为测试，不得只验证一个工具函数调用另一个函数。真实行为必须启动 Spring、
  MyBatis 或数据库且用户选择 fast_fix 时，记录“未运行集成验证”，不要创建替代性假测试。
- fast_fix 默认不运行测试、编译、全量类型检查或质量复核。极小修改预算为 0–2 条命令、
  1–2 分钟；单页面或单方法小修复为 3–5 条命令、3–5 分钟。超过软预算先说明新增风险；
  超过 5 条命令或 3 分钟必须停止。
- 证据以工作树 binding、HEAD 和目标文件指纹为身份；身份未变化时复用已有 CodeGraph、编译、
  类型错误基线、接口、SQL 和调用路径证据，不得机械重跑。
- 不满足任一 fast_fix 条件时回到下列标准流程；不得使用强制覆盖参数伪装低风险。

## 1. 登记需求和知识文档

- 新工程需求开始时，先检查 Praxis 工作空间和关联业务系统、仓库、业务域。
- 调用 Praxis MCP（不可用时使用可解析的 `praxis` CLI）创建需求，完整保留用户原文。
- 核对返回的需求编号和路径，并确认至少存在 `需求总览.md`、`原始需求.md`、`调查分析.md`、`实施计划.md`、`执行进度.md`、`验收结论.md`。
- 新建需求时不要创建工作树。调查、澄清、影响分析和方案文档也不需要工作树。
- 文档投影失败时停止；不要脱离 Praxis 手工伪造另一套需求目录。
- 规划模式明确禁止正式登记需求时，不要为了满足流程而伪造需求。可创建本轮临时
  `investigation_scope`，并通过 `praxis database investigate` 对项目画像已登记的 DBX
  连接（包括已登记的生产连接）做有目的的只读调查。该入口不写需求、文档、产出物或审计状态，返回
  `persisted: false`；进入实施模式后再登记需求并把仍有效的证据正式纳入需求。
- 规划模式的跨模块、公共接口或影响范围调查可通过
  `praxis codegraph investigate <target> --project <项目> --purpose <目的>` 查询项目画像中
  已有且无 pending 的有效索引。该入口不得初始化、同步或持久化索引，返回
  `persisted: false`；进入实施后仍须在需求工作树 binding 上完成正式影响分析。

## 2. 调查和规划

- 只把有证据的结论写入 `调查分析.md`，把经用户确认的范围和步骤写入 `实施计划.md`。
- 把开发约束写入结构化需求约束卡；后续结论改变时用 `supersedes` 明确覆盖旧约束，禁止只在
  聊天或人工文档中留下互相冲突的结论。计划确认时分别保存开发期聚焦 TDD 命令和完整验证
  矩阵的精确 approval receipt。
- 路由业务技能和必要的方法技能，并记录真实调用来源；不要用执行命令冒充技能调用。
- 调查节点必须先路由并完成 `brainstorming`、`grilling` 与 `ponytail`；`grill-me`
  只是用户入口，只有实际执行逐问确认的 `grilling` 才能作为完成凭证。涉及代码定位时条件路由
  `file-search`，缺陷或失败时条件路由 `systematic-debugging`，数据库问题路由 DBX 技能。
- 调查涉及跨模块、公共接口、共享服务、高扇出或影响范围时条件路由
  `codegraph-impact-analysis`；Plan Mode 使用不持久化入口，正式修改使用 binding 审计。
- 节点路由只产生计划。Skill 开始和结束必须分别记录 `skill.invoked` 与 `skill.completed`；
  `skill.routed`、上下文注入或命令历史都不能作为真实调用凭证。
- 只有文档具有有效内容后，才推进需求到 `ready`。
- `03-实施计划.md` 必须在计划阶段填写“验证矩阵（计划阶段确认）”，逐项区分可自动化命令与
  需环境验证、环境依赖、授权状态和证据；空白模板不能绕过 ready 门禁，verifying 阶段只执行
  已确认的矩阵，不临时扩大验证范围。
- 使用 `requirement advance` 一次只推进一个合法状态，并先查看来源状态、目标状态和缺失门禁；
  不再通过重复执行某个阶段命令猜测状态迁移。
- 纯调查、纯文档或无需代码变更的需求不得创建工作树。
- 规划模式的临时数据库调查只允许已登记连接和只读 SQL，已登记的生产连接也允许查询，并自动执行
  `select current_database()`；生产写入、其他写入、锁定读取、连接变更和默认库猜测仍必须阻断。

## 3. 在首次代码修改前隔离

- 只有确认需要修改代码时，才为实际受影响的仓库和阶段创建 Worktrunk 工作树。
- 创建前必须用 `praxis worktree preview` 展示并固定最终工作空间、末级目录和
  分支名；用户确认后以 preview ID 执行 `worktree ensure`，多仓 Git 准备并行。
- 把仓库的 `default_branch` 视为保留本地运行配置的长期本地模板，把唯一的 `template_branches` 项视为上游开发或发布分支。
- 创建需求工作树前，先获取上游最新提交，在承载 `default_branch` 的干净工作树中合并 `origin/<template_branch>`；该分支尚未检出时才创建固定的模板工作树，不得为了同步而切换用户当前分支。
- 同步失败、发生冲突、模板工作树不干净或模板配置不唯一时停止，不得改用上游分支直接创建需求工作树。
- 每个需求使用 `praxis/<需求编号>__<固定简称>` 开发分支；需求工作空间为
  `.worktrees/<需求编号>__<固定简称>`，仓库工作树末级目录为
  `<需求编号>__<固定简称>__<repository_id>`。阶段名称不得进入目录或分支。
- 首次创建时持久化简称快照和 display slug；需求标题后续变化不得自动漂移已有路径或分支。
  内部身份始终使用 `WT-<需求编号>--<仓库ID>`，不得从目录名或分支名反向推断。
- 旧名称必须通过 `praxis worktree migrate-name` 正式迁移，完整移动 Git worktree、重命名分支、
  更新 binding 和产出物路径。Git 交易成功即自动恢复 active，CodeGraph 后台重建；
  Git/路径步骤失败才补偿回旧名称。
- 迁移全程保持 binding 为 `migrating` 并持久化旧路径、分支和状态；进程中断后重复执行同一
  migrate-name 命令完成旧名称恢复与旧路径 CodeGraph 重建，create 在恢复前必须 fail-closed。
- 创建成功后核对需求编号、仓库、阶段、分支、需求工作空间和仓库工作树路径；将 Agent 工作目录切换到需求工作空间，实际 Git 操作切换到对应仓库子目录。
- `worktree ensure` 为每个成功仓库自动生成 coder context。开始编码前核对返回的
  `context_bundles`；若 `context_errors` 非空，保留已创建工作树并先处理上下文诊断。
- 仓库配置了 `local_files` 时，在 CodeGraph 初始化前只从 `project.path` 指向的主仓库复制这些
  ignored 本地运行文件到相同相对路径；不得扫描或批量复制 `.env*`。源缺失、越界、目录或
  不安全符号链接必须阻断并保留 blocked 工作树，禁止静默创建不可运行的环境。
- 仓库配置了 `worktree_setup_commands` 时，创建阶段只做命令、精确包管理器版本和锁文件
  的快速 preflight，不安装依赖。首次需要构建时显式运行 `praxis worktree prepare`；
  仍只按参数向量执行，不通过 shell，不联网回退，不审计命令输出或环境变量。
- 显式准备命令以 `pnpm` 开头时，必须读取仓库根 `package.json#packageManager` 并使用其中
  声明的精确 pnpm 版本；只允许 PATH 中的匹配版本或已安装的 pnpm 工具缓存，不得联网下载。
  声明缺失、格式无效、包管理器不匹配或精确版本不可用时必须阻断；版本声明变化必须使既有
  准备指纹失效并重新准备。
- `--stage` 可省略，缺省只记录内部 `development` 元数据；阶段变化不得创建新的开发分支。
- Git 工作树、白名单本地文件和 binding 就绪即标记 `active`。CodeGraph 以仓库工作树
  路径后台排队，失败只降级图谱能力，不取消 Git 可开发状态。普通调查先用 `rg`，
  低风险局部任务才允许回退。事务、锁、原生 SQL、并发、公共接口、共享服务、跨模块、
  结构迁移和高扇出改动必须在首次编辑前调用 `codegraph-impact-analysis`，等待新鲜索引并
  保存调用路径和 Blast Radius；不得等出现遗漏或返工后才刷新。
- 查询 CodeGraph 状态时优先使用 binding ID 或仓库工作树路径，不得拿根仓库状态代替需求工作树状态。
- 第一次代码编辑前再次检查当前目录位于已绑定工作树。禁止在根工作区或未绑定目录修改业务代码。
- `pre-commit`/`pre-merge` 在主仓库发现业务代码改动且没有 binding 时必须 fail-closed，并提示
  “请走 praxis 工作树”；不得用普通 `rg` 或手工声明替代该守卫。
- 除上述 fast_fix 例外外，功能、缺陷修复、重构和行为变更默认执行 TDD：先编写一个描述期望行为的聚焦测试并观察它
  因缺少目标行为而失败（RED），再写使其通过的最小实现（GREEN），通过后才能重构。测试立即
  通过、因拼写或环境错误失败、先写实现后补测试，都不能登记为 TDD 完成凭证。
- 生成代码、一次性原型或纯声明式配置等例外必须在计划中明确并由用户接受；存在可稳定验证的
  下游契约时优先测试契约。用户明确拒绝聚焦测试时如实记录例外，不能声称执行了 TDD。
- TDD GREEN 后默认调用 `minimum-module-compile`：根据变更文件选择最近的 Maven module、
  pnpm workspace package、UniApp 目标或 Python package，执行最小编译并记录命令和 exit code。
  禁止扩大为全仓构建；无法唯一确定安全命令时暂停并要求登记，不能猜命令。
- 工作树创建或绑定失败时停止，不回退到根工作区继续开发。

## 4. 人工同意边界

- 用户确认代码开发时，默认同时批准计划中明确列出的聚焦 TDD RED/GREEN 命令；开始前将精确
  命令和最小模块编译命令保存为当前需求的 `development_tdd` approval receipt。未获得开发
  同意、未列明命令或用户明确拒绝时不得运行。
- 完整回归、lint、format、typecheck、覆盖率、构建、代码质量复核以及 reviewer/tester Agent
  始终需要独立验证授权；聚焦 TDD 收据不能扩大为这些操作的授权。
- “提交”“推送”“完成”“继续”等指令不等于对质量复核或测试的批准。
- 完整验证、代码质量复核、reviewer/tester Agent、子代理和分支收尾 Skill 命中后先标记
  `blocked_pending_approval`，不得以路由结果代替用户批准。
- 获批时只执行用户同意的具体命令或复核范围；同意仅对当前需求和当前轮次有效，不跨需求复用。
- 可在开发开始时把用户对精确验证矩阵的同意保存为当前需求的 approval receipt；
  只有直接用户授权才能生成收据，“继续/提交/完成”不能推断为授权。
- 工作树绑定、允许路径、密钥检测、提交信息和只读 CodeGraph 新鲜度属于安全门禁，可以自动执行，但不得借安全门禁触发项目质量命令或测试。
- 所有外部命令必须先由 RTK 代理：有专用子命令时使用 `rtk rg`、`rtk mvn` 等适配；测试、
  错误聚合和无专用适配命令分别使用 `rtk test`、`rtk err`、`rtk proxy`。普通文本搜索默认
  使用 `rg`，不是 `grep` 或“rg-grep”；机器 JSON 也使用 `rtk proxy` 保持原始输出。
- 只有错误明确来自 RTK 自身执行失败时才允许直接命令降级，并记录原 RTK 命令、错误和降级
  命令。被代理命令自身返回非零不是 RTK 故障，不得通过直跑掩盖真实失败。

## 5. 进度和交付

- 持续更新 `执行进度.md` 和产出物清单，不以聊天记录代替知识库。
- 代码稳定后再登记产出物；`artifact add` 按“需求+路径” upsert 并刷新哈希。
- 代码改动使用 `code-change` 类型登记，保留仓库、分支、diff 统计和变更文件哈希。
- 工作树内新文件可用 `artifact add --binding <binding_id>` 登记；源路径按 binding 的仓库子目录
  解析，未绑定或跨 binding 的路径继续阻断，提交分支仍是最终交付来源。
- 实施完成后用 `requirement record-implementation` 记录实施维度；多个项目使用重复
  `--project <project>=<artifact-id,...>` 一次原子合并，避免并行登记互相覆盖。验证维度和人工
  验收维度独立。
  用户明确选择不运行某个精确验证项时用 `verification decline` 记录收据，状态只能是 declined，
  不得标为 verified 或 passed。
- 从 verifying 回开发使用带原因的 `requirement reopen`；同一问题默认最多一次恢复、一次重试。
- 完成多个 Skill 后使用 `lifecycle complete-node --used-skill
  <id>=<passed|not_applicable|approval_missing|failed>:<outcome>` 原子写入真实结果、检查门禁并按需
  推进一个状态。未列出的 Skill 不得自动补写为已使用；`approval_missing` 必须显示“实施完成、
  验证待批准”，不得伪装为普通 completed。
- CLI 帮助中的多值参数示例固定为 `--used-skill 'skill-id=passed:结果说明'`：外层单引号包裹，
  值内冒号使用半角 `:`，避免全角标点和 shell 拆词。
- 生命周期为 `in_progress → implemented → verifying → completed`。`implemented` 表示代码实施
  已登记，不代表测试通过或人工验收完成。
- 节点路由统一保存为需求状态名；`investigation`、`analysis`、`planning`、`development`、
  `verification` 会规范化为对应状态，其他未知节点必须失败，不得静默退化为仅业务 Skill。
- 查询单个工作树使用 `worktree status --binding <binding_id>`，避免扫描所有仓库；active binding
  对外状态固定为 `bound_active`，原始 Worktrunk 状态仅作为诊断字段保留。
- subagent 默认使用 `fork_turns=none` 和精简交接包；父节点单写需求状态与 Skill gate，
  子 Agent 只返回改动路径、决策、阻塞和后续请求收据。
- 提交前确认改动只存在于绑定工作树，提交信息关联需求编号。
- 未获质量或测试批准时如实记录“未执行”，不得写成“通过”。
- 交付时报告需求文档路径、工作树路径、实际执行的门禁以及未执行项。
