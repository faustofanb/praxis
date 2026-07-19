# AGENTS.md

This is the thin Agent entrypoint for {{ workspace_name }}.

## Load Order

1. Read `praxis.toml`.
2. Read `praxis.projects.toml`; use project `label`, `description`, `aliases`, `path` and `kind` to route the task.
3. Read `.praxis/core.toml`.
4. Read `.praxis/project-adapter.toml`.
5. Read `.praxis/contracts/agents/turn.schema.json`.
6. Read `.praxis/contracts/agents/delivery.schema.json` before delivery or closeout work.
7. Read installed extension manifests only when a task matches that extension.

## Operating Rules

- Use `task ...` as the human-facing command surface when this workspace provides it.
- 默认使用中文与用户对话；用户明确要求其他语言时除外。
- 需求文档必须使用中文；代码、命令、路径、API 名称和原始引用可保留原文。
- Keep Praxis core project-neutral.
- Keep domain or stack-specific rules in extensions.
- Keep generated reports under `.praxis/out/`.
- Use project configuration for branch names and project paths.
- Do not infer the target repository from the current shell directory. Resolve the project from `praxis.projects.toml`, then check `.codegraph/` only at that project's actual repository root.
- If the selected project has a usable `.codegraph/`, CodeGraph may accelerate source understanding; otherwise use normal local search. Do not rebuild an index for a quick task.
- 快速需求默认由主对话完成：低风险 L0 代码任务先运行 `task project -- quick <project> <简短任务名>` 创建隔离 worktree 与 `.praxis/tasks/<id>.toml`；修改后运行 `task project -- quick-check <project> <简短任务名>`，再执行 manifest 输出的语法/解析或聚焦检查。不默认使用 TDD、全局校验、预检、子代理或阶段文档。数据库、迁移、权限、报表、共享契约或跨项目变更必须升级到 formal 模式。


## Every Turn Contract

- Treat each user message as a new turn.
- Reconcile the latest user request, active task state, workspace state and loaded Praxis sources.
- Before creating anything, search exact-name active requirements. Same-aggregate results are retrieval candidates only; a different requirement name creates an independent directory and worktree.
- For code-bearing business work, create or restore the project worktree before editing business code. Use `project quick` for eligible L0 work without retained requirement docs; use `project start` when requirement documents or L1/L2 lifecycle evidence must be retained.
- For docs-only business work with retained output, create or restore the requirement directory before drafting.
- Answer-only, read-only investigation and pure workflow maintenance may waive the business worktree, but the final answer must state the waiver reason and residual risk.
- Delivery or closeout work must identify confirmed commits, excluded commits, candidate audit evidence and required confirmations before preparing destructive or remote commands.
