# cli

`@praxis/cli` 当前实现行为。模块定位的唯一权威是 `docs/02-system-design.md` §4.6（composition root）；命令需求来自 `docs/03-project-plan.md` M2.5。

## 当前内容（M2-T005 起；M2-T006 增加真实模型源）

入口唯一 `src/index.ts`；依赖 `contracts / core / store-sqlite / provider-openai / tools-local`（架构允许集中不含 testkit——确定性 provider 由 CLI 自持）。进程入口是两行包装：`main(argv, io)` 可被测试直接驱动。

- **命令**（零依赖手写 argv 解析，`--flag value` 对）：
  - `run [--db P] [--session ID] [--input TEXT] [--root DIR] ( --script FILE | --model NAME [--api-key KEY] [--base-url URL] )`：三态合一——无 `--session` 创建会话（需 `--input`）；`--session + --input` 开新 turn；仅 `--session` 续跑 open turn（含崩溃恢复）。两个模型源互斥；`--model` 走 `@praxis/provider-openai`（key 回退 `OPENAI_API_KEY`，缺 key 拒绝启动；key 只进请求头，不进事件/输出）。退出码 0 完成 / 1 用法或运行错误 / 2 paused 或 cancelled（turn 保持 open，提示 resume 命令）。
  - `sessions [--db P]`：列出会话 id、状态、head seq（SQLite 元数据投影，事实以事件流为准）。
  - `help` / 未知命令：usage 到 stderr。
- **ScriptFileModelProvider**（`src/scripted-provider.ts`）：确定性 provider——JSON 脚本文件（数组的数组），每次 `complete()` 消费一个脚本；文件是非受信边界，逐事件经 `ModelEventSchema` 解析；脚本耗尽 fail loud。真实模型行为归 `@praxis/provider-openai`（见 `provider-openai.md`），CLI 只做组装。
- **流式输出**：`observingStore` 包装 SessionStore——每次成功 append 后把 durable 事件按 `[seq] Type detail` 打到 stdout；模型/工具事实边产生边流。流式 delta 不落库也不打印（不是 durable 事件）。
- **进程关切归 CLI**：真实随机 ID（`crypto.randomUUID` 品牌化）、墙钟 `Date.now()`、SIGINT→AbortController（协作取消：尝试记为 ModelRequestFailed，turn 保持可恢复）、store 句柄开闭。所有 durable 规则（循环、恢复、守卫）在 core——CLI 不含自己的 loop/recovery 逻辑。
- 默认值：db `./praxis.db`、root=当前工作目录、固定 system prompt。

## 测试

- `tests/cli/cli.bun.test.ts`（bun runner，经 `@praxis/cli` 传递依赖 bun:sqlite）：run 垂直全链路（read_file 往返 + 事件流断言）、崩溃后续跑（悬挂执行 → INDETERMINATE、单脚本证明历史零重执行、无新模型调用）、open turn 拒绝新 input、缺模型源 / 畸形脚本 / 未知命令 fail loud、sessions 空与列表、`--model` 与 `--script` 互斥、缺 key 拒绝、本地假 OpenAI 兼容端点（`Bun.serve`）跑通 `--model` read_file 竖切。门：`mise run test:cli`（quality-gates 规则 `cli-app`：apps/cli/** 要求 cli+integration+store）。
