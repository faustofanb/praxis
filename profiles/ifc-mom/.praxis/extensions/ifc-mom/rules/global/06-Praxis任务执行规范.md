# Praxis 任务执行规范

## 定位

本文件只做 Praxis 工作流总索引。具体执行规则已拆分到 `.praxis/extensions/ifc-mom/rules/global/praxis-workflow/`，避免单文件过大导致实际执行时漏读、漏遵守。

默认先读：

- `.praxis/extensions/ifc-mom/rules/global/00-工作流精简索引.md`
- 本文件
- 与任务类型匹配的拆分规则文件

## 拆分索引

- `praxis-workflow/01-入口与自动化.md`：标准入口、项目短名、脚本职责、自动化边界。
- `praxis-workflow/02-主对话与Subagent.md`：主对话职责、subagent 派发、上下文预算、通信协议、写锁。
- `praxis-workflow/03-调查门禁.md`：真实数据库调查、数据口径、迁移中间产物前置门禁。
- `praxis-workflow/04-需求文档与Worktree.md`：需求文档初始化、阶段迭代、README 索引、worktree 和分支边界。
- `praxis-workflow/05-大任务拆分与验证.md`：大任务拆分、验证等级、各项目验证命令策略。
- `praxis-workflow/06-交付收口.md`：finish/deliver/cleanup、feature 分支、迁移收尾、交付说明。
- `praxis-workflow/07-过程改进与维护.md`：`todo.md` 使用、规则维护、脚本变更同步。

## 快速路由

- 不确定先读哪一份：读 `.praxis/extensions/ifc-mom/rules/global/00-工作流精简索引.md`。
- 要查命令入口：读 `praxis-workflow/01-入口与自动化.md`。
- 要派发或管理 worker：读 `praxis-workflow/02-主对话与Subagent.md`。
- 涉及真实数据、SQL、迁移、字段口径：读 `praxis-workflow/03-调查门禁.md`。
- 新需求、文档迭代、worktree：读 `praxis-workflow/04-需求文档与Worktree.md`。
- 验证选 L0/L1/L2：读 `praxis-workflow/05-大任务拆分与验证.md`。
- 交付、feature、清理：读 `praxis-workflow/06-交付收口.md`。
- 用户指出流程缺口：读 `praxis-workflow/07-过程改进与维护.md`。

## 权威关系

- `AGENTS.md`：工作区入口、任务路由、少量硬门禁。
- `.praxis/extensions/ifc-mom/rules/global/00-工作流精简索引.md`：默认执行清单和细粒度引用。
- `.praxis/extensions/ifc-mom/rules/global/praxis-workflow/*.md`：Praxis 执行细则。
- `.praxis/extensions/ifc-mom/rules/projects/`：项目专属规则，优先于全局通用规则。
- `.praxis/extensions/ifc-mom/skills/`：项目或任务技能，按任务类型使用。

当规则冲突时，优先级为：用户明确要求 > 项目专属规则 > Praxis 拆分细则 > 精简索引 > AGENTS 导航。
