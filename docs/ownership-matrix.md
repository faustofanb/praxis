# 文件所有权矩阵

## 允许分类

本矩阵只使用十个允许层级：`runtime kernel`、`reusable capability`、`stack capability`、`domain capability`、`profile composition`、`workspace facts`、`workspace runtime state`、`generated projection/cache`、`platform adapter`、`obsolete`。

## 所有权原则

- 旧文件不是迁移清单；只有行为和归属被保留。
- 共享执行逻辑归 `runtime kernel`，不得复制到 workspace 或 profile。
- 规则、模板、检查计划按能力归 `reusable capability`、`stack capability` 或 `domain capability`。
- profile 只组合 capability 和参数，不能承载 runtime、事实注册表、凭据或运行状态。
- 新计划把项目事实注册表收回 `.praxis/workspace.toml`；旧根目录 `praxis.projects.toml` 是事实来源证据，不作为新布局惯性保留。
- profile 源内旧 `.praxis/out/` 是运行输出混入包资产的反例，必须拆到 state/cache/generated，而不是随 profile 打包。

| 旧文件或文件类 | 旧职责 | 新归属 | 新处理 |
|---|---|---|---|
| `scripts/praxis_init_workspace.py` | 初始化 workspace 并复制 thin templates/profile | `runtime kernel` | 重写为 `WorkspaceService.init`；只写允许的 workspace facts/state/cache/generated。 |
| `scripts/praxis_check_workspace.py` | 检查旧 thin files 和 root project registry | `runtime kernel` | 重写为 `WorkspaceService.check`；检查 `.praxis/workspace.toml`、state JSON、profile resolve/cache。 |
| `scripts/praxis_sync_profile.py` | 将 packaged profile、rules、skills、runtime 复制到 workspace | `obsolete` | 废弃目录同步模型；保留依赖解析行为到 profile resolver/capability registry。 |
| `scripts/praxis_auto_sync.py` | SessionStart 自动探测并修复 profile drift | `platform adapter` | 改为 adapter 调用 `praxis workspace check --json` 和重建 generated projection；不得复制 runtime/profile。 |
| `scripts/praxis_sync_workspaces.py` | 从本地 registry 批量同步 workspace | `obsolete` | 不迁移；新项目不从插件反向同步 canonical files 到 workspace。 |
| `scripts/praxis_build_adapters.py` | 从 command metadata 生成平台投影 | `runtime kernel` | 重写为 manifest renderer；输出只属于 package/adapters 或 workspace generated projection。 |
| `scripts/praxis_vendor_ponytail.py` | 校验/更新 vendored Ponytail | `platform adapter` | 保留为可选 adapter/vendor 边界；core 不依赖。 |
| `scripts/praxis_verify_package.py` | 包完整性检查 | `runtime kernel` | 重写为 `doctor`/release verify 的内部检查。 |
| `runtime/praxis_core/policy.py` | quick/formal policy decision | `runtime kernel` | 合并进统一 task policy；规则从 capability manifest 输入。 |
| `runtime/praxis_core/quick_task.py` | 写 quick task state | `runtime kernel` | 改写 `.praxis/state/tasks/*.json`，不复制到 `scripts/praxis/praxis_core`。 |
| `profiles/ifc-mom/profile.toml` | 单一 ifc-mom profile metadata 和 managed_roots | `profile composition` | 拆成 `profiles/base`、`java-vue`、`mom`、`aotu` 薄 manifests。 |
| `profiles/ifc-mom/scripts/praxis/task.py` | 旧 task CLI 分发 | `runtime kernel` | 重写为安装包 `praxis` CLI；命令组稳定中文 help/JSON。 |
| `profiles/ifc-mom/scripts/praxis/momlib/config.py` | 读取 root/legacy project facts 和 DB facts | `workspace facts` | 项目事实迁入 `.praxis/workspace.toml`；DB 只保留引用/非秘密元数据。 |
| `profiles/ifc-mom/scripts/praxis/momlib/praxis_profile.py` | 校验 workspace-local core/adapter/extensions | `runtime kernel` | 重写为 profile/capability resolver；不读 workspace 静态 core。 |
| `profiles/ifc-mom/scripts/praxis/momlib/praxis_templates.py` | 模板渲染和 rule/skill 检查 | `reusable capability` | 模板归 capability resource；渲染由 runtime 调度。 |
| `profiles/ifc-mom/scripts/praxis/momlib/quick_tasks.py` | quick task worktree 和 state | `runtime kernel` | 行为保留；state 写 `.praxis/state/tasks/*.json`。 |
| `profiles/ifc-mom/scripts/praxis/momlib/requirements.py` | formal start 绑定 docs/worktree/branch | `runtime kernel` | 行为保留；模板外移 capability，状态独立 JSON。 |
| `profiles/ifc-mom/scripts/praxis/momlib/git_worktree.py` | Git worktree create/reuse/cleanup/locks | `runtime kernel` | 统一 command runner 和 state ownership；web local config sync 下沉到 stack capability。 |
| `profiles/ifc-mom/scripts/praxis/momlib/workflow_checks.py` | docs/check/change/migration/guard gates | `reusable capability` | 通用 gates 保留；MagicAPI/报表/PDA 触发项拆入 domain capabilities。 |
| `profiles/ifc-mom/scripts/praxis/momlib/process.py` | command runner、RTK fallback、Git capture | `runtime kernel` | 重写为 `src/praxis/process/runner.py`；移除硬编码 `/usr/bin/git` 依赖。 |
| `profiles/ifc-mom/scripts/praxis/momlib/project_actions.py` | status/verify/run/shell 分发 | `runtime kernel` | 合并进 project service；执行命令来自 declarative project facts/check plans。 |
| `profiles/ifc-mom/scripts/praxis/momlib/docs.py` | 需求文档目录、模板、domain index | `reusable capability` | 文档生命周期为 reusable；`ifc-mom` tags/domain rules 拆入 domain capability。 |
| `profiles/ifc-mom/scripts/praxis/momlib/docs_tolaria.py` | Tolaria check/publish/types/views | `domain capability` | 可选 Tolaria capability；未启用返回 `capability_not_enabled`。 |
| `profiles/ifc-mom/scripts/praxis/momlib/etl.py` | ETL/report asset tree and templates | `domain capability` | 拆为 `etl-report` capability。 |
| `profiles/ifc-mom/scripts/praxis/momlib/delivery_policy.py` | delivery commit/file policy | `reusable capability` | 归 delivery capability；migration-specific checks 依赖 migration capability。 |
| `profiles/ifc-mom/scripts/praxis/momlib/finish.py` | delivery status/finish/commit/deliver/cleanup | `runtime kernel` | 交付生命周期由 runtime 执行；策略由 delivery capability 提供。 |
| `profiles/ifc-mom/scripts/praxis/momlib/context.py` | context packet 和 worker rule/skill path selection | `runtime kernel` | context assembly 归 runtime；规则/技能来源改为 resolved profile/capability。 |
| `profiles/ifc-mom/scripts/praxis/momlib/business-domain-rules.json` | MOM 业务聚合关键词 | `domain capability` | 拆入 `manufacturing-rules` 或 MOM domain parameters。 |
| `profiles/ifc-mom/scripts/praxis/frontend_changed.ts` | pnpm-web/pnpm-uniapp changed source classifier | `stack capability` | 归 `pnpm-web`/`pnpm-uniapp`；由 runtime 调用，不放 workspace scripts。 |
| `profiles/ifc-mom/scripts/praxis/backend_run.py` | backend local run helper | `stack capability` | 归 `java-maven` executor/check plan；项目命令参数来自 workspace facts。 |
| `profiles/ifc-mom/scripts/praxis/verify.py` | stack verification dispatcher | `runtime kernel` | verification service 调用 stack capability check plans。 |
| `profiles/ifc-mom/scripts/praxis/praxislib/codegraph_adapter.py` | codegraph allowed subcommands | `reusable capability` | 作为 optional investigation capability；不进入通用 profile 默认必需。 |
| `profiles/ifc-mom/scripts/praxis/praxislib/policy.py` | policy report generation | `reusable capability` | 可保留为 policy-check capability。 |
| `profiles/ifc-mom/scripts/praxis/tests/*` | 旧 profile-local tests | `obsolete` | 不复制；提炼最小 fixture/behavior tests 到新 `tests/`。 |
| `profiles/ifc-mom/.praxis/commands.toml` | 旧 workspace command contract | `reusable capability` | 拆为 CLI metadata/capability command projections；不写 workspace canonical copy。 |
| `profiles/ifc-mom/.praxis/extensions/ifc-mom/extension.toml` | extension loader metadata | `profile composition` | 转为 capability/profile manifests；不保留 ifc-mom 作为通用能力名。 |
| `profiles/ifc-mom/.praxis/extensions/ifc-mom/manifest.toml` | task policies and routing | `profile composition` | 行为拆成 task-policy capability + stack/domain capabilities；profile 只组合。 |
| `profiles/ifc-mom/.praxis/extensions/ifc-mom/project-adapter.toml` | ifc-mom routing, paths, database_policy, project_kinds | `profile composition` | 通用 kind 路由拆入 capabilities；MOM/AOTU 差异进 profile parameters/workspace facts。 |
| `.praxis/core.toml` in real workspaces | portable stages/risk lanes/tool candidates | `runtime kernel` | 提炼为 runtime schema/defaults；不作为 workspace static required file。 |
| `.praxis/project-adapter.toml` in real workspaces | generic adapter loader and extension policy | `runtime kernel` | 装入 package resolver；workspace 不保存 adapter implementation。 |
| `praxis.projects.toml` in real workspaces | project paths/types/branches/verify commands/DB facts | `workspace facts` | 按新计划迁入 `.praxis/workspace.toml`；禁止保存密码和 runtime state。 |
| `praxis.toml` in real workspaces | workspace marker/profile selection | `workspace facts` | 合并进 `.praxis/workspace.toml`，保留 profile id/locale 等最小 facts。 |
| `AGENTS.md` in real workspaces | user/project-facing guidance | `workspace facts` | 可作为用户事实文档保留；不作为 runtime/capability canonical source。 |
| `.praxis/contracts/agents/*.json` | agent handoff schemas | `reusable capability` | schemas 打包为 capability/package resources；workspace 只可保存实例 evidence/state。 |
| `.praxis/methodology.toml` | 方法论/risk/evidence policy | `reusable capability` | 拆入 task-policy/context/verification capability manifests。 |
| `.praxis/profile.toml` | installed profile marker | `profile composition` | 替换为 resolved profile lock/cache，源 manifest 来自 package。 |
| `.praxis/platforms/*` | platform-specific command projections/hooks | `platform adapter` | 由 adapter renderer 生成；workspace 投影只在 `.praxis/generated/<platform>/`。 |
| `.praxis/templates/*` | shared doc/rule/skill templates | `reusable capability` | canonical templates 留在 installed package capability resources。 |
| `.praxis/rules/global/*` | shared workflow rules | `reusable capability` | 拆成 workspace/task/context/verification/delivery/documentation capabilities。 |
| `.praxis/extensions/ifc-mom/rules/projects/backend/*` | Java/Maven backend rules | `stack capability` | `java-maven` capability；migration-specific 内容依赖 migration/domain capability。 |
| `.praxis/extensions/ifc-mom/rules/projects/web/*` | Vue/pnpm web rules | `stack capability` | `pnpm-web` capability。 |
| `.praxis/extensions/ifc-mom/rules/projects/pda/*` | UniApp/PDA rules | `stack capability` | 技术栈部分归 `pnpm-uniapp`，PDA 产品约束归 domain capability。 |
| `.praxis/extensions/ifc-mom/rules/projects/big-screen/*` | dashboard/big screen rules | `stack capability` | `npm-dashboard` + `big-screen` domain split。 |
| `.praxis/extensions/ifc-mom/skills/global/mom-agent-workflow/*` | role workflow references | `reusable capability` | 拆为 task-policy/context/delivery capabilities；去除 mom-* 命名。 |
| `.praxis/extensions/ifc-mom/skills/global/mom-database-investigation/*` | DB investigation procedure | `domain capability` | `database-investigation` capability。 |
| `.praxis/extensions/ifc-mom/skills/global/mom-migration-script-generation/*` | Flyway/migration generation guidance | `domain capability` | `migration-checks`/migration domain capability。 |
| `.praxis/extensions/ifc-mom/skills/global/mom-lightweight-etl-report/*` | ETL/report/MagicAPI assets | `domain capability` | `etl-report` + `magicapi` capabilities。 |
| `.praxis/extensions/ifc-mom/skills/global/mom-tolaria-vault/*` | Tolaria vault rules | `domain capability` | optional `tolaria` capability。 |
| `.praxis/extensions/ifc-mom/skills/projects/backend/java-backend-development/*` | Java backend development skill | `stack capability` | `java-maven` capability。 |
| `.praxis/extensions/ifc-mom/skills/projects/backend/magic-api-development/*` | MagicAPI business integration | `domain capability` | `magicapi` capability。 |
| `.praxis/extensions/ifc-mom/skills/projects/pda/pda-development/*` | PDA/PAD behavior | `domain capability` | `pda-pad` capability, depending on `pnpm-uniapp` stack where needed。 |
| `.praxis/extensions/ifc-mom/skills/projects/big-screen/big-screen-development/*` | large screen dashboard behavior | `domain capability` | `big-screen` capability。 |
| `.praxis/extensions/ifc-mom/skills/projects/web/*form*` | bill/form low-code patterns | `domain capability` | Web stack + product/domain capability split。 |
| `.praxis/out/readiness/*` | old readiness runtime output embedded in profile tree | `workspace runtime state` | Never package; new state/evidence under `.praxis/state` or cache. |
| `.praxis/out/context/*` | context packet runtime output embedded in profile tree | `generated projection/cache` | Rebuildable cache only; not profile source. |
| `.praxis/out/handoffs/*` | old handoff runtime output embedded in profile tree | `workspace runtime state` | Instance state only; not profile/package asset. |
| `.praxis/out/locks/*` | runtime locks embedded in profile tree | `workspace runtime state` | Runtime locks/state only; not package. |
| `.praxis/out/verdicts/*` | quality/delivery verdict runtime output embedded in profile tree | `workspace runtime state` | Instance evidence state only. |
| `.praxis/out/delivery-precheck/*` | delivery precheck generated output embedded in profile tree | `workspace runtime state` | Instance evidence state only. |
| `.praxis/out/profile.json` | profile report generated by old `task system -- praxis-profile` | `generated projection/cache` | Recompute from resolved profile; not packaged. |
| `.praxis/out/template-report.json` | template check generated output | `generated projection/cache` | Recompute under cache/report location. |
| `.praxis/out/command-audit.json` | command audit generated output | `generated projection/cache` | Recompute; audit docs are canonical for rebuild. |
| `.praxis/out/tolaria/tolaria-check.json` | Tolaria check report | `workspace runtime state` | Workspace evidence/report only when Tolaria enabled. |
| `.praxis/requirements/*` | process requirement records | `workspace runtime state` | New `.praxis/state/requirements/*.json`。 |
| `.praxis/tasks/*` | quick task records | `workspace runtime state` | New `.praxis/state/tasks/*.json`。 |
| `.worktrees/*` | Git worktree directories | `workspace runtime state` | Managed by runtime with ownership JSON under `.praxis/state/worktrees/*.json`。 |
| `.praxis/profile-sync.lock` | old auto-sync lock | `obsolete` | Removed with sync model；new locks only for runtime operations。 |
| `workspaces.local.json` | plugin checkout local registry | `obsolete` | Do not migrate；new CLI can inspect explicit workspace path only。 |
| `templates/AGENTS.md.tpl` | old bootstrap guidance template | `reusable capability` | If needed, generate projection from package; not required runtime source. |
| `templates/praxis.projects.toml.tpl` | old root facts starter | `workspace facts` | Replaced by `.praxis/workspace.toml` initializer. |
| `templates/core.toml.tpl` | old copied runtime config template | `obsolete` | Runtime defaults live in package, not workspace. |
| `templates/project-adapter.toml.tpl` | old copied adapter template | `obsolete` | Adapter/resolver lives in package. |
| `templates/turn.schema.json` | turn schema | `reusable capability` | Package resource; not workspace canonical. |
| `templates/delivery.schema.json` | delivery schema | `reusable capability` | Package resource with AOTU stricter fields considered. |
| `.codex-plugin/plugin.json` | Codex plugin metadata | `platform adapter` | Generated from canonical adapter manifest。 |
| `.claude-plugin/plugin.json` | Claude Code plugin metadata | `platform adapter` | Generated from canonical adapter manifest。 |
| `.claude-plugin/marketplace.json` | Claude marketplace metadata | `platform adapter` | Generated projection; no business logic。 |
| `package.json` | OMP extension registration | `platform adapter` | Thin adapter package metadata only。 |
| `commands/praxis-*.toml` | platform command prompts | `platform adapter` | Generated or packaged thin prompts that call `praxis ... --json`。 |
| `commands/praxis-*.md` | generated Markdown command projections | `platform adapter` | Generated output; check drift。 |
| `commands/ponytail*.toml` | Ponytail command prompts | `platform adapter` | Optional Ponytail adapter/capability。 |
| `hooks/hooks.json` | Claude/Codex lifecycle hooks | `platform adapter` | Thin launcher only；must not sync profile/runtime。 |
| `hooks/ponytail-*.js` | Ponytail hook runtime | `platform adapter` | Optional adapter boundary；not core。 |
| `adapters/omp/praxis-auto-sync.mjs` | OMP session-start auto-sync extension | `platform adapter` | Rewrite to spawn stable Praxis CLI through controlled environment。 |
| `adapters/omp/ponytail-extension.mjs` | OMP Ponytail command/status extension | `platform adapter` | Keep optional; core independent。 |
| `pi-extension/index.js` | old Pi/OMP runtime extension | `platform adapter` | Rebuild thinly or discard if superseded by OMP adapter。 |
| `vendor/ponytail/*` | vendored Ponytail upstream assets | `platform adapter` | Optional pinned vendor; never copied into workspace。 |
| `vendor/ponytail.lock.json` | Ponytail hash/license/allowlist | `platform adapter` | Check fail-closed; not core。 |
| `skills/rtk/SKILL.md` | RTK usage guidance | `reusable capability` | Optional command-runner diagnostics; runtime semantics unchanged without RTK。 |
| `skills/praxis-workflow/*` | old user workflow skill | `reusable capability` | Split into smaller capability rules; do not keep monolithic profile skill。 |
| `skills/ponytail*/*` | Ponytail skills | `platform adapter` | Optional Ponytail boundary。 |
| MOM `.praxis/contracts/agents/delivery.schema.json` | delivery agent contract, weaker commit allowlist | `reusable capability` | Use as lower-bound evidence only。 |
| AOTU `.praxis/contracts/agents/delivery.schema.json` | stricter delivery agent contract | `reusable capability` | Prefer stricter confirmation fields in shared delivery capability。 |

## 拒绝迁移清单

| 旧内容 | 原因 | 新归属 |
|---|---|---|
| 整个 `profiles/ifc-mom` 目录树 | 混合 runtime、rules、skills、profile、generated output 和 project adapter | `obsolete` |
| `scripts/praxis/praxis_core` copied shared core | runtime 副本，不允许进入 workspace | `obsolete` |
| 旧 `.praxis/out/*` profile source 输出 | runtime/generated state 混入 package source | `workspace runtime state` |
| 旧 root `praxis.projects.toml` 布局 | 新计划要求 `.praxis/workspace.toml` 为项目事实注册表 | `workspace facts` |
| `.praxis/core.toml` 和 `.praxis/project-adapter.toml` workspace 副本 | runtime/adapter 不应由 workspace 持有 | `obsolete` |
| `profile-sync.lock` 和 auto-sync repair model | 同步模型本身被废弃 | `obsolete` |
| `workspaces.local.json` | 本机插件 registry，不是可分发事实 | `obsolete` |
| 旧测试快照目录 | 不证明新架构边界，且会复制旧实现 | `obsolete` |
| MOM/AOTU 本机路径、DB 名称、prodBranches 进入通用 profile | 业务事实污染通用 profile/kernel | `workspace facts` |
| Ponytail vendored assets 进入 core/workspace | 可选平台增强，不是 Praxis 核心能力 | `platform adapter` |
