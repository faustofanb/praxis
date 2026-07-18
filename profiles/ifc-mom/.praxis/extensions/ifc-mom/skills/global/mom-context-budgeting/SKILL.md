---
name: mom-context-budgeting
description: '用于 IFC MOM 主对话上下文预算、本地化 context-optimization、何时派发 worker、worker 输出上限、长日志摘要、证据落盘、需求目录恢复和上下文退化防护。适用于长任务、多项目任务、源码调查、测试日志、构建日志、数据库调查和交付收口。'
user-invocable: true
---

# MOM Context Budgeting

## 适用场景

- 任务跨后端/Web/PDA/大屏/报表多个项目。
- 需要读取大量源码、规则、日志、SQL、diff 或测试输出。
- 对话已长、上下文接近上限、恢复旧需求或交接 worker。
- 需要决定主对话直接做，还是派 Requirement/Execution/Quality/Delivery Agent。

## 核心约束

- Tester/Quality 只能作为选项；上下文或风险阈值只能触发建议，得到用户明确许可后才能派发。
- 主对话先读控制面：`AGENTS.md`、需求 README、最新阶段文件、`task context` 输出。
- 主对话不批量加载项目规则、源码、长日志、全量 diff；能由 worker 压缩的交给 worker。
- worker 输出必须结构化，给结论、证据路径、关键摘录、验证结果和剩余风险，不粘贴长日志。
- 长日志只保留失败命令、退出码、首个根因段、相关文件行号和复现/验证路径。
- 阶段结论必须落盘到需求目录，不能只留在聊天上下文。

## 派发阈值

- 低风险快车道：单项目、3 个文件以内、不涉及 SQL/迁移/真实数据/公共组件/权限/异步/定时任务时，主对话可记录 `subagent: waived-small-change` 并直接推进；默认只读 `task context -- --brief` 与变更相关样例。
- 源码调查超过 3 个文件或跨模块：可建议 Execution/Requirement Agent；未获用户并行授权时由主对话继续。
- 测试/构建日志超过 120 行：优先用工具截取首个根因；用户已授权并行时可由 worker 摘要。
- diff 超过 300 行或跨两个项目：建议 Quality Agent 独立复核，等待用户许可。
- 涉及数据库口径、迁移、报表：使用数据库调查专门流程；只有用户授权并行时才派发 worker。
- 交付收口、cleanup、feature 分支：派 Delivery Agent 或按 delivery skill 复核；常规收口优先使用 `task gate -- ready` 聚合检查，专项排查才单跑 `guard/change-check/migration-check`。

## Worker 输出上限

- `changed_files`：只列实际相关文件。
- `evidence`：每项最多 3 条关键路径或查询。
- `verification`：命令、退出码、关键摘要；失败日志摘录不超过 40 行。
- `risks`：只列会影响继续推进或交付的风险。
- `stage_updates`：说明已写文件或建议写入位置。

## 落盘规则

- 需求理解/调查：`01-需求分析拆解/`。
- 实施计划：`02-任务规划/`。
- 实现、验证、暂停、收口：`03-开发进度/`。
- SQL、MagicAPI、前端说明、关联调查：`04-产出物/`。

## 完成检查

- 主对话没有携带不必要的长源码、长日志或全量规则。
- 关键证据可从需求目录、代码审查结论、readiness 或命令输出恢复。
- worker 回报足够 Quality Agent 复核。
- 最终交付说明包含验证结果和未验证原因。
