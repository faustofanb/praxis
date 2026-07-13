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
- 每完成一个可独立确认的工作流步骤，回复末尾必须给出“推荐下一步”和 2-4 个可选工作流动作，标明推荐项；涉及提交、交付、清理、远程操作、生产数据或扩大范围时，等待用户选择后继续推进。
- 快速需求默认由主对话完成：先调查、后改代码，只做语法/解析检查；不默认使用 TDD、全局校验、预检、子代理或阶段文档。


## Every Turn Contract

- Treat each user message as a new turn.
- Reconcile the latest user request, active task state, workspace state and loaded Praxis sources.
- Before creating anything, search same-name and same-aggregate active requirements. Continuous work reuses the selected requirement directory and worktree; independent delivery or acceptance creates a new one.
- For code-bearing business work, create or restore the project worktree before editing business code. Create or restore a requirement directory only when documentation output must be retained.
- For docs-only business work with retained output, create or restore the requirement directory before drafting.
- Answer-only, read-only investigation and pure workflow maintenance may waive the business worktree, but the final answer must state the waiver reason and residual risk.
- Delivery or closeout work must identify confirmed commits, excluded commits, candidate audit evidence and required confirmations before preparing destructive or remote commands.
