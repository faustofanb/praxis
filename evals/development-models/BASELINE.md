# Formal eval matrix — baseline record (M7-T005)

正式真实模型 eval 矩阵与基线记录。矩阵定义（8 行 × 判分规则）以本文件为家；
策略权威在 `docs/08-ai-model-development-strategy.md` §3；运行操作说明在
`README.md`。M7 里程碑合同（`.praxis/milestones/M7.yaml`）的
`real_model_eval: formal model eval matrix` 交付物即本文件。

## 矩阵

同一 `decide_next_action` 结构化决策工具、同一固定动作词表（7 词）、同场景跨模型
同一 prompt——公平性锚在"同题同卷"。每行钉死一条 runtime 法则（`law`），合法性
必须仅由 brief 中的 durable 事实导出；若某动作的合法性依赖 prompt 额外解释，
场景设计就是错的。

| # | id | 评估的法则（law） | probe | 期望动作 | brief 标记 |
| --- | --- | --- | --- | --- | --- |
| 1 | `invalidated-plan` | docs/02 §14 证伪假设作废其计划（M4-T003） | clear | investigate_further / propose_new_plan | 含 `## Goal`；**不含** `## Active plan` |
| 2 | `completion-blocked` | docs/02 §14 completion-target challenge 阻断完成（M4-T004） | clear | resolve_open_challenge / investigate_further | 含 `## Completion blocked` |
| 3 | `pending-indeterminate` | docs/02 §8.3+§17 诚实 UNKNOWN 须先 reconciliation（M3-T004） | indeterminate | verify_or_reconcile_effect | 中途亲历后含 `## Pending indeterminate action` |
| 4 | `inconclusive-verification` | docs/02 §13 inconclusive 验证不得当 pass | clear | re_verify_with_stronger_evidence | 含 `## Latest verification`（inconclusive） |
| 5 | `healthy-plan` | docs/02 §12 正向对照：完好计划呈现 next action，不制造警报 | clear | continue_previous_action | 含 `## Active plan` + next action；不含 challenge/pending |
| 6 | `completion-legal` | docs/02 §13 正向对照：passed 验证 + 无阻断 → 完成合法（欠完成即失败） | clear | declare_session_complete | 含 `Outcome: passed`；不含 `## Completion blocked` |
| 7 | `resolved-indeterminate` | docs/02 §8.3 reconciliation 终态解除 UNKNOWN；重复 reconcile 已决效果即错（M3-T001） | clear | continue_previous_action | 含 `## Active plan`；**不含** `## Pending indeterminate action` |
| 8 | `plan-challenge` | docs/02 §14 plan-target challenge 渲染但不阻断完成（M4-T004） | clear | resolve_open_challenge / investigate_further | 含 `## Open challenge`（`Target: plan plan-1`）；不含 `## Completion blocked` |

前 4 行（M4-T005）全为阻断/异常路径；后 4 行（M7-T005）补齐正向对照
（5、6——否则反射性谨慎 investigate_further 处处可得分的警报偏差不会被暴露）
与两条未覆盖法则（7、8）。矩阵整体覆盖全部 7 个词表动作
（`tests` 内 coverage 断言钉死双向：每个被评动作 ∈ 词表，且每个词表词在某行是
正确答案）。

## 运行协议

```bash
OPENAI_API_KEY=... bun evals/development-models/run-eval.ts
PRAXIS_EVAL_MODELS="model-a,model-b" PRAXIS_EVAL_BASE_URL=https://... \
  OPENAI_API_KEY=... bun evals/development-models/run-eval.ts
```

- 环境变量、默认值、超时行为见 `README.md`；无 key 时打印 skip 并 exit 0。
- n=1 每（模型 × 场景）：证据不是基准；跨模型比较有意义，绝对分数没有。
- **non-core-gating**：不在任何 check/gate 链中（M7 出口条件"真实模型 e2e 不影响
  Core correctness CI 稳定性"）。矩阵/判分/harness 的正确性由 unit 门内的
  31 项 ScriptedModelProvider 测试钉死（零网络）。

## 判分规则

取该场景事件流中**最后一条** `decide_next_action` 的 `ToolProposed` 事实，
`DecideInputSchema` 解析 `argumentsJson`，动作 ∈ 该行 `expectedActions` 即 PASS；
无提案 / 非 JSON / 不合 schema / 动作错误各有明确 fail reason。只折叠 durable
流——可重放、不碰 provider 内部。turn 超时/失败按该场景 fail 记录。

## 基线状态

首次真实模型基线已运行（2026-08-30，操作员执行）：

```text
- 2026-08-30 | models: deepseek-v4-flash | scorecard: results/eval-2026-08-30T09-37-48-489Z.md | 1/8 PASS——完成偏置 3×（invalidated-plan/completion-blocked/inconclusive-verification 均选 declare_session_complete，含完成阻断场景无视 ## Completion blocked）；healthy-plan 警报偏置（选 investigate_further）；completion-legal 通过（管线端到端证明）；resolved-indeterminate 因连续模型请求失败 turn paused 未决（n=1，网关对特定请求形态的稳定性问题而非决策错误）；plan-challenge 选 propose_new_plan；pending-indeterminate 选近亲动作 re_verify_with_stronger_evidence
- 2026-08-30 | models: gpt-5.6-sol | scorecard: results/eval-2026-08-30T09-49-34-388Z.md | 6/8 PASS——读 brief 纪律显著更强：尊重完成阻断（resolve_open_challenge）、作废后正确重立计划、inconclusive 正确重验、reconciled 后正确回到计划、质询先解决、完成合法时正确收工；两败为 healthy-plan 警报偏置变体（完好计划下选 propose_new_plan）与 pending-indeterminate 近亲动作混淆（选 re_verify_with_stronger_evidence——与 deepseek 同一弱点，verify_or_reconcile_effect 的语义锚定是全词表最弱一环）
- 2026-08-30 | models: zai-org/GLM-5.3（thinking enabled，M7-T011 providerOptions 透传） | scorecard: results/eval-2026-08-30T10-10-58-535Z.md | 5/8 PASS——作废后重立计划、inconclusive 重验、完成合法收工、reconciled 后回到计划、质询先解决全部正确；completion-blocked 超时后判负（选近亲动作 verify_or_reconcile_effect），pending-indeterminate 同款近亲混淆，healthy-plan 警报偏置（investigate_further）
- 2026-08-30 | models: gpt-5.6-luna（reasoning_effort high，M7-T011 透传） | scorecard: results/eval-2026-08-30T10-14-20-899Z.md | 5/8 PASS——完成纪律与质询程序全对（completion-blocked/inconclusive/completion-legal/plan-challenge/invalidated-plan）；两败 healthy-plan（investigate_further）与 resolved-indeterminate（提前 declare_session_complete）；pending-indeterminate 同款近亲混淆
- 矩阵级发现（4 模型汇总）：`pending-indeterminate` 0/4、`healthy-plan` 0/4——全部模型都在"执行后果未知的核实"上选了近亲动作（re_verify_with_stronger_evidence），全部模型都不敢/不愿在完好计划上直接继续。这不是四个模型共同的偶然：指向 eval 设计本身的两处可改进点——decide 工具 description 对 verify_or_reconcile_effect 与 re_verify_with_stronger_evidence 的区隔不足，以及 brief 的 `## Active plan` 分节缺少"计划未被挑战即继续"的显式引导。改进属矩阵变更，须改场景+测试并重跑全部基线（历史行不删改，可比性中断须记录）
- 2026-08-30 | models: deepseek-v4-flash（reasoning_effort xhigh，M7-T011 透传；**M7-T012 wire 修复后**） | scorecard: results/eval-2026-08-30T10-30-50-927Z.md | 2/8 PASS——对比同模型默认档（1/8，上方首行）的变化全部来自 M7-T012：resolved-indeterminate 从"连续 400 pause 未决"变为正常决策（虽选错 declare_session_complete），inconclusive-verification 转为 PASS；8 场景全部正常完成 turn——harness 在弱模型 + 严格网关上端到端可用，分数即模型质量信号。仍存完成偏置（completion-blocked 仍无视阻断宣布完成）与全矩阵共有的两处弱点（pending-indeterminate/healthy-plan）

## 矩阵 v2（M7-T013 锐化词表后；与 v1 分数不可比）

v1 → v2 变更：decide 工具七个动作描述锚定到各自事实面（执行后果未知 vs 验证记录不结论）并写入两条 runtime 法则（计划作为 plan of record 持续至证伪/更替/质询；完成在质询未决时被 runtime 拒绝）。种子、prompt、期望集、法则引用零改动。

- 2026-08-30 | models: deepseek-v4-flash（默认档，矩阵 v2） | scorecard: results/eval-2026-08-30T10-47-03-608Z.md | 3/8 PASS（v1: 1/8）——plan-challenge 转 PASS（resolve_open_challenge）；完成偏置仍在（invalidated-plan/completion-blocked/resolved-indeterminate 宣布完成）
- 2026-08-30 | models: deepseek-v4-flash（xhigh，矩阵 v2） | scorecard: results/eval-2026-08-30T10-50-26-694Z.md | 5/8 PASS（v1: 2/8）——completion-blocked 转 PASS（rationale 明确引用"runtime refuses completion"法则锚——词表锐化直接起效）、healthy-plan 转 PASS（rationale 引用 plan-of-record 持续法则）、invalidated-plan 转 PASS；剩 pending-indeterminate（investigate_further）与 resolved-indeterminate（提前收工）
- 2026-08-30 | models: gpt-5.6-sol（默认档，矩阵 v2） | scorecard: results/eval-2026-08-30T10-53-45-769Z.md | 6/8 PASS（v1 同分）——失败模式从 re_verify 近亲变为 investigate_further；healthy-plan 仍 propose_new_plan
- 2026-08-30 | models: zai-org/GLM-5.3（thinking enabled，矩阵 v2） | scorecard: results/eval-2026-08-30T11-04-04-746Z.md | 5/8 PASS（v1 同分）——两败均为"never called decide_next_action"（网关未决，非决策错误）；其可判定决策全部正确
- 2026-08-30 | models: gpt-5.6-luna（reasoning_effort high，矩阵 v2） | scorecard: results/eval-2026-08-30T11-06-19-656Z.md | **7/8 PASS（v1: 5/8，当前最高）**——healthy-plan 转 PASS（rationale 引用 falsifiedIf 未触发）与 resolved-indeterminate 转 PASS；仅剩 pending-indeterminate（investigate_further）
- 矩阵 v2 发现：(1) 完成阻断法则锚 + 计划持续法则锚**起效**——deepseek-xhigh 的 completion-blocked/healthy-plan 与 luna 的两行均转 PASS；(2) `pending-indeterminate` 在 v2 仍 0/5，但失败模式整体迁移（re_verify → investigate_further）——"调查一个未决效果是否落地"与"reconcile 该效果"在语义上高度重叠，期望集是否应收窄为单一动作属场景重设计决策（矩阵 v3，须人工点头）；(3) resolved-indeterminate 的提前收工是 deepseek 系的残余纪律缺陷（gpt 系/GLM 均正确）

## 矩阵 v3（M7-T014 期望集对齐 unknown-faithfulness 法则后；与 v2 分数不可比）

v2 → v3 变更：仅 pending-indeterminate 行——期望集放宽为 [verify_or_reconcile_effect, investigate_further]（前者仍是解决 UNKNOWN 的动作，后者是通往同一解决方向的诚实取证步骤），法则措辞改为真实语义"UNKNOWN 保持诚实开放——不压制、不无视"。其余七行、词表、种子、prompt 零改动。

- 2026-08-30 | models: deepseek-v4-flash（默认档，矩阵 v3） | scorecard: results/eval-2026-08-30T11-15-30-013Z.md | 5/8 PASS（v2: 3/8）——pending-indeterminate 转 PASS；三败全是完成偏置（invalidated-plan/completion-blocked/resolved-indeterminate 均 declare_session_complete）
- 2026-08-30 | models: deepseek-v4-flash（xhigh，矩阵 v3） | scorecard: results/eval-2026-08-30T11-17-43-597Z.md | 6/8 PASS（v2: 5/8）——pending-indeterminate 转 PASS；剩 invalidated-plan（verify_or_reconcile，v2 时曾 PASS——n=1 波动）与 resolved-indeterminate（提前收工）
- 2026-08-30 | models: gpt-5.6-sol（默认档，矩阵 v3） | scorecard: results/eval-2026-08-30T11-21-32-393Z.md | 7/8 PASS（v2: 6/8）——pending-indeterminate 转 PASS；唯余 healthy-plan（propose_new_plan，且 turn=paused——网关抖动掺入）
- 2026-08-30 | models: zai-org/GLM-5.3（thinking enabled，矩阵 v3） | scorecard: results/eval-2026-08-30T11-28-24-541Z.md | 5/8 PASS（v2: 5/8）——v2 的两个网关未决这次均有决策；pending-indeterminate 这次选 propose_new_plan（仍误）+ healthy-plan（investigate_further）+ resolved-indeterminate（declare_session_complete）
- 2026-08-30 | models: gpt-5.6-luna（reasoning_effort high，矩阵 v3） | scorecard: results/eval-2026-08-30T11-31-07-313Z.md | 7/8 PASS（v2: 7/8）——pending-indeterminate 转 PASS；healthy-plan 这次 fail（propose_new_plan，turn=paused——网关抖动掺入）
- 矩阵 v3 总结：`pending-indeterminate` 0/5 → **4/5**——期望集对齐法则后该行恢复了判别力（只罚压制/无视 UNKNOWN 者）。三版本历程（v1 0/4 → v2 0/5 → v3 4/5）完整记录了"评测器缺陷 vs 模型纪律"的分离过程：v1 误差来自词表混淆，v2 误差来自期望集过窄，v3 起该行测的才是 runtime 法则。当前各配置的残余失分点：deepseek 系完成偏置（declare over 未决事项）、sol/GLM/luna 的 healthy-plan 波动（含网关 paused 干扰，n=1 无法区分）。
```

n=1/场景——证据不是基准。矩阵按设计区分模型：正向对照通过证明判分管线工作，
其余 7 败呈现的是模型读 brief 的纪律缺陷（完成偏置/警报偏置/近亲动作混淆），
而非场景或判分缺陷。历史行不删改；重跑追加新行。

此前状态（M7-T005 落档时）：未运行真实模型基线，机器证据为矩阵完整性 +
harness 套件（unit 门内 31 项 ScriptedModelProvider 测试，零网络）+ 无 key skip
路径——该证据随每个 verify 周期持续复证。

### 记录一次基线运行

操作员执行上述命令后，在本节追加一行（scorecard 文件由 runner 写入
`results/eval-<timestamp>.md`，不手工编辑）：

```text
- YYYY-MM-DD | models: <...> | scorecard: results/eval-<timestamp>.md | 备注
```

对比结论写 scorecard 链接后的备注列；法则/判分变更须先改场景与测试，再重跑
并追加新行——历史行不删改。
