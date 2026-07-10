# AGENTS.md

This is the thin Agent entrypoint for {{ workspace_name }}.

## Load Order

1. Read `praxis.toml`.
2. Read `praxis.projects.toml`.
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
- 每完成一个可独立确认的工作流步骤，回复末尾必须给出“推荐下一步”和 2-4 个可选工作流动作，标明推荐项；涉及提交、交付、清理、远程操作、生产数据或扩大范围时，等待用户选择后继续推进。
- Oh My Pi/Codex 默认按单一 Codex 订阅调度：先用工具取事实，Main Codex 只做路由、风险、锁和最终集成；只读 worker 负责候选定位和长日志摘要；Execution worker 只处理有明确写锁和验证命令的实现；Tester/Quality 只在测试或独立复核确有价值时使用。无 SQL/迁移/权限/异步/共享模块/生产数据风险且 3 个文件以内的小改可记录 `subagent: waived-small-change` 后由 Main 直接处理。

## Every Turn Contract

- Treat each user message as a new turn.
- Reconcile the latest user request, active task state, workspace state and loaded Praxis sources.
- For code-bearing business work, create or restore the requirement directory and project worktree before editing business code.
- For docs-only business work, create or restore the requirement directory before drafting implementation detail.
- Answer-only, read-only investigation and pure workflow maintenance may waive the business worktree, but the final answer must state the waiver reason and residual risk.
- Delivery or closeout work must identify confirmed commits, excluded commits, candidate audit evidence and required confirmations before preparing destructive or remote commands.
