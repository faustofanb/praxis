# extension-telemetry

`@praxis/extension-telemetry` 当前实现行为。Extension 接缝的权威是 `docs/02-system-design.md` §19 与 ADR-0013；redaction 法则在 §20（telemetry 永不携带秘密/完整敏感 Tool output）。本包是接缝的第一个**产品级消费者**：M6 场景验收 "extension adds tool/context/event observer without core edit" 的 telemetry 半边——`packages/core` 与 `packages/contracts` 零改动（M6-T002 合同以 forbidden_paths 强制）。

## 当前内容（M6-T002 起）

只依赖 `@praxis/contracts`（扩展是应用持有的值，实现 contracts 接口；不依赖 core——host 由应用注入）。入口唯一 `src/index.ts`。

- **`createTelemetryObserver(options?)` → `{ extension, snapshot() }`**（`src/telemetry.ts`）：
  - `extension`：name `telemetry-observer`，`failurePolicy: "isolate"`（docs/02 §19：telemetry 默认不阻断——sink 抛错由 host 的 isolate 策略吞掉，本包**故意不 catch**，骑的就是这条法）。
  - 实现 8 个 hook 中的 6 个观察 hook：`onTurnStart`/`onTurnEnd`（turn 计数、outcome 直方图、时长）、`beforeModel`/`afterModel`（请求数、结果种类直方图、toolCalls 数、时延）、`afterTool`（per 工具名 per 终态计数，含 REJECTED）、`onEvent`（per 事件类型直方图 + 总数）。
  - **故意不实现** `contributeContext`（观察型扩展零 prompt 字节）与 `beforeTool`（否决路径属于 policy 扩展；telemetry 无意见）。
  - 状态全在闭包（AGENTS.md 无模块级可变状态）；时钟可注入（`options.now`，默认 `Date.now`）保证确定性；`options.sink` 每条观察记录回调一次（应用接线的唯一集成点；默认仅内存快照）。
- **Redaction 是结构性的**：`TelemetrySnapshot` 的字段只有计数、时长、outcome/status 枚举、工具名、事件类型名——**没有任何字段能装下** tool 参数、tool output、model 文本或 provider payload，hook 写错也无法泄漏（由标记测试钉死：序列化快照不含 payload 标记）。
- `snapshot()` 返回深度冻结的时间点拷贝，unload 后仍可读、计数不再增长。

## 测试

- 单元：`tests/extensions/telemetry.test.ts`（M6-T002：全回合直方图与折叠流**精确相等**（非 ≥）；redaction 标记（tool output/model 文本/turn input/参数路径均不出现）；注入时钟确定性（两次运行快照相等、时延/时长精确值）；providerError 计入结果直方图且 turn 照常完成；每条记录都抛错的 sink 不破坏 turn 且计数完整；另一扩展 deny → REJECTED 计数（telemetry 不在否决路径上）；unload 后计数冻结、快照可读且冻结）。门：`mise run test`（unit 面）。
