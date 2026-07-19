---
name: mom-praxis-command-contract
description: '用于维护 IFC MOM adapter 的 Praxis 命令契约一致性。适用于修改 Taskfile.yml、.praxis/commands.toml、.praxis/manifest.toml、scripts/praxis/task.py、AGENTS.md、Praxis 规则文档或任何 task/命令入口说明，防止文档命令与脚本命令漂移。'
user-invocable: true
---

# MOM Praxis Command Contract

## 适用场景

- 修改 `Taskfile.yml`、`.praxis/commands.toml`、`.praxis/manifest.toml`、`.praxis/core.toml`、`.praxis/project-adapter.toml`、`scripts/praxis/task.py`。
- 修改 `AGENTS.md`、`.praxis/extensions/ifc-mom/rules/global/00-工作流精简索引.md`、`.praxis/extensions/ifc-mom/rules/global/praxis-workflow/`、`.praxis/templates/` 中的命令示例或模板。
- 新增、重命名、删除 `task req/project/context/etl/gate/delivery/system` 子命令。
- 修复 “文档写的是一个命令，脚本实际是另一个命令” 的漂移。

## 核心约束

- `task ...` 是对话和文档中的首选入口；底层 `uv run scripts/praxis/task.py ...` 只作为实现细节或测试入口。
- 带子命令分发的 go-task 写法必须使用 `--` 分隔，例如 `task project -- status <project>`。
- `.praxis/commands.toml` 是命令定义台账；`.praxis/manifest.toml` 只能引用已登记命令；`.praxis/core.toml` 承载可共享阶段、风险通道和工具候选；`.praxis/project-adapter.toml` 承载项目特异路径、项目 kind 和规则入口；`rules`/`skills` 只能引用真实存在的文件或目录。
- 改命令时必须同步：脚本解析、Taskfile 入口、commands 台账、manifest 引用、AGENTS/规则示例、相关测试。
- 不允许只改文档不改脚本，也不允许只改脚本不改命令台账。

## 执行流程

1. 先定位命令真实实现：`Taskfile.yml`、`scripts/praxis/task.py` 和对应 `momlib/*` parser。
2. 再检查命令台账：`.praxis/commands.toml`。
3. 再检查共享平台与项目适配：`.praxis/core.toml`、`.praxis/project-adapter.toml`。
4. 再检查机器路由：`.praxis/manifest.toml` 的 `commands`、`rules`、`skills`、`gates`。
5. 最后同步人类入口：`AGENTS.md`、`.praxis/extensions/ifc-mom/rules/global/00-工作流精简索引.md`、相关 `praxis-workflow/*.md`。
6. 修改后运行命令契约和工作流检查。

## 必跑验证

```bash
task system -- command-audit
task system -- check
task system -- praxis-profile
task system -- template-check
uv run scripts/praxis/tests/test_praxis.py
uv run scripts/praxis/tests/test_workflow.py
uv run scripts/praxis/tests/test_praxis_profile.py
uv run scripts/praxis/tests/test_praxis_templates.py
```

## 完成检查

- 新命令在脚本、Taskfile、commands 台账、manifest、文档示例中一致。
- go-task 分发命令示例带 `--`。
- manifest 没有引用不存在的 command id、rule path 或 skill path。
- Praxis profile 没有缺失命令、路径、项目 kind 或工具候选官方来源。
- Template report 没有缺失 rule 标题、Skill frontmatter 或模板占位符。
- 输出说明列出同步过的入口文件和验证结果。
