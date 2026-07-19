---
description: 创建无需求文档的 L0 快速任务工作树与可恢复状态
---
<!-- Generated from commands/praxis-quick.toml by scripts/praxis_build_adapters.py; do not edit. -->

使用中文快速落地一个低风险代码任务。运行 `task project -- quick <project> <简短任务名>`，只创建隔离 worktree 与 `.praxis/tasks/<id>.toml` 状态，不创建需求文档。仅适用于不涉及数据库、迁移、权限、报表或共享契约的 L0 变更；命中这些边界时升级为 `task project -- start <project> <需求名> <用户原始需求>`。在 worktree 中完成最小修改后运行 `task project -- quick-check <project> <简短任务名>`；通过变更边界后执行输出的语法/解析或聚焦契约检查，并报告状态文件、验证证据与剩余风险。
