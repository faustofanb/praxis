---
name: praxis-system-development
description: 将系统开发任务路由到最小的已安装方法技能，适用于设计、审查、上下文、检索、调试和测试。
---

# Praxis 系统开发路由

## 一、技能用途

根据工作流节点和任务上下文生成可审计的 Skill 路由计划，只加载真正匹配的方法技能。

## 二、适用业务域

适用于所有已登记业务系统的工程任务。

## 三、适用场景

- 设计不确定：头脑风暴
- 正确性或可维护性审查：代码质量审查
- 上下文丢失或冲突：上下文退化检测
- 预算或指令过多：上下文优化
- 仓库定位：文件检索
- 缺少能力：技能发现
- 实现范围控制：Karpathy 开发准则
- 缺陷或失败测试：系统化调试
- 功能、缺陷修复、重构和行为变更：默认测试驱动开发
- TDD GREEN 后：最小受影响模块编译
- 高风险共享改动：编辑前 CodeGraph 调用链和影响范围分析
- 新增或修改测试：测试编写规范
- AOTU/MOM 接口权限迁移：`api-permission-migration`
- AOTU/MOM UniApp OpenAPI/Alova 生成：`uniapp-api-generation`
- 调查节点：头脑风暴、逐问式需求确认（`grilling`）、最小范围控制和文件检索
- 计划节点：实施计划编写和复杂度约束
- 开发节点：必需调用 `test-driven-development`，保留先 RED、后最小 GREEN 的真实凭证
- 开发节点：必需调用内置 `minimum-module-compile`，记录模块、精确命令和 exit code
- 事务、锁、原生 SQL、并发、公共接口、共享服务、跨模块和高扇出改动：条件调用
  `codegraph-impact-analysis`，在编辑前保存调用路径和 Blast Radius，不能等返工后才刷新
- 验证、评审和交付节点：只有获得用户对当前范围的明确批准后才调用相应技能

## 四、不适用场景

不用于承载业务知识、SQL 安全规则或发布策略。

## 五、所需输入

需求编号、工作流节点、任务意图、系统与业务域、仓库类型、Agent 角色、风险、产出物、
已安装 Skill、人工批准范围和上下文预算。

## 六、提供能力

返回必需、命中后必需、条件、需批准和不可用决策，以及选择原因、来源、版本、许可证、风险、
内容哈希和预算。完整 Provider 规则见 `references/node-routing.toml`。

## 七、依赖工具

所选技能必须真实安装；缺失时报告来源和安装候选，不在 bootstrap 中自动下载或执行。
“已安装”只表示 Provider 可发现，“已登记”表示存在于路由策略，“已路由”表示当前节点和
意图确实匹配。三者不得互相替代。Agent 角色是匹配建议之一，明确意图可独立命中。

## 八、业务约束

业务事实只来自需求、画像和已审核业务技能。

## 九、数据约束

不默认加载全部技能或全部历史上下文。

## 十、风险

Markdown 不直接执行行为，权限和门禁仍由 Praxis Python 服务裁决。

## 调用协议

1. 使用 `praxis skill route-node` 生成当前节点计划。
2. 调用 Skill 前使用 `praxis skill invoke` 记录版本、内容哈希、会话和批准状态。
3. 完成 Skill 流程后使用 `praxis skill complete` 写入完成凭证。
4. 节点流转前使用 `praxis skill gate`；`skill.routed` 或命令记录不能替代调用凭证。
5. `blocked_pending_approval`、`unavailable` 和 `omitted_budget` 状态不得伪装为已调用。
6. 使用 `praxis doctor` 核对 `policy_without_provider`、
   `installed_without_policy` 和 `delegate_without_policy`；未登记的安装项不会自动进入路由。
7. `orca-cli`、`orca-per-workspace-env` 和 `obsidian-markdown` 明确排除，不参与 Provider 扫描。
8. 所有外部命令必须先由 RTK 代理：专用适配优先，其余按输出类型使用 `rtk test`、
   `rtk err` 或保留原始输出的 `rtk proxy`；机器 JSON 也走 `rtk proxy`。
9. 只有 RTK 自身执行失败时才允许直接命令降级，并记录原 RTK 命令、错误和降级命令；
   被代理命令自身失败不得伪装成 RTK 故障。普通文本搜索使用 `rtk rg`，不使用“rg-grep”。

## 十一、验证方法

检查路由决策、Token 预算、调用凭证、节点门禁和最终来源清单。

## 十二、知识来源

来源为 `skill.toml` 中登记的已安装方法技能。
