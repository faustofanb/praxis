# Praxis Harness 开发基线包

本目录是 Praxis Harness 在进入应用代码开发之前的工程基线。它不是白皮书的重复，而是把白皮书中的原则转化为**可执行的技术选型、系统边界、开发计划和 AI 编码约束**。

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
- `docs/05-acceptance-strategy.md`：M0–M8 正式验收和发布准入。
- `docs/06-ai-development-control-plane.md`：AI 自动规划、守界、测试、验收与交接机制。
- `docs/07-architecture-conformance.md`：把系统设计转化为可由 guard/CI 检查的架构合同。
- `docs/08-ai-model-development-strategy.md`：主力编码模型、独立 Review、真实模型 Eval 与换模规则。
- `docs/12-architecture-current-state.md`：as-built 架构全景（包图、port→实现、公共 API 面、机器执法清单）。
- `docs/13-cli-quickstart.md`：CLI 快速上手——read/write/approval/resume 全流程示例（复制即可运行）。
- `AGENTS.md`：每次 AI 编码会话都必须进入上下文的短规则。
- `.agents/rules/`：按主题拆分的详细规则。
- `.agents/skills/`：高频开发任务的操作 Skill。

## 进入代码前的最低条件

只有以下条件全部满足，才进入 M1 应用代码实现：

- 技术栈和依赖版本已冻结；
- Core/Adapter/Composition Root 边界已接受；
- Event Store 与 Tool Execution 状态机已接受；
- v1 不做清单已冻结；
- CI、测试分层、提交规则和 AI 开发规则已启用；
- M0 验收清单全部通过。

## 开发原则

> Start simple, escalate on evidence.

先实现最小确定性闭环；只有真实测试、故障注入或任务轨迹证明现有设计不足时，才增加新机制。

## 阶段验收基线

项目 M0–M8 的正式放行标准见：

- `docs/05-acceptance-strategy.md` — 阶段验收、故障注入、CLI/TUI、真实模型 Eval 与 v1 发布准入规范。

任何 Milestone 的完成声明都必须同时满足项目规划书与该验收规范。

## AI 开发控制面

长期 AI 开发不再只依赖文档记忆。仓库必须以 `.praxis/` 机器状态 + `scripts/ai/` 控制脚本约束开发：

- `.praxis/project.yaml`：项目/v1 不变量；
- `.praxis/architecture.yaml`：机器可检查架构边界；
- `.praxis/milestones/`：M0–M8 可验收合同；
- `.praxis/tasks/`：每次非微小开发的 Task Contract；
- `.praxis/state.yaml`：跨 AI 会话的当前真实项目状态；
- `.praxis/quality-gates.yaml`：真实 diff 到必须运行测试的映射；
- `docs/06-ai-development-control-plane.md`：完整控制机制。

M0 必须把 `ai:brief / ai:plan / ai:guard / ai:verify / ai:accept / ai:handoff` 变成真实可执行命令。在此之前，这些文件属于 bootstrap contract；完成 M0 后它们成为开发流程的一部分。
