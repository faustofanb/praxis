---
name: praxis-workflow
description: Use when working in a Praxis workspace, changing Praxis workflow behavior, initializing or checking a Praxis workspace, deciding whether a task needs a requirement directory or worktree, using Praxis helper scripts or templates, or explaining Praxis project configuration boundaries.
---

# Praxis Workflow

## Purpose

Use this skill as the shared, agent-neutral entry discipline for Praxis workspaces. It packages reusable workflow rules, thin templates and helper scripts while leaving project-specific paths, branch names, verification commands and domain rules in the current workspace.

## Language Policy

默认使用中文与用户对话。需求文档、分析、规划、进度和交付说明必须使用中文；代码、命令、路径、API 名称、日志片段和用户提供的原始引用可保留原文。用户明确要求其他语言时，以用户要求为准。

## 快速需求路径

用户要求快速落地且变更属于 L0 时，默认走：项目定位 -> `task project -- quick <project> <简短任务名>` -> 隔离 worktree -> 必要调查 -> 最小代码修改 -> 语法/解析检查 -> 回写 `.praxis/tasks/<id>.toml` 状态。

- L0 不默认创建需求目录，也不默认使用 TDD、完整测试、全局校验、预检、子代理或阶段文档。
- 数据库、迁移、权限、报表、共享契约或跨项目变更不属于 L0；改走 `task project -- start <project> <需求名> <用户原始需求>`。
- 同一项目/任务名的并发创建由 workspace lock 串行化；现存 worktree 必须唯一，出现多个候选时停止，不猜测。
- 快速任务仍必须在隔离 worktree 中完成，并保留 `.praxis/tasks/<id>.toml`，使模式、项目、策略、worktree 与状态可恢复。
- 修改后运行 `task project -- quick-check <project> <简短任务名>`；高风险路径会 fail closed，边界通过后按 manifest 输出执行语法/解析或最多 1–2 个聚焦契约检查。

## 受控开发边界

- 工作流默认只负责源码调查、编码和代码级检查；不以页面可见效果代替可重复的代码证据。
- 禁止使用浏览器、桌面控制或电脑控制工具执行测试，也不自动访问管理页面、读取登录态、操作外部系统或发布结果。
- 默认代码级检查仅限变更范围检查、语法/解析、lint、类型检查、编译和聚焦的单元/契约测试；完整测试、独立 Quality 复核、预检和收口门禁不自动展开。
- 浏览器/UI/人工运行时测试、外部联调、完整回归或额外复核只能作为选项报告，得到用户明确许可后才能执行。


## Load Local Sources First

At the start of an acting turn inside a Praxis workspace:

1. Read the workspace `AGENTS.md`.
2. Read `praxis.toml`.
3. Read `praxis.projects.toml`; use each project's `label`, `description`, `aliases`, `path` and `kind` to route the task before reading source.
4. Read `.praxis/core.toml`.
5. Read `.praxis/project-adapter.toml`.
6. Read `.praxis/contracts/agents/turn.schema.json` when present.
7. Read `.praxis/contracts/agents/delivery.schema.json` when doing delivery or closeout work.
8. Read `.praxis/rules/praxis-workflow.md` when present.
9. Read each installed extension's `extension.toml` and matching `manifest.toml` only when the task matches that extension.
10. Route matching IFC MOM/AOTU tasks through manifest-listed global/backend/web/pda/big-screen rules and skills; do not preload unrelated profile assets.

Treat this plugin as shared behavior, not as the source of project facts.

## Project Root And CodeGraph

Do not infer the target repository from the current shell directory. A Praxis workspace can aggregate many backend, frontend and uni-app repositories.

Resolve the target project from `praxis.projects.toml` first. Use the selected project's `path` as the candidate repository, then locate that repository's actual root. Use an existing `.codegraph/` index only at that project root; otherwise fall back to source search. Never auto-initialize a missing graph.

## Reference Map

Read only the reference needed for the task:

- Startup gate decisions: `references/startup-gate.md`.
- Requirement worktree rules: `references/worktree.md`.
- Command examples and drift checks: `references/command-contract.md`.
- Project branch/path ownership: `references/project-config-boundary.md`.
- Verification, resume and final response evidence: `references/verification-closeout.md`.
- Delivery candidate auditing and confirmations: `references/delivery-contract.md`.

## Session Integration

The installed plugin's session-start hook automatically detects an existing packaged profile, compares managed files, and synchronizes drift under a local lock. Do not ask the user to run profile sync on every task. Manual sync is only for first-time initialization, explicit repair, bulk registry distribution, or a workspace with auto-sync disabled in `.praxis/plugin-sync.toml`. The hook never owns workspace-local project paths, branches, databases, requirements or business documents.

## Helper Scripts

Use scripts from this plugin only for generic Praxis workspace operations:

```bash
python scripts/praxis_check_workspace.py <workspace>
python scripts/praxis_check_workspace.py <workspace> --json
python scripts/praxis_init_workspace.py <workspace> --name "Workspace Name"
python scripts/praxis_sync_profile.py <workspace> ifc-mom --force
python scripts/praxis_sync_workspaces.py ifc-mom --force
```

Prefer the workspace's own `task ...` commands after a workspace already has its Praxis entry files. If RTK is available, use it for shell commands; if not, run the underlying command and report `RTK optimization unavailable` in delivery.

## Packaged Profiles

Profiles under `profiles/` carry reusable project-family assets such as extension rules, skills, command registries and automation scripts. Use them to reduce per-workspace duplication while keeping project facts local:

- `ifc-mom`: IFC MOM workflow rules, MOM/AOTU skills, command registry, delivery automation, ETL/report, backend, web, PDA and big-screen guidance.

Workspace registries such as root `workspaces.local.json` are local orchestration lists for syncing shared profile assets to multiple workspaces. They do not replace workspace-local `praxis.projects.toml` and are not part of the portable package.

Profile sync must not overwrite project registries, branch names, verification commands or requirement records unless the user explicitly asks for that local project change.

## Boundary

Do not treat this plugin as the source for project-specific facts. Read local configuration for project names, labels, descriptions, aliases, paths, `defaultBranch`, `upstreamBranch`, worktree root, verification commands, installed extensions and domain rules.

Do not ask the user to provide `local` as a branch name when the workspace already has `defaultBranch` in `praxis.projects.toml`. A manual branch argument is only appropriate for an explicit diagnostic or override path.
