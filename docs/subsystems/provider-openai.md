# provider-openai

`@praxis/provider-openai` 当前实现行为。Port 契约权威见 `docs/02-system-design.md` §10 与 ADR-0010；架构边界见 `.praxis/architecture.yaml`（仅依赖 contracts）。

## 当前内容（M2-T006 起）

入口唯一：`src/index.ts`，导出 `OpenAIChatProvider`（实现 contracts 的 `ModelProvider` port）、`OpenAIChatProviderOptions`、`FetchLike`。**零第三方 SDK**：直接用运行时全局 `fetch` 对话 OpenAI 兼容的 Chat Completions 端点（`POST {baseUrl}/chat/completions`，SSE 流式）。zod 仅用于 wire 边界校验。

### Wire 协议：Chat Completions（而非 Responses API）

docs/02 §4.4 原文写的是 Responses API，本任务落地时更正为 Chat Completions，理由：

- 任务要求 **OpenAI 兼容**生态：vLLM、Ollama、OpenRouter、DeepSeek、Moonshot 等兼容端点普遍只实现 chat completions；Responses API 在兼容生态中覆盖稀疏；
- `finish_reason`（stop/tool_calls/length）与 v1 `ModelFinishReason` 一一映射，无需近似；
- wire 格式经 openai-node 类型（由官方 OpenAPI spec 生成）核对。

Responses adapter 未来可在同一 Port 后新增（ADR-0010 revisit trigger 已预留），无需动 contracts/core。

### 请求映射（`src/chat-provider.ts`）

- 消息：system/user → `{role, content}`；assistant → `{role, tool_calls:[{id,type:"function",function:{name,arguments}}]}`（`argumentsJson` 原样传字符串）；tool 结果 → `{role:"tool", tool_call_id, content}`。
- 工具：`parametersJson` 由 adapter `JSON.parse` 为 wire 对象（Core 从不解析，见 ADR-0010）；非法 JSON 在发请求前抛出（自身工具定义缺陷，响亮失败）。
- `maxOutputTokens` → `max_completion_tokens`；`providerOptions` 浅合并为最后 escape hatch，但 `stream`/`stream_options` 不可被覆盖——Port 只提供流式形态。
- 固定附加：`stream: true`、`stream_options: {include_usage: true}`（usage 在 `[DONE]` 前的空 choices chunk 中到达）。
- 鉴权：`Authorization: Bearer <apiKey>`；key 只进请求头，不进事件/日志/上下文。

### 事件映射

- `delta.content` → `textDelta`；
- `delta.tool_calls[]` 按 wire `index` 累积：首片段（必带 `id`+`function.name`，否则判 malformed）→ `toolCallStart`，后续 `function.arguments` 片段 → `toolCallDelta`；
- chat completions 没有单工具调用结束标记：`toolCallEnd`（按到达顺序）、`usage`、`completed` 在流收敛后统一发出，`completed` 保持终态事件语义；
- `finish_reason`：stop→stop、tool_calls→toolCalls、length→length；**其余值（content_filter、function_call、未知）不近似映射**，如实上报 `providerError {kind:"unknown", retryable:false}`。

### 失败分类与 adapter 自有重试（ADR-0010）

| 来源 | kind | retryable |
| --- | --- | --- |
| HTTP 401/403 | auth | 否 |
| HTTP 429 | rateLimit | 是 |
| HTTP 5xx | overloaded | 是 |
| HTTP 其他 4xx | invalidRequest | 否 |
| fetch 抛错（非 abort） | network | 是 |
| 读超时（非调用方取消的 abort） | timeout | 是 |
| 坏 JSON / wire schema 不符 / 缺 finish_reason | unknown | 否 |

- retryable 失败由 adapter 重试（默认 `maxRetries: 2`，退避 `initialRetryDelayMs * 2^attempt`，默认 500ms 起），重试期间**调用方 abort 优先**（静默结束）；
- **逃逸法则（M7-T002，docs/02 §10）**：retry 只发生在本次尝试尚未向消费者转发任何事件之前；一旦有任何事件（textDelta/toolCallStart/…）逃逸，retryable 失败也如实上抛为一次终态 `providerError`——重放流会让消费者把两次尝试的事件拼进同一逻辑响应（durable text 翻倍、半构建 tool call 泄漏为幽灵调用，均为 P0 状态失真；`tests/fault/provider-adapter.fault.test.ts` 钉死）；
- 非 retryable 直接上抛为一次终态 `providerError` 事件，消费者永远不会被 throw；
- `fetch`/`sleep` 可注入（`FetchLike`），全部测试确定性离线。

### 取消与超时

- 调用方 signal abort → 流静默结束（无 completed、无 providerError、不抛错），且不重试——port 契约的取消语义；
- 每次尝试挂 `AbortSignal.any([调用方signal, AbortSignal.timeout(timeoutMs)])`（默认 120s）：调用方先取消 → 静默；只有超时先触发 → `providerError {kind:"timeout", retryable:true}`。

## CLI 接线

`apps/cli` 组合根：`praxis run --model NAME [--api-key KEY] [--base-url URL]`，key 回退 `OPENAI_API_KEY` 环境变量；与 `--script` 互斥。`modelId` 即 `--model` 值（记入 `ModelRequestStarted` 事实）。

## Smoke（非阻塞，不入 check 链）

`mise run smoke:openai`（`scripts/smoke/openai-smoke.ts`）：无 `OPENAI_API_KEY` 时打印 skip 并 exit 0；有 key 时发一次真实请求（默认 `gpt-4o-mini`，`PRAXIS_SMOKE_MODEL`/`PRAXIS_SMOKE_BASE_URL` 可覆盖），断言收到终态 completed 且有文本。M2 里程碑的 real_model_eval 证据来源。

## 测试与门

- 单元（vitest/Node）：`tests/provider-openai/chat-provider.test.ts`，16 用例——请求体映射、事件顺序、双工具并行、finish_reason 三值+越界、HTTP 状态分类、429 重试一次、5xx 退避耗尽、network 重试、超时、预取消/中流取消静默、malformed SSE、缺 finish_reason、构造参数校验。入 `test:unit` 门。
- 故障（vitest/Node）：`tests/fault/provider-adapter.fault.test.ts`（M7-T002：中途断连**逃逸后**不再重试——已交付 textDelta / 半构建 tool call 后的 mid-body reset 只上抛一次终态 providerError、fetch 恰一次；退避睡眠中 abort 静默收口且无下一次尝试；429→401 降级即停；真实 runTurn 端到端——每请求恰一次 fetch、三次后 core 连败守卫暂停 turn、零 `ModelResponseCompleted`、partial 文本从不进入任何 durable payload）。入 `test:fault` 门。
- 安全（vitest/Node）：`tests/security/secret-confinement.security.test.ts`（M7-T002：§18 密钥禁锢——key 只出现在 Authorization 头（对照断言证明 key 真实在途），wire body、整段 durable 事件流、模型消息（模型上下文的 wire 投影）全图深搜零命中）。入 `test:security` 门。
- CLI 端到端（Bun）：`tests/cli/cli.bun.test.ts` 新增 3 例——`--model`+`--script` 互斥、缺 key 拒绝、本地 `Bun.serve` 假端点跑通 read_file 竖切（含 Bearer 校验与两次模型请求断言）。入 `test:cli` 门。
