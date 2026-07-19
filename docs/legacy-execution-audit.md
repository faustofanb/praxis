# 旧版执行链审计

## 审计边界

- 证据源只读：`/Users/fausto/plugins/praxis-workflow`、`/Users/fausto/Desktop/workplace/project/ifc/mom`、`/Users/fausto/Desktop/workplace/project/ifc/aotu`。
- 新实现边界：审计用于归属和行为重写，不是复制清单。
- 旧执行链共同事实：旧插件通过 `scripts/praxis_init_workspace.py`、`scripts/praxis_sync_profile.py`、`scripts/praxis_auto_sync.py` 和 profile 内 `scripts/praxis/task.py` 组合运行；真实 workspace 还保存 `.praxis/core.toml`、`.praxis/project-adapter.toml`、`.praxis/commands.toml`、`.praxis/extensions/ifc-mom/*`、`scripts/praxis/*` 与 `praxis.projects.toml`。

### 1. workspace init

- 入口文件和命令：`scripts/praxis_init_workspace.py`；旧 README 暴露 `python scripts/praxis_init_workspace.py <workspace> --name "IFC MOM" --profile ifc-mom`。
- 完整调用链：`main()` -> `initialize_workspace_with_profiles()` -> `initialize_workspace()` -> 可选 `sync_profile(workspace, profile, force=force)`。
- 读取配置：插件内 `templates/AGENTS.md.tpl`、`praxis.toml.tpl`、`praxis.projects.toml.tpl`、`core.toml.tpl`、`project-adapter.toml.tpl`、`turn.schema.json`、`delivery.schema.json`；可选读取 `profiles/<id>/profile.toml`。
- 写入状态：目标 workspace 根目录写 `AGENTS.md`、`praxis.toml`、`praxis.projects.toml`、`.praxis/core.toml`、`.praxis/project-adapter.toml`、`.praxis/contracts/agents/*.json`；带 profile 时继续复制 profile-managed files。
- 模板/规则/技能：模板来自插件 `templates/`；profile sync 后引入 `.praxis/extensions/ifc-mom/rules` 与 `skills`。
- 项目内静态依赖：初始化结果把共享 runtime 入口和规则投放进 workspace，后续命令依赖这些文件存在。
- MOM/AOTU 特化：`--profile ifc-mom` 将 MOM/AOTU 共用 profile 复制到任意目标。
- 目标架构层：`runtime kernel` 负责 init；workspace 只保留 `.praxis/workspace.toml` 的事实和 state/cache/generated，不复制 runtime/rules/templates。
- 证据：`scripts/praxis_init_workspace.py:17-25`、`28-55`、`62-82`；`README.md:77-85`。

### 2. workspace check

- 入口文件和命令：`scripts/praxis_check_workspace.py <workspace> --json`。
- 完整调用链：`main()` -> `analyze_workspace()` -> `collect_projects()` -> `report_to_json()`。
- 读取配置：检查 `AGENTS.md`、`praxis.toml`、`praxis.projects.toml`、`.praxis/core.toml`、`.praxis/project-adapter.toml`、contracts；读取 `praxis.projects.toml` 并提取 `path/kind/defaultBranch/upstreamBranch`。
- 写入状态：无写入，只输出文本或 JSON。
- 模板/规则/技能：只检查 `.praxis/rules/praxis-workflow.md` 是否缺失；不加载技能。
- 项目内静态依赖：旧 check 把 `.praxis/core.toml` 和 `.praxis/project-adapter.toml` 当必需文件。
- MOM/AOTU 特化：项目 facts 来自各 workspace 的 `praxis.projects.toml`，MOM/AOTU 的分支和数据库差异在该文件中。
- 目标架构层：`runtime kernel` + `workspace facts`；新 check 应验证 `.praxis/workspace.toml`、state JSON、resolved-profile cache，而不是要求旧静态 core/adapter。
- 证据：`scripts/praxis_check_workspace.py:15-23`、`36-65`、`68-90`、`103-134`。

### 3. profile resolution

- 入口文件和命令：旧 `task system -- praxis-profile`；旧 profile sync 内 `profile_metadata(profile)` 也解析 profile。
- 完整调用链：`task.py run_praxis_system_action('praxis-profile')` -> `write_praxis_profile_report()` -> `praxis_profile_payload()` -> `read_toml(.praxis/core.toml)` + `read_toml(.praxis/project-adapter.toml)` + `validate_praxis_profile()`。
- 读取配置：`.praxis/core.toml`、`.praxis/project-adapter.toml`、`.praxis/commands.toml`、`praxis.projects.toml` 或 `.praxis/projects.toml`、`.praxis/extensions/*/extension.toml`。
- 写入状态：`.praxis/out/profile.json`。
- 模板/规则/技能：校验 adapter 的 `rule_paths`、`skill_paths` 和 extension 指向的 rules/skills/templates。
- 项目内静态依赖：强依赖 workspace 本地 `.praxis` 静态 profile 和 extension 目录。
- MOM/AOTU 特化：`profiles/ifc-mom/profile.toml` 声明 `extension_root = ".praxis/extensions/ifc-mom"`，真实 workspace 的 project facts 决定实际项目组合。
- 目标架构层：`profile composition` + `runtime kernel`；新 resolver 应从已安装包资源解析 capability/profile，不读 workspace 静态 runtime。
- 证据：`task.py:160-163`；`momlib/praxis_profile.py:12-22`、`81-164`、`167-223`；`profiles/ifc-mom/profile.toml:1-7`。

### 4. profile sync

- 入口文件和命令：`scripts/praxis_sync_profile.py <workspace> ifc-mom --force [--prune] [--json]`；workspace 批量入口是 `scripts/praxis_sync_workspaces.py`。
- 完整调用链：`main()` -> `sync_profile()` -> `profile_metadata()` -> `sync_sources()` -> `shutil.copy2()`；`--prune` 先 `_prune_managed_files()`。
- 读取配置：插件 `profiles/<profile>/profile.toml`、profile source tree、`runtime/praxis_core`。
- 写入状态：复制 profile files 到 workspace；额外把 `runtime/praxis_core` 复制到 `scripts/praxis/praxis_core`；可删除 managed/obsolete roots 下 stale 文件。
- 模板/规则/技能：复制 `.praxis/extensions/ifc-mom/rules`、`skills`、templates 和 `scripts/praxis`。
- 项目内静态依赖：同步后 workspace 本地持有 canonical 静态副本。
- MOM/AOTU 特化：只有 `ifc-mom` 一个 profile，MOM/AOTU 都靠同一 profile 加各自 workspace facts。
- 目标架构层：旧行为拆分为 `profile composition`、`reusable capability`、`platform adapter`；新架构禁止目录同步成为 runtime 模型。
- 证据：`scripts/praxis_sync_profile.py:14-21`、`52-77`、`98-127`、`130-155`、`158-181`；`README.md:117-121`。

### 5. project inspect/list

- 入口文件和命令：`task list`、`task project -- status|verify|run|shell|worktree <project> ...`。
- 完整调用链：`task.py main()` -> `list_projects(load_config())` 或 `run_praxis_project_action()` -> `run_project_action()` -> `project_actions.*`/`project_config()`/`project_dir()`。
- 读取配置：`praxis.projects.toml` 优先，其次 `.praxis/projects.toml`、`.codex/workspace-projects.toml`；每个项目读取 `path`、`kind`、`verify`、`run`、`defaultBranch`、`upstreamBranch`。
- 写入状态：list/status/shell 无写入；`verify/run` 透传到项目进程；`worktree` 可能创建 Git worktree。
- 模板/规则/技能：无直接模板；context/adapter 规则会引用项目 kind。
- 项目内静态依赖：旧事实文件是 workspace 根 `praxis.projects.toml`。
- MOM/AOTU 特化：MOM/AOTU 的项目路径、数据库和分支差异全部在各自 `praxis.projects.toml`，例如 MOM backend `defaultBranch=local/upstream=develop`，AOTU backend `defaultBranch=auto/local/upstream=auto/test`。
- 目标架构层：`workspace facts`；按新计划迁入 `.praxis/workspace.toml` 项目事实注册表，禁止 DB 密码/runtime state 混入。
- 证据：`momlib/config.py:13-28`、`31-66`；`task.py:462-475`、`429-459`；MOM `praxis.projects.toml:7-83`；AOTU `praxis.projects.toml:7-89`。

### 6. quick start

- 入口文件和命令：`task project -- quick <project> <简短任务名>`；平台 prompt 暴露 `/praxis-quick`。
- 完整调用链：`task.py run_project_action('quick')` -> `start_quick_task()` -> `resolve_task_policy(mode='quick')` -> `create_worktree(require_requirement=False)` -> `write_quick_task_state()`。
- 读取配置：workspace project facts、`.praxis/extensions/*/manifest.toml` 的 `[task.quick]`、Git refs/worktree list。
- 写入状态：创建 `.worktrees/<project>/<date-task>-dev`；创建 Git branch；写 `.praxis/tasks/<id>.toml`。
- 模板/规则/技能：`manifest.toml [task.quick]` 声明 commands/gates；不创建需求文档模板。
- 项目内静态依赖：读取 workspace-local extension manifest 和同步后的 `scripts/praxis/praxis_core`。
- MOM/AOTU 特化：quick policy 从 `ifc-mom` extension 命名空间读取，但行为本身是通用 L0 task。
- 目标架构层：`runtime kernel` + `workspace runtime state`；policy 应来自 capability manifest，state 写 `.praxis/state/tasks/*.json`。
- 证据：`commands/praxis-quick.toml:1-2`；`task.py:436-440`；`quick_tasks.py:20-73`；`git_worktree.py:252-343`。

### 7. quick check/resume

- 入口文件和命令：`task project -- quick-check <project> <简短任务名>`；旧 README 提到 quick 可恢复状态，但没有独立 CLI resume 入口。
- 完整调用链：`task.py run_project_action('quick-check')` -> `check_quick_task()` -> `project_worktree_dir()` -> `changed_files()` -> `resolve_task_policy(mode='quick', changed_files=files)`。
- 读取配置：project facts、extension manifest task policy、Git changed files、已注册 worktree。
- 写入状态：quick-check 无写入；旧 resume 通过 worktree/branch/state 文件人工恢复，没有独立命令。
- 模板/规则/技能：quick policy gates 来自 manifest；高风险边界来自 `praxis_core.policy`。
- 项目内静态依赖：读取 workspace extension manifests 和 copied shared core。
- MOM/AOTU 特化：命名仍在 `ifc-mom` extension；风险类型包含 MOM 报表/数据库术语。
- 目标架构层：`runtime kernel`；新 CLI 应提供显式 `task resume` 并读 `.praxis/state/tasks/*.json`。
- 证据：`README.md:91-103`；`task.py:441-444`；`quick_tasks.py:76-94`。

### 8. formal start

- 入口文件和命令：`task project -- start <project> <需求名> <原始需求>`；仅文档类可用 `task req -- init`。
- 完整调用链：`task.py run_project_action('start')` -> `start_requirement()` -> `doc_init()` -> `create_worktree()` -> `assert_requirement_binding()` -> `update_context_index()` -> `context_command()`。
- 读取配置：project facts、docs path、business-domain-rules、Git branch/worktree state。
- 写入状态：`docs/02-req/YYYY-MM/YYYY-MM-DD-需求名/` 文档树；代码项目创建 `.worktrees/...-dev` 和 Git branch；更新需求 README。
- 模板/规则/技能：需求 README、原始需求、阶段目录模板；README 写入 `rule_skill_paths(project)`。
- 项目内静态依赖：docs service 从 `.praxis/extensions/ifc-mom/*` 引用规则/技能。
- MOM/AOTU 特化：需求 frontmatter tags 使用 `ifc-mom/*`；业务聚合规则来自 `business-domain-rules.json`。
- 目标架构层：`runtime kernel` + `requirement-lifecycle reusable capability` + `workspace runtime state`；模板保留在 capability 资源中，实例文档保留 workspace 文档路径。
- 证据：`commands/praxis-start.toml:1-2`；`task.py:431-435`；`requirements.py:32-42`；`docs.py:324-482`。

### 9. worktree create/reuse/cleanup

- 入口文件和命令：`task project -- worktree <project> <需求名>`、formal/quick start 隐式调用、`task delivery -- cleanup <project> <需求名>`。
- 完整调用链：create/reuse：`create_worktree()` -> `worktree_creation_lock()` -> `project_worktree_dirs()` -> Git `worktree list --porcelain`/`for-each-ref`/`worktree add`；cleanup：`cleanup_requirement()` -> `project_worktree_dirs()` -> status check -> Git `worktree remove`/`branch -D`/`worktree prune`。
- 读取配置：project path、defaultBranch、upstreamBranch、worktreeRoot、developmentBranchPrefix；Git refs/status/worktree list。
- 写入状态：`.worktrees/...`、`.locks/*.lock`、Git branch/worktree metadata；pnpm-web 复制被忽略本地 `.env*` 等运行配置到 worktree。
- 模板/规则/技能：无模板；安全策略硬编码在 runtime。
- 项目内静态依赖：依赖 workspace project facts；状态散落在 Git 和 `.worktrees`。
- MOM/AOTU 特化：PDA 分支说明写在注释和 project facts；web local config sync 是技术栈能力。
- 目标架构层：`runtime kernel` + `worktree-lifecycle reusable capability` + `workspace runtime state`；cleanup 必须 fail closed。
- 证据：`git_worktree.py:54-69`、`124-157`、`193-249`、`252-343`；`finish.py:431-461`。

### 10. requirement document lifecycle

- 入口文件和命令：`task req -- init|iter|check|index|index-all|domain-index|db-plan ...`。
- 完整调用链：`task.py run_praxis_requirement_action()` -> `doc_init()`/`doc_iter()`/`docs_check()`/`docs_index()`/`write_requirement_global_index()`/`write_domain_index()`/`db_plan()`。
- 读取配置：docs project path、business-domain-rules、需求目录现有 README/阶段文档/附件。
- 写入状态：`docs/02-req` 下原始需求、分析、计划、进度、产出物目录；README 索引；domain/global indexes。
- 模板/规则/技能：文档模板内嵌在 `docs.py`；rules/skills 通过 `rule_skill_paths()` 写入 README。
- 项目内静态依赖：模板和规则引用在 workspace-local scripts 与 `.praxis/extensions` 中。
- MOM/AOTU 特化：frontmatter tags `ifc-mom/*`，产出物目录包含 `MAGIC-API脚本草案`，domain rules 含 WMS/PDA/MES 等业务词。
- 目标架构层：`reusable capability` + `domain capability`；实例文档是 workspace fact/用户产物，不是 runtime。
- 证据：`task.py:187-235`；`docs.py:324-635`；`workflow_checks.py:390-505`、`508-552`。

### 11. changed-file classification

- 入口文件和命令：`task gate -- change-check <project> <需求名>`、`task gate -- guard|ready`、`verify.py` 内 changed files；前端分类器 `frontend_changed.ts`。
- 完整调用链：`change_check()` -> Git changed/commit files -> `classify_changed_file()`；frontend verify -> `classify_frontend()` -> Bun `frontend_changed.ts`。
- 读取配置：Git status/log/diff-tree；project kind；需求目录 SQL 中间产物。
- 写入状态：change-check 主要输出终端报告；ready 会间接写 readiness report。
- 模板/规则/技能：分类规则硬编码 Python/TypeScript；delivery policy 参与检查。
- 项目内静态依赖：使用 workspace-local scripts；前端分类器路径存在旧 bug/漂移风险：`verify.py` 指向 `scripts/codex/frontend_changed.ts`，profile 实际文件在 `scripts/praxis/frontend_changed.ts`。
- MOM/AOTU 特化：分类术语含 MagicAPI、菜单授权、PDA、报表等。
- 目标架构层：`runtime kernel` + `database-change-classification reusable capability` + stack/domain capability rules；通用分类器不得硬编码 MOM/AOTU。
- 证据：`workflow_checks.py:79-83`、`293-387`；`verify.py:187-200`；`frontend_changed.ts:1-95`。

### 12. database/migration checks

- 入口文件和命令：`task req -- db-plan <需求名>`、`task gate -- migration-check <project> <需求名>`、`task gate -- guard|ready`。
- 完整调用链：`db_plan()` 读取 workspace DB facts 并输出只读 SQL 调查清单；`migration_check()` -> `changed_files()` -> `is_official_migration()` -> `has_intermediate_sql()`；`guard_check()` 组合 docs/change/migration/common path。
- 读取配置：`[database.local]`、需求目录 `04-产出物/SQL` 或 legacy `中间文档/*.sql`、Git changed files。
- 写入状态：db-plan 不写；guard/ready 可能写 evidence/readiness。
- 模板/规则/技能：SQL 调查模板硬编码；migration 规范来自 backend rules/skills。
- 项目内静态依赖：workspace local DB name 直接在 `praxis.projects.toml`，旧 scripts 读取后输出。
- MOM/AOTU 特化：MOM/AOTU database 名称和多生产分支差异在 workspace facts；MagicAPI/菜单授权触发高风险。
- 目标架构层：`domain capability` + `migration-checks reusable capability`；workspace 只保存 DB 引用名/非秘密元数据，不能保存密码。
- 证据：`workflow_checks.py:20-41`、`104-111`、`508-568`、`571-590`；MOM `praxis.projects.toml:7-10`；AOTU `praxis.projects.toml:7-23`。

### 13. docs/Tolaria flows

- 入口文件和命令：`task docs -- tolaria-check [<需求名>|--all]`、`task docs -- tolaria-publish <需求名>|--all`、`/praxis-tolaria-check`。
- 完整调用链：`task.py run_praxis_docs_action()` -> `tolaria_check()`/`tolaria_publish()` -> `tolaria_scan_roots()` -> markdown/frontmatter scan 或 `publish_tolaria_types_and_views()` + `publish_requirement_tolaria_index()`。
- 读取配置：docs project path、`docs/02-req`、`docs/03-etl`、需求目录 Markdown。
- 写入状态：check 写 `.praxis/out/tolaria/tolaria-check.json`；publish 写 `docs/types/*.md`、`docs/views/*.yml`、`04-产出物/Tolaria知识索引.md` 和 publish report。
- 模板/规则/技能：Tolaria Type/view 模板内嵌；skills 包含 `mom-tolaria-vault`。
- 项目内静态依赖：运行逻辑在 workspace scripts；输出写 workspace docs 与 `.praxis/out`。
- MOM/AOTU 特化：tags 与 saved views 使用 `ifc-mom/etl`、`ifc-mom/tolaria`。
- 目标架构层：可选 `domain capability`；未启用时返回 `capability_not_enabled`。
- 证据：`commands/praxis-tolaria-check.toml:1-2`；`task.py:238-256`；`docs_tolaria.py:89-148`、`159-292`、`295-362`。

### 14. verification

- 入口文件和命令：`task project -- verify <project> [需求名]`，底层 `uv run scripts/praxis/verify.py <project> --repo <repo>`。
- 完整调用链：`task.py` -> `verify_project()` -> `run_exit([uv, run, verify.py, project, --repo, repo])` -> `verify.py main()` -> `changed_files()` -> kind-specific verifier。
- 读取配置：project facts、Git changed files、package.json/pom.xml、frontend classifier 输出、env flags `MOM_WEB_PACKAGE_TYPECHECK`/`MOM_PDA_FULL_TYPECHECK`。
- 写入状态：不写状态文件；打印 Markdown 验证证据。
- 模板/规则/技能：验证证据模板内嵌；frontend 分类在 TypeScript。
- 项目内静态依赖：旧验证从 workspace-local scripts 启动。
- MOM/AOTU 特化：project kinds 覆盖 java-maven/pnpm-web/pnpm-uniapp；env 变量以 MOM 命名；Maven profile 默认 `dev`。
- 目标架构层：`runtime kernel` + stack capabilities (`java-maven`、`pnpm-web`、`pnpm-uniapp`、`npm-dashboard`)。
- 证据：`project_actions.py:38-42`；`verify.py:34-65`、`68-184`、`203-262`、`298-328`。

### 15. delivery

- 入口文件和命令：`task delivery -- status|finish|commit-split|deliver|cleanup[-all] ...`。
- 完整调用链：`task.py run_praxis_delivery_action()` -> grouped or single action -> `delivery_status()`/`write_execution_compliance_evidence()` + `finish_requirement()`/`split_commit_requirement()`/`deliver_requirement()`/`cleanup_requirement()`。
- 读取配置：project facts、Git status/log/refs、requirements docs、delivery policy、readiness/context packets。
- 写入状态：`commit-split` 创建 Git commits；`deliver` 创建 feature branch 并 cherry-pick；`cleanup` 删除 worktrees/branches；`finish` 写 `.praxis/evidence/*execution-compliance.json`。
- 模板/规则/技能：delivery command/handoff 文本内嵌；delivery contract schema 在 `.praxis/contracts/agents/delivery.schema.json`。
- 项目内静态依赖：旧 delivery 强依赖 workspace scripts、contracts、Git branches。
- MOM/AOTU 特化：commit 示例 `feat(mes)`；feature branch from upstream；AOTU delivery schema 比 MOM 多 `confirmedCommitAllowlist`、`candidate_audit` 等安全字段。
- 目标架构层：`runtime kernel` + `delivery reusable capability` + `workspace runtime state`；真实 remote rewrite/push 必须只输出方案，等待授权。
- 证据：`task.py:383-426`；`finish.py:196-245`、`246-287`、`292-379`、`380-461`；MOM/AOTU `delivery.schema.json`。

### 16. session-start integration

- 入口文件和命令：Claude/Codex `hooks/hooks.json` 的 `SessionStart`；OMP extension `adapters/omp/praxis-auto-sync.mjs`。
- 完整调用链：Claude/Codex hook 先 `node hooks/ponytail-activate.js`，再 `python3 scripts/praxis_auto_sync.py || true`；OMP `pi.on('session_start')` -> `runPraxisAutoSync()` -> spawn python -> auto_sync JSON -> UI notify。
- 读取配置：workspace discovery 查 `praxis.toml` + `praxis.projects.toml`；`.praxis/plugin-sync.toml`；`.praxis/extensions/*/extension.toml`；plugin profile assets。
- 写入状态：auto-sync 可写 `.praxis/profile-sync.lock` 并在漂移时复制/删除 profile-managed files；Ponytail 写模式状态。
- 模板/规则/技能：Ponytail hooks 读取 mode/config/instructions；Praxis auto-sync 读取 profile rules/skills。
- 项目内静态依赖：旧 session-start 直接执行 Python 并修复 workspace 静态文件。
- MOM/AOTU 特化：检测 packaged profile `ifc-mom` 并同步该 profile。
- 目标架构层：`platform adapter` 只调用 `praxis workspace check --json` 和可重建 projection，不执行 profile 全量同步。
- 证据：`hooks/hooks.json:3-27`；`scripts/praxis_auto_sync.py:43-87`、`182-235`；`adapters/omp/praxis-auto-sync.mjs:1-41`；`README.md:54-64`。

### 17. RTK fallback

- 入口文件和命令：platform commands 优先提示 `rtk task ...`；runtime subprocess wrapper `momlib/process.py`。
- 完整调用链：human-facing Git command -> `run_command()` -> `command_argv()` -> if `git` and `shutil.which('rtk')` then `[rtk, *argv]` else `/usr/bin/git ...`；machine capture -> `capture()` -> `machine_command_argv()` -> `/usr/bin/git ...` bypass RTK。
- 读取配置：PATH 上的 `rtk`；env assignments；Git command argv。
- 写入状态：无 Praxis state；只影响子进程 stdout/stderr。
- 模板/规则/技能：`skills/rtk/SKILL.md`、command prompts。
- 项目内静态依赖：旧实现硬编码 `/usr/bin/git` fallback。
- MOM/AOTU 特化：无业务特化；是通用输出优化。
- 目标架构层：`runtime kernel` command runner；新实现不得硬编码 Homebrew/系统路径，机器 Git 必须绕过 RTK。
- 证据：`momlib/process.py:11-18`、`32-52`、`87-113`；`commands/praxis-check.toml:1-2`；`commands/praxis-tolaria-check.toml:1-2`。

### 18. Ponytail integration

- 入口文件和命令：`hooks/ponytail-activate.js`、`hooks/ponytail-subagent.js`、`hooks/ponytail-mode-tracker.js`、OMP `adapters/omp/ponytail-extension.mjs`、commands `ponytail*.toml`。
- 完整调用链：SessionStart/SubagentStart/UserPromptSubmit hooks -> Node scripts -> Ponytail config/instructions/mode tracker；OMP registers `/ponytail` command, resolves mode, persists default, appends session entry, updates status.
- 读取配置：`hooks/ponytail-config.js`、`hooks/ponytail-instructions.js`、vendored `vendor/ponytail.lock.json`、skills under `skills/ponytail*`。
- 写入状态：mode/default state through hook config and OMP session entries; vendor check reads hash/allowlist.
- 模板/规则/技能：Ponytail skills and command prompts；vendored Ponytail 4.8.4 assets。
- 项目内静态依赖：插件内 vendor，不应复制进 workspace；old plugin couples Ponytail and Praxis in same package.
- MOM/AOTU 特化：无 MOM/AOTU 业务特化。
- 目标架构层：`platform adapter` 或独立 optional capability/adapter；core command/profile/worktree must not depend on Ponytail.
- 证据：`package.json:7-15`；`hooks/hooks.json:3-55`；`adapters/omp/ponytail-extension.mjs:13-145`；`commands/ponytail*.toml`；`vendor/ponytail.lock.json`。

## MOM/AOTU 真实差异

- 静态 Praxis 文件集（`.praxis` 与 `scripts/praxis`，排除 out/cache/pyc/DS_Store）各 181 个，路径集合完全相同。
- 内容哈希仅 1 个文件不同：`.praxis/contracts/agents/delivery.schema.json`。
- MOM 版 delivery schema 的 `input_required` 为 `requirementDir/readinessJson/guardOutput/changeCheckOutput/commitList`，`output_required` 为 `readiness/blockers/commands_checked/required_confirmations`，forbidden 较少。
- AOTU 版新增 `confirmedCommitAllowlist` 输入，新增 `confirmed_commits/excluded_commits/candidate_audit` 输出，forbidden 新增 `implicit_non_test_commit_filtering` 和 `include_test_support_without_confirmation`，是更强交付确认约束。
- 业务差异主要在 workspace facts：数据库、分支、项目标签和 prodBranches；应进入各自 workspace facts/profile parameters，不得硬编码进通用 runtime。
