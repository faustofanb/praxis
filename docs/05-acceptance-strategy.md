# Praxis Harness 验收策略

> 状态：Baseline / Normative  
> 机器合同：`.praxis/milestones/*.yaml`、`.praxis/quality-gates.yaml`  
> 任务级验收流程与边界：`docs/06-ai-development-control-plane.md` §5、§10

## 1. 目的

本文定义 M0–M8 每个 Milestone 以及 v1 发布的**正式验收制度**：验收分几层、证据长什么样、谁能签核、失败如何返工。它不复制各 Milestone 的具体出口条件——那些属于：

- `docs/03-project-plan.md`：WBS、各阶段 Exit Criteria、DoR/DoD；
- `.praxis/milestones/Mn.yaml`：机器可读的 Milestone 合同；
- `docs/acceptance/Mn.md`：人类可读的验收记录（本文定义其填写规则）。

一条事实只保留一个权威位置：本文管"怎么验收"，`docs/03` 管"验收什么"。

---

## 2. 验收的五个层次

任何 Milestone 完成声明都必须按层给出证据；"代码写完了"不是其中任何一层。

| 层次 | 内容 | 证据形式 |
|---|---|---|
| 1. Machine Gates | `mise run` 质量门（format/lint/typecheck/unit/build/knip，及后续 integration/replay/property/fault/security） | `ai:verify` 写入 `.praxis/state.yaml` 的 machine-readable gate summary，或 CI run |
| 2. Scenario Acceptance | Milestone 合同中预设场景的端到端通过（如 clean clone/bootstrap/check-all） | Scenario report：命令、环境、输出摘要、commit SHA |
| 3. Failure Acceptance | 负向证明：门真的会失败（注入 lint/type/测试错误必须让 gate FAIL），故障注入用例按期通过 | Failure report：注入了什么、预期 FAIL、实际 FAIL |
| 4. Human Demo | Milestone 合同声明 `human_demo_required: true` 时才需要 | Demo 记录：操作者、步骤、观察结果 |
| 5. Real-model Eval | Milestone 合同声明非 `none` 时需要；方法与模型角色见 `docs/08-ai-model-development-strategy.md` | Eval summary：任务集、模型、结果对比 |

Machine Gates 的命名必须与 `.praxis/quality-gates.yaml` 的 `gates` 键一致；Milestone 合同不得引用不存在的 gate。

---

## 3. 三个验收对象与签核权

### 3.1 Task 验收

按 `docs/06` §10 的边界执行：普通低风险实现可由 `ai:accept` 机器验收；涉及 ADR、Event schema、Capability 语义、依赖引入、用户可见契约大改的任务只能进入 `ACCEPTANCE_READY`，由人类或独立评审放行。

### 3.2 Milestone promotion

负责实现的 AI **不得自行推广 Milestone**（`model_cannot_promote_milestones`）。推广的最终状态变更至少要求：

```text
Machine Gates PASS
Scenario PASS
Failure Acceptance PASS
Required Human Demo PASS（如有）
Required Real-model Eval 完成（如有）
Independent/Human approval
```

签核由人类或按 `docs/08` 担任独立评审的模型完成；`docs/acceptance/Mn.md` 的 Exit Decision 记录签核者身份。

### 3.3 v1 发布准入

以 `docs/03` M8 出口条件 + `docs/acceptance/M8.md` + `.agents/skills/release-check/SKILL.md` 的发布门为准。发布检查不得因"赶进度"跳过 soak/恢复演示与依赖清点。

---

## 4. 验收记录（docs/acceptance/Mn.md）填写规则

每个 `docs/acceptance/Mn.md` 按 `docs/acceptance/M0.md` 的模板维护，规则：

1. **Machine Gates** 勾选前提：对应 gate 在被验收的 commit 上真实通过，且证据可复现；
2. **Scenario / Failure Acceptance** 勾选必须附证据引用（见 §5）；
3. **Exit Decision** 只允许三种值：`PENDING`（未验收）、`ACCEPTED`（已签核）、`REJECTED`（返工，附原因）；
4. `Accepted by` 只能由实际签核者填写——实现方 AI 填 `TBD` 之外的值视为违反本策略；
5. Milestone 推广后，将 `.praxis/milestones/Mn.yaml` 的 `status` 从 `active` 改为 `accepted`（或 `rejected`），并更新 `.praxis/state.yaml`。这是人类/独立评审的操作，不是编码 AI 的操作。

---

## 5. 证据规则

所有 Evidence Artifacts 必须满足：

- **可复现**：附命令或 CI run 引用 + commit SHA；不接受"我本地跑过"；
- **机器可读优先**：gate summary 来自 `ai:verify` 输出或 CI 日志，不手抄结论；
- **同 commit**：Scenario/Failure 证据必须来自与 Machine Gates 相同或更新的 commit；
- **不弱化**：为了让验收通过而删除/放宽测试或 gate 配置，本身构成验收失败（见 §6）。

---

## 6. 失败与返工

- 任一层 FAIL：任务进入 `REWORK`，修复后重新走 verify；不允许跳层放行；
- Failure Acceptance 发现"门不会失败"（注入错误仍 PASS）：按 P1 处理，先修 gate 再继续；
- 返工期间发现验收标准本身不合理：修改的是 Milestone 合同（`.praxis/milestones/`）+ 对应 acceptance 文档，并说明原因——不是绕过标准。

---

## 7. 与其他文档的关系

| 文档 | 职责 |
|---|---|
| `docs/03-project-plan.md` | 各 Milestone 出口条件、DoR/DoD、PR 策略 |
| `docs/06-ai-development-control-plane.md` | Task 级 ai: 流程、自动验收边界、防漂移机制 |
| `docs/07-architecture-conformance.md` | Milestone 验收附加的设计—实现一致性问答 |
| `docs/08-ai-model-development-strategy.md` | 独立评审角色与真实模型 Eval 方法 |
| `.praxis/quality-gates.yaml` | gate 名称到命令的机器映射 |
| `.praxis/milestones/*.yaml` | 每个 Milestone 的机器合同 |

---

## 8. 最终原则

> **验收不是仪式，是对"系统能被反证"的持续证明。**

能自动检查的绝不靠自觉；能负向证明的（门必须会失败）必须真的注入过失败；不能自动签核的（里程碑推广、安全边界、durable contract）绝不由实现方自己签。这三条合在一起，才是"实践检验"在工程上的落地。
