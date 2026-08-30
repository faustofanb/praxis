# extension-standing-orders

`@praxis/extension-standing-orders` 当前实现行为。Extension 接缝权威是 `docs/02-system-design.md` §19 与 ADR-0013；context 组合法则是 §14（M5-T001）。本包是接缝的第二个**产品级消费者**，也是 §19 失败策略表 **policy 格**（`fail_closed`）的第一个落地实例——M6 场景验收 "extension adds tool/context/event observer without core edit" 的 context + tool 半边：`packages/core` 与 `packages/contracts` 零改动（M6-T003 合同以 forbidden_paths 强制）。

## 当前内容（M6-T003 起）

只依赖 `@praxis/contracts`。入口唯一 `src/index.ts`。

- **`createStandingOrdersExtension(options?)`**（`src/standing-orders.ts`）→ `PraxisExtension`，name `standing-orders`，`failurePolicy: "fail_closed"`（docs/02 §19：policy/security 扩展 fail closed——standing orders 是承重的 operator 策略，hook 崩溃时 turn 必须诚实崩进 §17 既有恢复，绝不静默丢掉 operator 约束；该崩溃法已由 M6-T001 fault 测试钉死，本包只声明策略）。
  - **`contributeContext`**：配置了 `instructions` 时返回单一片段（host 盖 `source`、按 M5-T001 上限法则渲染为 `## Extension: standing-orders` 节）；未配置返回 `undefined`——**零配置字节恒等**（已注册但未配置的扩展不花一个 prompt 字节）。
  - **`beforeTool`**：提案工具名在 `deniedTools` 内 → `{decision: "deny", reason: "standing orders forbid tool '<name>'"}`（deny-only 生命周期 seam：只做限制，组合在 capability authorizer 批准之后）；否则 `undefined`。
  - 只实现这两个 hook——无观察 hook（那是 `extension-telemetry` 的职责），也永远无法表达 allow。
- **构造即校验**（fail-closed 哲学：配置错误在构造时大声抛 `InvalidStandingOrdersError`，绝不在 turn 中途才发现）：空白 `instructions`、空白/非字符串 `deniedTools` 条目直接拒绝。
- **策略输入冻结**：工厂复制并冻结 `deniedTools`——调用方事后改数组不改变已注册扩展执行的政策。

## 测试

- 单元/集成：`tests/extensions/standing-orders.test.ts`（M6-T003：fail_closed 声明 + `validatePraxisExtension` 通过 + instructions 渲染于 base prompt 之后；零配置下 request/stream 与裸跑字节恒等；deny → ToolRejected 引用扩展名、无 ToolStarted/ToolSucceeded、turn 照常完成；与 `@praxis/extension-telemetry` 同 host 组合——deny 被计为 REJECTED（M6-T004 前置）；构造校验拒绝坏配置；策略输入冻结（调用方 push 新名字后 beforeTool 仍不拦截）；unload 后两个贡献立即停止）。门：`mise run test`。
