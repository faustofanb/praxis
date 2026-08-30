# Changelog

Praxis Harness 的里程碑级变更记录（M0 → M8 v1 RC）。详细任务证据见各
`.praxis/handoffs/`；法则与设计权威见 `docs/02`。

## M8 — v1 Release Candidate（2026-08-30）

- as-built 架构全景与公共 API 面文档（`docs/12`）；子系统索引终化。
- CLI quickstart（`docs/13`）：read / write approval / 真实模型 / resume 全流程。
- CLI capability 接线：`--allow-write` / `--allow-bash`（缺省 durable 拒绝，fail closed）。
- 工程发布验收：干净克隆场景全路径 + kill→resume→finish + 失败注入证明（M8-T003）。
- v1 release eval 基线：冻结矩阵 v3 × 五配置（M8-T004）。
- v1 非目标冻结、发布清单（`docs/14`）、威胁与限制（`docs/15`）。

## M7 — Quality Hardening（2026-08-30）

- 状态机硬化：全词汇表 fast-check 套件 + 影子机器（M7-T001）。
- P0 修复：provider 逃逸后禁重试（durable 事实翻倍/幽灵 tool call）；逃逸法则入 §10（M7-T002）。
- 密钥禁锢套件：§18 全图深搜（M7-T002）。
- 10k turn soak + 恰好线性增长证明 + 折叠成本 tripwire（M7-T003）。
- 依赖五事实清单 + 许可允许清单漂移守卫（`docs/09`，M7-T004）。
- eval 形式化：8 行正式矩阵 + `BASELINE.md` 基线制度（M7-T005）。
- knip 清零（M7-T006）；增长报告（`docs/10`，M7-T007）；SQLite 策略（`docs/11`，M7-T008）；
  Bun 1.4 兼容 job（M7-T009）；Core 覆盖地板 95/90（M7-T010）。
- harness 增强：`providerOptions` 透传（M7-T011）、同 id tool 响应合并修复严格网关 400（M7-T012）、
  eval 词表锚定与期望集对齐（M7-T013/T014）。

## M6 — Extensions & Recovery UX

- Extension host 接缝（ADR-0013）：telemetry 只读观察、standing-orders fail-closed 命令扩展。
- 上下文确定性压缩（M5-T002 延伸）与恢复编排完善。

## M5 — Recovery & Compaction

- §17 崩溃矩阵六格逐格注入（M5-T004）；deterministic compaction（M5-T002）；
  brief 双层组装 fail closed（M5-T001）。

## M4 — Epistemic Layer

- 九个认识论事件 + reducer 法则（Goal/Observation/Hypothesis/Plan/Challenge/Verification，ADR-0012）；
  证伪作废、完成阻断；eval 轴落地（M4-T005）。

## M3 — Tools & Capability

- 工具执行状态机（INDETERMINATE/reconciliation，ADR-0006/0011）；
  capability 门 fail closed（ADR-0007）；write 工具（write_file/bash）。

## M2 — Agent Loop & Adapters

- contracts 事件词汇 + ports；core reducer/agent-loop/context；
  provider-openai（Chat Completions 流式）；tools-local read；
  store-sqlite EventStore；CLI run/sessions；testkit。

## M1 — Contracts & Store

- 契约骨架、SQLite migration/append/replay 底座。

## M0 — Bootstrap

- 工具链冻结（Bun 1.3.14 + mise + lefthook）、七包骨架、CI、
  AI 开发控制面（plan/guard/verify/accept/handoff）、架构符合性测试。
