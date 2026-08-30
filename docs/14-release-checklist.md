# v1 Release Checklist

> v1 发布前置检查单。状态标注 @ HEAD（2026-08-30，M8-T005）；release-day 动作
> （打 tag、push、发布）是人工动作，保持未勾。法则/设计权威见
> `docs/02-system-design.md`；符合性见 `docs/07-architecture-conformance.md`。

## 1. 机器门

- [x] `mise run check:all` 全绿（format/lint/typecheck/test/knip/test:architecture + coverage）
- [x] Core 覆盖地板生效：`packages/core/src/**` statements ≥95 / branches ≥90（实测 97.58/94.31，M7-T010）
- [x] knip 零发现（M7-T006）
- [x] 机器门全量复证：unit 502-508 / integration 32-34 / property 23 / replay 19 / fault 27 / security 40 / store 13 / cli 14 / build（各任务 verify 记录 + M7 验收文档 @ `da4c80c`）

## 2. 场景与故障验收

- [x] 干净克隆场景验收：clean install → read → write(deny) → write(approval) → resume（M8-T003，克隆 HEAD `1df3b31`）
- [x] kill → resume → finish（SIGINT exit 2 → turn open → 剩余脚本续跑 → TurnCompleted）
- [x] 失败注入负向证明：架构违规 / 精确锁违规均使门变红（M8-T003）
- [x] §17 崩溃矩阵六格逐格注入 + 人工解锁环（M5-T004，`tests/fault/crash-matrix.fault.test.ts`）

## 3. 发布基线

- [x] 真实模型 eval：冻结矩阵 v3 于 RC HEAD 五配置重跑（M8-T004，10 份 scorecard 存档，`evals/development-models/BASELINE.md` "v1 release baseline"）
- [x] 模型结论：gpt-5.6-sol / gpt-5.6-luna 7/8 稳定并列第一；deepseek-v4-flash 完成偏置跨时间点复现（不宜无人监督自主）——记录于 BASELINE.md 与 threat/limitation 文档
- [x] 性能/增长基线：10k turn soak（M7-T003）+ 增长模型报告（`docs/10`）

## 4. 维护与合规

- [x] 依赖清单 + 漂移守卫：11 个外部直接依赖五事实表、许可允许清单（M7-T004，`docs/09`）
- [x] Bun 1.4 兼容证据（非门禁 job，M7-T009；主工具链仍锁定 1.3.14）
- [x] SQLite 损坏/恢复策略（`docs/11`）+ 内存/上下文增长报告（`docs/10`）
- [x] 文档集齐备：as-built 地图（`docs/12`）、CLI quickstart（`docs/13`）、子系统文档 ×10

## 5. v1 非目标冻结

- [x] **LOCKED for v1**：`docs/02-system-design.md` §1.1 所列九项非目标
  （无 Multi-Agent 调度、无实时矛盾分类器、无 Critic/Judge Agent、无云端
  App Server/IDE 协议、无 Workflow DSL、不自动修改宪法/Policy、无企业级分布
  式数据库、无 exactly-once 副作用承诺、无长期自治生产运维）在 v1 全部不实现；
  违反任一项即架构变更，须走 ADR（docs/07 §4）。

## 6. Release-day（人工，保持未勾）

- [ ] 复核本清单 + `docs/15-threats-and-limitations.md`
- [ ] Human demo（`docs/acceptance/M8.md` Human Demo 节）+ Exit Decision 签核
- [ ] git tag（v1 RC）+ push——**人工动作**
