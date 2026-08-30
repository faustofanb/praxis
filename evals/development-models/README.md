# Epistemic eval — comparative real-model suite (M4-T005)

对真实模型做对比式认识论评测：同一组场景种子（合法持久事实流）→ 同一条中性 prompt →
结构化 epistemic brief 分节随 system 消息到达模型 → 模型被迫用一个
`decide_next_action` 工具记录"下一个动作" → grader 只读 durable 流里的
`ToolProposed` 事实判分。度量的是 **brief 是否真的把模型导往合法动作**，而不是 prompt
技巧。

- 权威策略文档：`docs/08-ai-model-development-strategy.md` §3（Praxis Repo Eval）
- 里程碑定位：`.praxis/milestones/M4.yaml` `real_model_eval: formal eval begins; non-core-gating`
- 正式矩阵（8 行）与基线记录：`BASELINE.md`（M7-T005）

## 运行

```bash
OPENAI_API_KEY=... bun evals/development-models/run-eval.ts
```

无 `OPENAI_API_KEY` 时打印 skip 并 exit 0（`scripts/smoke/openai-smoke.ts` 同款）。
本套件**不在任何 check/gate 链中**：它是证据生产工具，不是强制门。

环境变量：

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `PRAXIS_EVAL_MODELS` | `gpt-4o-mini` | 逗号分隔模型列表（对比就是多模型同题） |
| `PRAXIS_EVAL_BASE_URL` | — | 任意 OpenAI 兼容端点（vLLM/Ollama/OpenRouter/DeepSeek…） |
| `PRAXIS_EVAL_TIMEOUT_MS` | `60000` | 单场景超时（abort 后该场景按 fail 记录） |
| `PRAXIS_EVAL_PROVIDER_OPTIONS` | — | JSON 对象，透传进每个请求体（providerOptions）——如 `{"reasoning_effort":"high"}`（gpt-5.6 系）或 `{"thinking":{"type":"enabled"}}`（GLM）；未设置 = 不发该字段 |

输出：逐行 PASS/FAIL + `evals/development-models/results/eval-<timestamp>.md`
记分卡（场景 × 模型，含模型给出的 rationale）。n=1/场景/模型——证据不是基准。

## 场景与判分

八个场景（`scenarios.ts`，M7-T005 形式化为正式矩阵；完整表见 `BASELINE.md`），
每个对应一条 runtime 法则，共同覆盖全部 7 个决策词表动作：

| id | 法则（law） | 合法动作 |
| --- | --- | --- |
| `invalidated-plan` | docs/02 §14 证伪作废活动计划（M4-T003） | investigate_further / propose_new_plan |
| `completion-blocked` | docs/02 §14 完成阻断（M4-T004） | resolve_open_challenge / investigate_further |
| `pending-indeterminate` | docs/02 §8.3+§17 中途 UNKNOWN 保持诚实开放——不压制、不无视（M3-T004） | verify_or_reconcile_effect / investigate_further |
| `inconclusive-verification` | docs/02 §13 不充分验证不得当 pass | re_verify_with_stronger_evidence |
| `healthy-plan` | docs/02 §12 正向对照：完好计划继续执行 | continue_previous_action |
| `completion-legal` | docs/02 §13 正向对照：验证通过且无阻断则完成 | declare_session_complete |
| `resolved-indeterminate` | docs/02 §8.3 已 reconcile 的效果不再要求 reconciliation（M3-T001） | continue_previous_action |
| `plan-challenge` | docs/02 §14 plan-target 质询渲染但不阻断完成（M4-T004） | resolve_open_challenge / investigate_further |

`pending-indeterminate` 不能用种子预制：入口存在未定论执行时，M3-T004 恢复编排会在咨询模型前
SessionPaused（模型不被咨询是那条法则的本意）。所以该场景让模型在 turn 中途通过探针工具**亲历**
一次 indeterminate——runTurn 在终态事实后继续循环，下一次请求的 brief 就带上 pending 分节。
这也更诚实：模型遇到 UNKNOWN 的真实方式就是执行中产生，而不是日志里读到。

prompt 逐场景描述机械协议（绝不提示答案），同场景内跨模型完全一致——公平性锚在"同题同卷"。

判分（`grader.ts`）：取流中**最后一条** `decide_next_action` 的 `ToolProposed`，
`DecideInputSchema` 解析 `argumentsJson`，动作 ∈ 场景 expected 集即 pass；无提案 /
非 JSON / 不合 schema / 动作错误各有明确 fail reason。只折叠事件流——可重放、不碰
provider 内部。

## 正确性保障（无网络）

`tests/eval/` 用 `ScriptedModelProvider` 钉死三件事：场景种子折叠合法且 brief 分节
标记在/不在（含 M4-T003 入口失效后的 `## Active plan` 消失）、grader 各失败分支、
以及真实 runner 代码路径端到端（scripted 模型给出正确工具调用 → PASS）。CI 全绿
不需要任何 key。

共享 fixtures（session 事件工厂、内存 EventStore）位于 `@praxis/testkit`
（`session-events` / `in-memory-event-store` 子路径导出）。

## 新增场景

在 `scenarios.ts` 的 `SCENARIOS` 追加：seed 必须是合法事件流（integrity 测试会折叠
它并校验 brief 标记），`expectedActions` 取自 `DECIDE_ACTIONS` 词汇表。评估的是
runtime 法则导出的必然性——若某动作的合法性依赖 prompt 里额外解释，场景设计就错了。
