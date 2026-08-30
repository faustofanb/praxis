# Threats & Limitations（v1 RC, M8-T005）

诚实的威胁与限制记录。每条链接其缓解证据或权威文档——**限制按限制陈述，不粉饰为控制**。

## 威胁与缓解

| 威胁 | 缓解（机器证据） |
| --- | --- |
| 模型操纵/污染会话状态 | 模型只能经 Commands 提案；durable facts 由 reducer 唯一裁决，context/brief 是派生投影而非可写存储（docs/02 §2/§12；property 套件钉死模型一致性） |
| 写操作失控（越权路径、危险命令） | capability 门 fail closed（workspace scope 逃逸直接 deny）；CLI 缺省拒绝写（durable ToolRejected，M8-T002/T003 证据）；write 工具原子写 + cwd 钉死 + 超时（docs/subsystems/tools-local.md） |
| API key 泄漏 | §18 禁锢：key 仅进 Authorization 头；wire body/durable 事件/模型消息全图深搜零泄漏（`tests/security/secret-confinement.security.test.ts`，M7-T002） |
| 失控循环 / 无限重试 | turn 16 步守卫 + 连续 3 次模型失败暂停（M8-T003 实录）；provider 逃逸法则——事件逃逸后禁重试，失败如实上抛（M7-T002，docs/02 §10） |
| UNKNOWN 被压制成失败/成功 | indeterminate ≠ failed 为 reducer 法则；完成阻断、reconciliation 编排由 fault/replay 套件钉死（§8.3/§17） |
| 崩溃后状态失真 | 六格崩溃矩阵逐格注入 + 跨进程持久性证据（M5-T004/M7-T002；docs/11） |

## 限制（v1 明确不做 / 尚不具备）

- **bash 无 OS 级沙箱**（docs/02 §9.3 如实声明）：v1 控制面 = capability 门 + cwd 钉死 + 超时 + 输出截断——不阻止 bash 自身逃逸出 root；不可信环境须配合外部沙箱部署。
- **单写者 per session**：无并发 agent 写同一会话；多 worker 只能经 Observation/Proposal 协作（docs/02 §16）。
- **无 Multi-Agent / Critic / Workflow DSL**：v1 非目标（docs/02 §1.1，LOCKED）。
- **SQLite 单文件本地库**：损坏的恢复策略 = 从文件系统备份整库还原；无在线修复/校验和/自动备份（docs/11）。
- **Provider 重试仅限逃逸前**：流事件一旦到达消费者即不可重放——中途断连表现为诚实失败而非自动恢复（设计取舍，docs/02 §10）。
- **上下文恒界（1+64 消息 / 32k token）**：长程依赖不靠上下文而靠 durable facts + brief 摘要——跨超长跨度的隐式状态检索不是 v1 能力（docs/10）。
- **Eval 证据为 n=1**：基线是证据不是基准；两时间点方差已如实记录（BASELINE.md），跨时间点结论（如 deepseek 系完成偏置）以复现为准。
- **模型纪律差异是真实的**：deepseek-v4-flash 完成偏置跨时间点复现——部署上应避免其无人监督自主宣告完成（runtime 会拦，代价是多轮刹车），或选 gpt-5.6-sol/luna 档（BASELINE.md）。
- **`--script` provider 每进程从头消费**：kill 后 resume 须提供剩余脚本（quickstart 已写明）。
- **每事件折叠成本 ~4.4× 增长**（10k turn 实测）：正确性无损，优化后置（docs/10、docs/subsystems/core.md）。

## 报告维护

新增威胁/限制：先落缓解证据（测试/文档），再在本文登记。本文与证据矛盾即漂移——以证据为准修本文。
