# Praxis CLI Quickstart

从零到跑通 read / write / approval / resume 的最短路径。所有命令可逐字复制执行
（示例输出摘自 2026-08-30 的实际运行；durable 事件逐条流式打印到 stdout）。

前置：[mise](https://mise.jdx.dev)（`mise install` 会装好锁定的 Bun 1.3.14）。

```bash
git clone <repo> praxis && cd praxis
mise install && mise run install   # frozen lockfile
```

## 1. 确定性示例会话（--script，零网络）

准备脚本文件（`scripts/read-note.json`）——每次 `complete()` 消费一个脚本，
脚本内是模型事件流：

```json
[
  [
    { "type": "toolCallStart", "toolCallId": "call-1", "name": "read_file" },
    { "type": "toolCallDelta", "toolCallId": "call-1", "argumentsDelta": "{\"path\":\"note.txt\"}" },
    { "type": "toolCallEnd", "toolCallId": "call-1" },
    { "type": "completed", "finishReason": "toolCalls" }
  ],
  [
    { "type": "textDelta", "text": "the note says: cli note body" },
    { "type": "completed", "finishReason": "stop" }
  ]
]
```

准备工作区并运行：

```bash
mkdir -p demo && cd demo && echo "cli note body" > note.txt
bun ../apps/cli/src/index.ts run --db demo.db --root . --script ../scripts/read-note.json --input "read the note"
```

stdout 流（节选）：

```text
[  1] SessionCreated
[  2] TurnStarted turn 3a… input=read the note
[  3] ModelRequestStarted scripted-file
[  4] ModelResponseCompleted 1 tool call(s)
[  5] ToolProposed read_file (read_only)
[  6] ToolAuthorized tool-exec-…
[  7] ToolStarted tool-exec-…
[  8] ToolSucceeded tool-exec-… — {"path":"note.txt","content":"cli note body\n"}
[  9] ModelRequestStarted scripted-file
[ 10] ModelResponseCompleted 0 tool call(s) the note says: cli note body
[ 11] TurnCompleted turn 3a…
the note says: cli note body
```

## 2. Approval：write 任务缺省拒绝，授权后落盘

不加 `--allow-write` 直接让模型写文件——capability 门 **fail closed**，拒绝是
durable 事实：

```bash
# 脚本把 read_file 换成 write_file（arguments: {"path":"out.txt","content":"hi"}）
bun ../apps/cli/src/index.ts run --db demo.db --root . --script ../scripts/write-note.json --input "write out.txt"
# stdout 会包含：
# [  5] ToolProposed write_file (reconcilable_write)
# [  6] ToolRejected tool-exec-… — capability fs.write requires human approval; …
# out.txt 不会出现。
```

显式授权后同一任务落盘：

```bash
bun ../apps/cli/src/index.ts run --db demo.db --root . --allow-write --script ../scripts/write-note.json --input "write out.txt"
# [  6] ToolAuthorized … / [  8] ToolSucceeded … — {"path":"out.txt","bytes":2} —— out.txt 出现在 --root 下
```

`--allow-write`（fs.write）与 `--allow-bash`（shell.exec）相互独立、都只作用于
`--root` 工作区、仅本次调用有效。root 之外的 scope 直接 deny（docs/02 §9）。

## 3. 真实模型（--model）

```bash
export OPENAI_API_KEY=sk-…   # 或 --api-key；OpenAI 兼容端点可用 --base-url
bun ../apps/cli/src/index.ts run --db demo.db --root . --model deepseek-v4-flash --input "read note.txt and summarize it"
```

## 4. 崩溃 / 中断后续跑（resume）与会话检视

turn 进行中 Ctrl-C（或进程被杀）：已落档的执行保持诚实状态，turn 保持 open，
进程以退出码 2 提示 resume 命令。恢复 = 只加 `--session`（不带 `--input`）：

```bash
bun ../apps/cli/src/index.ts run --db demo.db --root . --session <session-id>   # 续跑 open turn（含恢复编排）
bun ../apps/cli/src/index.ts sessions --db demo.db                              # 会话 id / 状态 / head seq
```

恢复编排（docs/02 §17）自动处理悬挂执行：未决事实如实落档（INDETERMINATE →
reconcile），历史工具绝不重执行。

## 退出码

| 码 | 含义 |
| --- | --- |
| 0 | turn 完成 / sessions 列出 |
| 1 | 用法或运行错误（fail loud，如缺模型源、畸形脚本、缺 API key） |
| 2 | paused 或 cancelled（turn 保持 open，按提示 resume） |

深入：架构全景 `docs/12-architecture-current-state.md`；CLI 实现细节
`docs/subsystems/cli.md`；恢复法则 `docs/02` §17；损坏/恢复策略 `docs/11`。
