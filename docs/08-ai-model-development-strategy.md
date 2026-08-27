# Praxis Harness AI 开发模型使用策略

> 状态：Operational Baseline / 可随模型市场变化重新评估  
> 基准日期：2026-08-27  
> 目的：规定“用哪些模型开发 Praxis、谁负责实现、谁负责独立复核、什么时候允许更换模型”，而不是把某个厂商模型写进架构核心。

---

# 1. 结论

Praxis Harness 开发采用**双强模型 + 确定性机器验收**：

## 主力实现模型

**GPT-5.6 Sol + Codex**

推荐配置：

- 普通实现：`high`；
- Tier 0 / Agent Loop / Event / Capability / Recovery：`max`；
- 复杂跨包变更可在明确分工时使用 Codex 的并行/多 Agent 能力，但不得因此绕过 `.praxis` Task Contract、Scope Guard 和验收流程。

选择理由：

- OpenAI 当前官方把 GPT-5.6 Sol 定位为复杂推理与编程的旗舰模型，并称其为当前最佳 coding model；
- 在长周期真实仓库、终端工作和 DeepSWE 类任务上处于最强一档；
- Codex 与 `AGENTS.md`、Skills、命令执行、长任务工作方式和本项目既有工程规则天然匹配；
- 相比极高成本模型，Sol 当前有较好的能力/速度/成本平衡。

如果只能选**一个模型完成项目**，当前默认选它。

---

## 独立架构 / Tier 0 Reviewer

**Claude Opus 5 + Claude Code**

推荐用途：

- Core Constitution 变更；
- Event/Session durable contract；
- Agent Loop；
- Capability/security；
- Crash/UNKNOWN/reconciliation；
- Milestone promotion 前独立代码/设计 Review；
- 主力实现模型陷入反复失败时的第二认识来源。

选择理由：

- Anthropic 将 Opus 5 定位为长周期 Agent、软件工程与专业工作中的最强 Opus；
- 当前独立 coding-agent 评测中 Opus 5 + Claude Code 与 GPT-5.6 Sol + Codex 同处第一梯队，某些总体指标领先，而 Sol 在 DeepSWE、成本与执行时间等维度更有优势；
- 更重要的是：不同模型 + 不同 Harness 可以降低“实现者与审查者共享同一偏差”的相关性。

**Tier 0 任务禁止只用同一个模型的第二次 self-review 代替独立 Review。**

---

## 高强度升级模型（可选）

**Claude Fable 5**

适用：

- 极其复杂的多日架构/迁移；
- Opus 5 与 Sol 都无法稳定解决的问题；
- 有明确验收标准、成本合理时的 escalation。

不作为默认：

- 成本/资源更高；
- 能力过强并不意味着普通小任务收益更高；
- 项目制度要求“从简单开始，由 Evidence 升级”，不能因为存在最强模型就所有任务一律使用。

---

## 成本/速度工作模型（后续可选）

候选：

- **Gemini 3.7 Flash**：当前 Google 面向 coding/agents 的高速度工作模型，适合大批量低/中风险实现、检索、辅助测试生成；
- **DeepSeek-V4-Flash**：当前 DeepSeek API 的 Agent/Coding 主力 Flash，Terminal/DeepSWE/Tool 使用指标强，且支持 Responses API/Codex 适配，可作为成本敏感或国内/开放生态路线的候选。

这两类模型在 Praxis 开发中只能承担：

- Tier 1/2 低风险任务；
- 大量机械实现；
- 测试/fixture/docs 初稿；
- 独立探索分支。

在本项目自己的 Repo Eval 证明质量不低于主力模型前，不自动替代 Tier 0 主力/Review。

---

# 2. 为什么不只选“排行榜第一”

Coding Agent 的表现是：

```text
Model
+
Harness
+
Tool set
+
Prompt/Rules
+
Repository
+
Test feedback
+
Budget
```

共同结果。

当前公开评测甚至会因为 benchmark 任务质量、污染、Harness 版本和计分方法变化而改变排名。OpenAI 2026 年也公开审计过 SWE-bench 系评测，指出部分 coding benchmark 存在显著坏题/信号问题。

因此外部排行榜只负责：

> **选择值得进入候选集的模型。**

真正决定 Praxis 开发主力的是：

> **Praxis Repo Eval。**

---

# 3. Praxis Repo Eval

从 M2 起建立 `evals/development-models/`。

不测试模型背算法题，而测试本项目真正需要的工作。

## 3.1 任务集

至少包含：

### A. Design adherence

给系统设计 + task contract，要求做一个小功能。

评价：

- 是否越包边界；
- 是否顺手扩 scope；
- 是否引入无必要 dependency；
- 是否把 adapter 放进 Core。

### B. Test discipline

给一个 Agent Loop defect。

评价：

- 是否先定位 Evidence；
- 是否添加 ScriptedModel integration test；
- 是否运行 required gates；
- 是否删除/弱化已有测试。

### C. Recovery reasoning

给 crash/UNKNOWN 场景。

评价：

- 是否把 timeout 误判 failure；
- 是否设计幂等/reconciliation；
- 是否保留 durable state 一致性。

### D. Long-horizon implementation

给跨 3–5 package 的明确设计任务。

评价：

- 是否维护 Goal/Scope；
- 是否分阶段验证；
- 是否过度重构；
- 最终 diff 可维护性。

### E. Review

给一个故意包含：

- architecture violation；
- missing failure test；
- fake completion；
- over-broad dependency；

的 PR。

评价模型能否找到真正 P0/P1，而不是只评 style。

---

# 4. 评价指标

记录：

```text
acceptance_pass_rate
required_gate_compliance
architecture_violation_rate
scope_expansion_rate
regression_rate
rework_rounds
human_review_findings
wall_time
model_cost
tool_calls
changed_LOC
```

其中最重要：

1. Acceptance pass rate；
2. Architecture violation rate；
3. Human/independent review 漏洞；
4. Rework rounds。

**Token 少不是第一目标，代码写得多也不是第一目标。**

---

# 5. 模型分工制度

## 普通 Tier 1/2 任务

```text
GPT-5.6 Sol (high)
→ machine gates
→ auto/human acceptance according to Task Contract
```

## Tier 0 / 高风险任务

```text
GPT-5.6 Sol (max) implementation
        ↓
machine verification
        ↓
Claude Opus 5 independent review
        ↓
required human/independent acceptance
```

也可以反过来：

```text
Claude Opus 5 implementation
→ GPT-5.6 Sol independent review
```

关键不是固定谁写，而是：

> **实现与独立复核不要依赖同一条模型/Harness 判断链。**

---

# 6. AI 自动验收中模型的地位

模型不拥有 Task/Milestone acceptance 主权。

模型可以：

- 生成 plan；
- review diff；
- 解释失败；
- 对照 acceptance checklist；
- 提出 PASS/FAIL 建议。

真正决定 acceptance：

```text
machine gates
+
scenario/failure evidence
+
acceptance policy
+
required independent/human approval
```

因此换模型不会改变项目质量制度。

---

# 7. 什么时候允许更换主力模型

不追逐每周新模型。

重新评估触发条件：

1. 当前主力模型连续在 Repo Eval 明显落后；
2. 新模型在公开 coding-agent 评测进入第一梯队；
3. 新模型在 Praxis Repo Eval 的 acceptance / architecture / rework 三个核心指标有统计上明显改善；
4. 成本/延迟改善足够大且质量不降低；
5. 当前模型/API 被弃用或可用性发生重大变化。

建议：

- 每个 Milestone 结束可做一次轻量比较；
- 正常情况下每月最多一次主力模型评审；
- 模型切换不修改 Core Architecture，仅更新开发政策/CI eval matrix。

---

# 8. 当前推荐矩阵（2026-08-27）

| 工作类型 | 首选 | 次选 | 说明 |
|---|---|---|---|
| 一般实现 | GPT-5.6 Sol / Codex high | Claude Opus 5 / Claude Code | Sol 当前速度/成本/长仓库工程综合很强 |
| Core/Tier 0 实现 | GPT-5.6 Sol max | Claude Opus 5 max/xhigh | 高 effort，但仍必须机器验收 |
| 独立架构 Review | Claude Opus 5 | GPT-5.6 Sol | 尽量不同厂商/Harness |
| 极难多日任务 | Claude Fable 5 | GPT-5.6 Sol Ultra/Max | Evidence 驱动才升级 |
| 高速低风险任务 | Gemini 3.7 Flash high | GPT-5.6 Luna / DeepSeek-V4-Flash | 必须经过相同质量门 |
| 成本敏感 Agent 工作 | DeepSeek-V4-Flash | Gemini 3.7 Flash | 后续用 Repo Eval 决定 |
| Praxis 自身模型 Eval | Sol + Opus 5 + 一个高效模型 | — | 至少跨两个厂商 |

---

# 9. 最终推荐

如果现在立即开始 Praxis Harness M0/M1：

> **使用 GPT-5.6 Sol in Codex 作为主力编码模型。**

M0/M1 本身主要是严格工程基础，建议：

- 普通任务：high；
- `contracts/core/event/reducer/store/replay`：max；
- 每个 Tier 0 合并点再使用 Claude Opus 5 做独立 Review；
- 机器 Test/Acceptance 永远高于两个模型的意见。

这套组合最符合 Praxis 本身已经确立的原则：

> **强生产能力 + 独立监督 + 现实验收。**

---

# 10. 参考来源（截至 2026-08-27）

- OpenAI, *GPT-5.6: Frontier intelligence that scales with your ambition* / OpenAI API Model Guidance.
- Anthropic, *Introducing Claude Opus 5*; *Claude Fable 5*; *Introducing Claude Sonnet 5*.
- Google, *Introducing Gemini 3.7 Flash*.
- DeepSeek API Docs, 2026-07-31 DeepSeek-V4-Flash update.
- Artificial Analysis, GPT-5.6 / Opus 5 / Gemini 3.7 Flash analyses and Coding Agent Index.
- OpenAI, *Separating signal from noise in coding evaluations*.
