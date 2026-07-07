# 需求文档与 Worktree

## 定位

业务需求文档与代码 worktree 的统一初始化、迭代和恢复规则。条目按优先级排列。

## 初始化命令

```bash
task req -- init <需求名> <用户原始需求原文>
task project -- start <project> <需求名> <用户原始需求原文>
task context -- --brief <project> <需求名>
task context -- <project> <需求名>
```

## 新对话启动门禁

**P0**

- 新对话收到业务需求后，先判定是否涉及业务代码；涉及代码新增、修改、删除或生成时，第一步必须是 `task project -- start <project> <需求名> <用户原始需求原文>`，不得先读实现文件、改代码或在主仓直接验证。
- `start` 是需求目录与主任务 worktree 的统一入口；缺需求目录或缺代码 worktree 时，当前任务状态为 blocked，必须补跑 `start` 或向用户报告主仓污染/同步冲突等具体阻塞。
- 只有答疑、只读调查、纯文档、规则维护、流程纠偏且不改业务代码时，才允许跳过代码 worktree；跳过时最终回复必须写明豁免原因、替代动作和风险。
- “改动很小”“只改一行”“只生成文件”“先临时修一下”不是豁免理由。

## 目录与初始化规则

**P0**

- `task req -- init` 创建 v2 标准目录（`README.md`、`00-原始需求/`、`01-`~`04-` 子目录）。
- 业务需求必须把用户原始需求原文写入 `00-原始需求/`；缺原文或占位词时脚本应失败。
- 非业务需求（规则维护、流程纠偏、工具配置、过程改进）**不**运行 `task req -- init`，直接更新 `AGENTS.md`、`.rule/`、`.skill/` 或 `todo.md`。

**P1**

- 原文不得缩减为摘要；长 SQL、脚本、接口示例、截图说明须完整保留；附件存 `00-原始需求/附件/` 并建链接。
- 需求名须含可识别业务对象；纯文档业务需求也须 `task req -- init`。
- 优先使用统一入口，避免手工 `mkdir`；误建目录后补跑同名 `task req -- init`（幂等，不覆盖人工内容）。
- 非代码任务未创建 worktree 或未用统一命令时，交付说明须写明豁免原因、替代动作和风险；涉及业务代码改动时不得豁免。

## 迭代与回写

**P0**

- 第一轮调查后必须 `task req -- iter <需求名> analysis <主题>` 新增证据化分析；只更新 README 视为文档门禁未完成。
- 阶段完成后不得保留“待补充”占位；最终回复前检查 README 最新结论。

**P1**

- `task req -- iter` 按 `序号-YYYY-MM-DD-HHmm-主题.md` 新增文件，不覆盖旧分析/规划/进度；已有完整阶段正文时使用 `--body-file <阶段正文.md>` 直接写入，避免生成后再替换模板占位。
- 分析文件须写清：调查对象、来源证据、关键路径/表字段/SQL、结论、未决项、下一步。
- 调查后写 analysis，方案确定后写 plan，实现/验证/阻塞后写 progress。
- `task req -- index` 回写 README 索引；`task req -- check` 检查证据化与占位状态。

```bash
task req -- iter <需求名> analysis|plan|progress <主题>
task req -- iter <需求名> analysis|plan|progress <主题> --body-file <阶段正文.md>
task req -- check <需求名>
task req -- index <需求名>
task req -- db-plan <需求名>
```

## 命令语义

- `context`：主对话与 worker 最小上下文（写入 `$PRAXIS_DIR/context/`；Taskfile 默认 `.praxis/out/runtime/context/`）。
- `preflight`：恢复报告（目录、阶段文件、worktree、涉库风险、验证命令）。
- `guard` / `migration-check`：文档与迁移门禁组合检查。
- `task project -- status <project>` 可只读查看主项目状态；`verify|run|shell` 用于代码项目时必须追加 `<需求名>` 并自动定位 `codex/*-需求名` worktree。
- 代码项目缺少需求名时，`run|shell` 必须失败并提示先执行 `task project -- start <project> <需求名> <用户原始需求原文>`。
- 接手卡住/恢复中的需求：先读 `AGENTS.md`、README、最新阶段文件，再 `context --brief`/`preflight`；需要完整角色协议或专题规则时再运行完整 `context`。

## Worktree 与分支

**P0**

- 聚合根不是单一 Git 仓库；分支/worktree 操作在具体子仓库执行。
- Codeup HTTPS Git 操作优先使用 `task`/`rtk` 工作流入口；必须手工执行底层 Git 时使用 `rtk git ...` 或 `/usr/bin/git ...`，禁止裸 `git ...`。
- 所有代码类需求无论大小，凡涉及业务代码新增、修改、删除或生成，必须创建主任务 worktree。
- 从 `defaultBranch` 创建（配置于 `.praxis/projects.toml`，PDA/Web/后端通常为 `local`）。
- 创建或同步需求 worktree 前，目标主项目仓库必须干净；若 `git status --short` 存在任何未提交变更或未跟踪文件，立即暂停任务并报告用户，等待确认处理方式。
- 创建前必须先同步 `upstreamBranch -> defaultBranch`；统一脚本执行 `fetch + switch defaultBranch + merge --no-edit origin/<upstreamBranch>`，失败或冲突时不得继续基于旧 `local` 创建需求 worktree。
- 主项目仓库有污染时，禁止自行 stash、restore、commit、手工绕过统一命令、基于旧 `local` 建 worktree 或继续在主项目仓库开发。
- 禁止对 PDA 默认用 `develop` 作开发基座；交付 feature 从 `upstreamBranch` 创建（后端/Web 为 `develop`，PDA 为场景分支如 `station/base`、`mes`、`base`）。

**P1**

- 优先 `task project -- start <project>`；默认路径 `.worktrees/<project>/<YYYY-MM-DD-需求名>-dev/`；正式交付 `.worktrees/<project>/<YYYY-MM-DD-需求名>-feature/`。
- Web worktree 须同步被忽略的本地配置（如 `apps/web-antd/.env.development`）。
- 分支命名默认 `codex/YYYYMMDD-任务名`；禁止 `git reset --hard` 等破坏性切换。
- 需求 worktree 不强制合并回 `local`。

**P2 — 非代码豁免**

答疑、只读调查、纯文档或规则维护且不改业务代码的任务可不建 worktree。涉及代码改动时不得以“微小修复”“单文件改动”“文案很小”作为豁免理由。

```bash
task project -- worktree backend <任务名>
task project -- worktree web <任务名> [基座分支]
```

分支职责见 `.rule/global/04-本地开发与交付工作流.md`。
