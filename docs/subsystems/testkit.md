# testkit

`@praxis/testkit` 当前实现行为。模块定位与职责清单的唯一权威是 `docs/02-system-design.md` §4.6；模型契约决策见 `docs/decisions/ADR-0010-model-provider-contract-v1.md`。

## 当前内容（M2-T001 起）

不进入生产依赖；只被测试与 dogfood 场景引用。入口唯一：`src/index.ts`。依赖 `@praxis/contracts`（`@praxis/core` 为既定的 workspace 依赖占位，尚未使用）。

- **ScriptedModelProvider**（`src/scripted-model.ts`）：实现 `ModelProvider` port 的确定性模型。
  - 构造时给一组 script（每个是 `ScriptItem[]`），每次 `complete()` 依次消费一个并按序流式产出事件；无时钟、无随机、无 I/O。
  - `ScriptItem`：`{ kind: "event", event: ModelEvent }` 或 `{ kind: "waitForAbort" }`（挂起直至 signal abort，用于确定性取消注入）。
  - 取消语义与 port 合同一致：调用前已 abort → 空流不抛；waitForAbort 处 abort → 静默结束，无 completed；事件之间 abort → 停在已产出的前缀。
  - `.requests` 记录每次被服务的请求（含已取消的），供断言 loop 实际发出了什么。
  - 超出 script 数量再消费 → 抛出显式 invariant 错误（`script exhausted`），让失控 loop 在测试里响亮失败。

## 测试

- 单元：`tests/testkit-scripted-model.test.ts`（脚本顺序与请求记录、三种取消路径、providerError 注入、script 耗尽报错）。
- in-memory EventStore / FakeTool / fixture builder 等其余 §4.6 职责按里程碑任务逐步落地。
