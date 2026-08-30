# Praxis Harness

确定性内核的 AI agent 运行时：会话状态由 append-only 事件流唯一裁决，模型只经
Commands 提案、runtime 只认 durable facts——UNKNOWN 是一等公民、capability 门
fail closed、崩溃可恢复、完成须验证。

**当前状态：v1 Release Candidate（M0–M8 全部里程碑已验收，2026-08-30）。**
v1 非目标已冻结（`docs/02` §1.1）；发布清单见 `docs/14-release-checklist.md`。

## 快速上手

前置 [mise](https://mise.jdx.dev)（`mise install` 装好锁定的 Bun 1.3.14）：

```bash
mise install && mise run install   # frozen lockfile
```

**确定性示例会话**（零网络，durable 事件逐条流式输出；脚本文件样例见 `docs/13`）：

```bash
bun apps/cli/src/index.ts run --db demo.db --root . \
  --script scripts/read-note.json --input "read the note"
```

**真实模型**（任意 OpenAI 兼容端点）：

```bash
export OPENAI_API_KEY=sk-…
bun apps/cli/src/index.ts run --db demo.db --root . --model deepseek-v4-flash --input "…"
```

**写操作须显式授权**（缺省 durable 拒绝，fail closed）：

```bash
bun apps/cli/src/index.ts run --db demo.db --root . --allow-write --script … --input "…"
```

**中断后续跑**：Ctrl-C / kill 后 turn 保持 open，`--session <id>` 续跑（§17 恢复编排）。

完整 walk-through（脚本文件样例、approval 演示、sessions 检视、退出码表）见
**`docs/13-cli-quickstart.md`**——全部命令逐字复制可运行。

## 核心文件

- `docs/01-technical-baseline.md`：技术选型、精确版本、依赖治理、代码规范、CI 基线。
- `docs/02-system-design.md`：完整系统架构、模块职责、依赖方向、状态机、事件模型、上下文、工具、权限、恢复和扩展设计。
- `docs/03-project-plan.md`：M0–M8 WBS、阶段出口、质量门勾选与 Definition of Done。
- `docs/04-ai-development-guide.md`：如何使用 AI 长期开发本项目，如何避免漂移、越界和"为了通过检查而改坏设计"。
- `docs/05-acceptance-strategy.md`：M0–M8 正式验收和发布准入。
- `docs/06-ai-development-control-plane.md`：AI 自动规划、守界、测试、验收与交接机制。
- `docs/07-architecture-conformance.md`：把系统设计转化为可由 guard/CI 检查的架构合同。
- `docs/08-ai-model-development-strategy.md`：主力编码模型、独立 Review、真实模型 Eval 与换模规则。
- `docs/09-dependency-inventory.md`：依赖五事实表 + 许可允许清单（漂移守卫测试）。
- `docs/10-memory-context-growth.md`：内存/上下文增长模型报告（恒界证明）。
- `docs/11-sqlite-corruption-recovery.md`：SQLite 损坏与恢复策略。
- `docs/12-architecture-current-state.md`：as-built 架构全景（包图、port→实现、公共 API 面、机器执法清单）。
- `docs/13-cli-quickstart.md`：CLI 快速上手全流程示例。
- `docs/14-release-checklist.md`：v1 RC 发布清单（release-day 动作留人工）。
- `docs/15-threats-and-limitations.md`：威胁缓解与限制（诚实陈述）。
- `CHANGELOG.md`：里程碑级变更记录。
- `AGENTS.md`：每次 AI 编码会话都必须进入上下文的短规则。
- `.agents/rules/`：按主题拆分的详细规则。
- `.agents/skills/`：高频开发任务的操作 Skill。

## 文档权威顺序

出现冲突时按以下顺序处理：

1. `docs/02-system-design.md`：当前系统设计与模块边界；
2. `docs/01-technical-baseline.md`：技术栈、依赖、代码/提交规范；
3. `docs/03-project-plan.md`：阶段计划、任务依赖和验收条件；
4. `AGENTS.md` 与 `.agents/rules/*`：AI/人类开发的常设规则；
5. `docs/decisions/*`：架构决策原因；
6. `docs/00-praxis-whitepaper.md`：理论来源和设计哲学，不直接覆盖当前工程事实。

**一条事实只保留一个权威位置。** 其他文件应链接到权威文档，而不是复制后形成多个版本。

## 仓库结构

```text
packages/contracts    durable 事件词汇 + EventStore/Model/Tool ports（唯一运行时依赖 zod）
packages/core         reducer、可恢复 agent loop、context 组装、capability、extension host
packages/provider-openai / store-sqlite / tools-local    adapters（实现 contracts 的 ports）
packages/testkit      ScriptedModelProvider + 事件工厂 + 内存 store（dev）
packages/extension-*  可选扩展（telemetry 观察、standing-orders 命令）
apps/cli              组合根：run / sessions 命令
evals/development-models   正式真实模型 eval 矩阵 + 基线记录
docs/                 设计、计划、符合性、策略与 subsystem 文档
.praxis/              AI 开发控制面机器状态（见下）
```

依赖方向 contracts ← core ← adapters ← apps 由 `tests/boundaries.test.ts` 与
`mise run test:architecture` 机器执法；全景见 `docs/12`。

## 开发原则

> Start simple, escalate on evidence.

先实现最小确定性闭环；只有真实测试、故障注入或任务轨迹证明现有设计不足时，才增加新机制。

## 质量门与测试

```bash
mise run check:all   # format/lint/typecheck/test/knip/test:architecture + coverage（Core 95/90 地板）
mise run test:store  # SQLite 套件（bun 运行时）
mise run test:cli    # CLI 套件
```

测试分层：unit（含 fault/security/soak/eval 完整性）、integration、property
（fast-check）、replay（崩溃-恢复 fixture）、fault、security、store、cli。

## AI 开发控制面

长期 AI 开发不依赖文档记忆。仓库以 `.praxis/` 机器状态 + `scripts/ai/` 控制脚本
约束开发（机制见 `docs/06`）：

- `.praxis/architecture.yaml`：机器可检查架构边界；
- `.praxis/milestones/`：M0–M8 可验收合同（全部已验收）；
- `.praxis/tasks/`：每次非微小开发的 Task Contract（allowed/forbidden paths）；
- `.praxis/state.yaml`：跨 AI 会话的当前真实项目状态；
- `.praxis/quality-gates.yaml`：真实 diff 到必须运行测试的映射。

```bash
mise run ai:plan   -- .praxis/tasks/<id>.yaml   # 激活任务（PLAN_READY）
mise run ai:guard  -- .praxis/tasks/<id>.yaml   # 改动边界检查
mise run ai:verify -- .praxis/tasks/<id>.yaml   # 跑质量门
mise run ai:accept -- .praxis/tasks/<id>.yaml   # 验收（高风险任务转人工）
mise run ai:handoff                             # 生成交接文档
```

每个任务循环的真实轨迹见 `.praxis/handoffs/`（M0–M8 共 40+ 份）。
