# Praxis Harness

可验证智能体运行时（verifiable agent runtime）。本仓库是 Praxis Harness 的唯一实现仓库：冻结设计文档、工程基线与代码在同库演进；理论来源见 `docs/00-praxis-whitepaper.md`。

## 当前状态

M0 — Repository Foundation 已完成并实证验收：clean clone 仅凭已提交文件即可复现工具链并通过 `mise run check:all`。各里程碑的规划与出口标准见 `docs/03-project-plan.md`；M1（Deterministic Session Kernel）尚未开始。

## 快速开始

环境搭建与贡献流程见 [CONTRIBUTING.md](./CONTRIBUTING.md)：`mise trust` → `mise install` → `bun install --frozen-lockfile`，统一质量入口为 `mise run check:all`。

## 仓库结构

```text
apps/cli/               # composition root（M2+ 实装）
packages/contracts/     # 协议、schema、ports；无 I/O
packages/core/          # 确定性 Agent Runtime（M1+ 实装）
packages/store-sqlite/  # EventStore SQLite adapter（M1.3 实装）
packages/provider-openai/
packages/tools-local/
packages/testkit/
tests/                  # 仓库级冒烟与依赖边界测试
docs/                   # 权威文档与 ADR（docs/decisions/）
.agents/                # AI 开发规则（rules/）与技能（skills/）
```

包依赖方向等架构事实以 `docs/02-system-design.md` 与 ADR-0002 为准，并由 `tests/boundaries.test.ts` 自动守护；各包当前为最小占位实现，不含业务代码。

## 文档权威顺序

出现冲突时按以下顺序处理：

1. `docs/02-system-design.md`：当前系统设计与模块边界；
2. `docs/01-technical-baseline.md`：技术栈、依赖、代码/提交规范；
3. `docs/03-project-plan.md`：阶段计划、任务依赖和验收条件；
4. `AGENTS.md` 与 `.agents/rules/*`：AI/人类开发的常设规则；
5. `docs/decisions/*`：架构决策原因；
6. `docs/00-praxis-whitepaper.md`：理论来源和设计哲学，不直接覆盖当前工程事实。

**一条事实只保留一个权威位置。** 其他文件应链接到权威文档，而不是复制后形成多个版本。

## 核心文件

- `docs/01-technical-baseline.md`：技术选型、精确版本、依赖治理、代码规范、Git/提交规范、CI 基线。
- `docs/02-system-design.md`：完整系统架构、模块职责、依赖方向、状态机、事件模型、上下文、工具、权限、恢复和扩展设计。
- `docs/03-project-plan.md`：从仓库初始化到 v1 RC 的 WBS、阶段出口、任务规范和 Definition of Done。
- `docs/04-ai-development-guide.md`：如何使用 AI 长期开发本项目，如何避免漂移、越界和“为了通过检查而改坏设计”。
- `AGENTS.md`：每次 AI 编码会话都必须进入上下文的短规则。
- `.agents/rules/`：按主题拆分的详细规则。
- `.agents/skills/`：高频开发任务的操作 Skill。

## 开发原则

> Start simple, escalate on evidence.

先实现最小确定性闭环；只有真实测试、故障注入或任务轨迹证明现有设计不足时，才增加新机制。
