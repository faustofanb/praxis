---
name: praxis-workflow
description: Use when working in a Praxis workspace, changing Praxis workflow behavior, initializing or checking a Praxis workspace, deciding whether a task needs a requirement directory or worktree, using Praxis helper scripts or templates, or explaining Praxis project configuration boundaries.
---

# Praxis Workflow

## Purpose

Use this skill as the shared Codex entry discipline for Praxis workspaces. It packages reusable workflow rules, thin templates and helper scripts while leaving project-specific paths, branch names, verification commands and domain rules in the current workspace.

## Language Policy

默认使用中文与用户对话。需求文档、分析、规划、进度和交付说明必须使用中文；代码、命令、路径、API 名称、日志片段和用户提供的原始引用可保留原文。用户明确要求其他语言时，以用户要求为准。

## 快速需求路径

用户要求快速落地时，默认走：项目/业务域定位 -> 恢复同名需求或新建独立需求与工作树 -> 必要的源码或数据调查 -> 修改代码 -> 语法/解析检查 -> 仅回写必须留档的文件。

- 不默认使用 TDD、完整测试、全局校验、预检、子代理或详细阶段文档。
- 代码修改仍必须在项目工作树中完成；先恢复同一需求已有工作树，确实是独立工作才新建。
- 只有用户输入、调查结论、SQL 草案、实施说明、进度等需要作为交付物保留时，才创建或复用需求目录；不要为纯代码小改机械建目录。
- 新建前按需求名查找未完成需求；业务聚合只用于检索候选，不能触发自动复用。只有同名需求可自动恢复，不同需求名默认新建独立目录和工作树。
- 语法/解析失败必须修复；其他验证仅在用户要求或变更风险确实需要时执行，并说明原因。

## 受控开发边界

- 工作流默认只负责源码调查、编码和代码级检查；不以页面可见效果代替可重复的代码证据。
- 禁止使用浏览器、桌面控制或电脑控制工具执行测试，也不自动访问管理页面、读取登录态、操作外部系统或发布结果。
- 默认代码级检查仅限变更范围检查、语法/解析、lint、类型检查、编译和聚焦的单元/契约测试；完整测试、独立 Quality 复核、预检和收口门禁不自动展开。
- 浏览器/UI/人工运行时测试、外部联调、完整回归或额外复核只能作为选项报告，得到用户明确许可后才能执行。


## Oh My Pi / Codex Runtime Routing

Default to a Codex-only budget in Oh My Pi unless the user explicitly names
another available subscription for the current task. Do not design plans that
depend on Claude, Gemini, Opencode, remote paid reviewers, or other non-Codex
models being available.

Use the cheapest reliable lane for each step:

- Tool-only: schema lookup, references, file search, status, validation and
  command output. Do not ask a model to infer facts that `dbx`, LSP, Code Graph,
  grep/glob/read or `task ...` can provide.
- Main Codex: requirement truth, routing, risk decisions, write locks, user
  confirmations, integration and final answer.
- Read-only worker / explorer: broad source discovery, same-domain examples,
  config inventory and long-log root-cause extraction.
- Execution worker: scoped edits with explicit write locks, known files and a
  concrete verification command.
- Tester / Quality worker: behavior tests or independent review only when the
  risk justifies the extra context and coordination.

Waive worker dispatch for answer-only tasks, deterministic maintenance, or
small single-project changes touching at most three files without SQL,
migration, permission, async, shared-module, production-data or delivery risk.
When waived, record `subagent: waived-small-change`, say why, and keep the main
conversation tool-first.

快速路径默认由主对话完成，不派发 worker/subagent。只有用户明确要求并行、
或主对话无法可靠完成的独立高风险工作，才按既有边界派发。

## Step Handoff

每完成一个可独立确认的工作流步骤，回复末尾必须给出“推荐下一步”和 2-4 个可选工作流动作，标明推荐项；若下一步涉及提交、交付、清理、远程操作、生产数据或扩大范围，必须等待用户选择后继续推进。

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
9. Load extension manifests and rules only when the task matches that extension.

Treat this plugin as shared behavior, not as the source of project facts.

## Project Root And CodeGraph

Do not infer the target repository from the current shell directory. A Praxis workspace can aggregate many backend, frontend and uni-app repositories.

Resolve the target project from `praxis.projects.toml` first. Use the selected project's `path` as the candidate repository, then locate that repository's actual root. Check CodeGraph only at that project root. If an existing Praxis graph is stale, `task system -- code-graph check` queues one asynchronous refresh while the current task falls back to source search. Never auto-initialize a missing graph.

## Reference Map

Read only the reference needed for the task:

- Startup gate decisions: `references/startup-gate.md`.
- Requirement worktree rules: `references/worktree.md`.
- Command examples and drift checks: `references/command-contract.md`.
- Project branch/path ownership: `references/project-config-boundary.md`.
- Verification, resume and final response evidence: `references/verification-closeout.md`.
- Delivery candidate auditing and confirmations: `references/delivery-contract.md`.

## Helper Scripts

Use scripts from this plugin only for generic Praxis workspace operations:

```bash
python scripts/praxis_check_workspace.py <workspace>
python scripts/praxis_check_workspace.py <workspace> --json
python scripts/praxis_doctor.py <workspace>
python scripts/praxis_init_workspace.py <workspace> --name "Workspace Name"
python scripts/praxis_sync_profile.py <workspace> ifc-mom --force
python scripts/praxis_sync_workspaces.py ifc-mom --force
```

Prefer the workspace's own `task ...` commands after a workspace already has its Praxis entry files. If a workspace imports RTK instructions, prefix shell commands with `rtk`.

## Packaged Profiles

Profiles under `profiles/` carry reusable project-family assets such as extension rules, skills, command registries and automation scripts. Use them to reduce per-workspace duplication while keeping project facts local:

- `ifc-mom`: IFC MOM workflow rules, MOM/AOTU skills, command registry, delivery automation, ETL/report, backend, web, PDA and big-screen guidance.

Profile workspace registries such as `profiles/ifc-mom/workspaces.json` are local orchestration lists for syncing shared profile assets to multiple workspaces. They do not replace workspace-local `praxis.projects.toml`.

Profile sync must not overwrite project registries, branch names, verification commands or requirement records unless the user explicitly asks for that local project change.

## Boundary

Do not treat this plugin as the source for project-specific facts. Read local configuration for project names, labels, descriptions, aliases, paths, `defaultBranch`, `upstreamBranch`, worktree root, verification commands, installed extensions and domain rules.

Do not ask the user to provide `local` as a branch name when the workspace already has `defaultBranch` in `praxis.projects.toml`. A manual branch argument is only appropriate for an explicit diagnostic or override path.
