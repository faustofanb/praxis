# Memory & Context Growth Report（M7-T007）

本报告回答一个问题：**Praxis 会话长时间运行时，什么在增长、什么不增长、以什么速率增长。**
它是对已钉死事实的解释与汇总——每个数字的权威家在别处，本文只引用并链接
（一条事实一个家）：

- 机器证据家：`tests/soak/turn-soak.test.ts`（M7-T003，unit 门内每次 verify 复跑）；
- 预算法与压缩法则家：`docs/02-system-design.md` §12.3；
- 预算常量家：`packages/core/src/context/budget.ts`（`DEFAULT_CONTEXT_BUDGET`）；
- 折叠成本特征的子系统记录：`docs/subsystems/core.md` Soak 条目。

## 内存模型：三层存储，三种增长

| 层 | 是什么 | 界 | 增长律 |
| --- | --- | --- | --- |
| **Event store** | append-only 事件流（SQLite 单行/事件） | 无界——设计如此：全保真历史，compaction 永不删除事件（§12.3） | 线性于落档事实 |
| **Derived state**（`foldSessionEvents`） | reducer 投影：turn 注册表、工具执行快照、observations/hypotheses/plans/challenges/verifications | 无硬上限——投影必然至少存下全部活跃结构 | 恰好线性于落档事实（10k turn 实测逐一相等） |
| **Working context**（`buildContext`） | 发给模型的每步重建投影：system（含 brief）+ 近窗消息 | **恒界**（六个 hard cap） | 与会话长度无关 |

关键推论：模型请求的体量与成本**不随会话变长而增长**；增长全部发生在
store（按设计保留）与派生态（线性、廉价）里。

## Working context：恒界由六个 cap 保证

`DEFAULT_CONTEXT_BUDGET`（budget.ts:27-34）：

| cap | 值 | 作用 |
| --- | --- | --- |
| `maxRecentMessages` | 64 | 近窗消息数（+1 system） |
| `maxEstimatedTokens` | 32 × 1024 | 组合请求估计 token，超限 fail closed |
| `maxFragmentBytes` | 16 KiB | 单 system 片段字节界 |
| `maxToolResultBytes` | 8 KiB | 单工具结果截断界 |
| `maxActiveObservations` | 8 | brief 观测条数（最新优先） |
| `maxActiveHypotheses` | 8 | brief 活跃假设条数 |

丢弃不无声：滑出窗口的消息触发**确定性压缩**（M5-T002）——system 片段末尾一行
按角色计数的诚实 recap；同输入同 budget 恒渲染同一 recap，零丢弃时与无压缩
投影逐字节一致。brief 双层组装（M5-T001）：不可压缩层逐行硬界、永不因字节压力
被逐出；可压缩层整节让位并附 `…[+K omitted]` 计数；放不下即
`ContextBudgetExceededError`（fail closed），绝不静默丢治理状态。

## 实测：10,000 turn 全词汇表合成会话

Soak（M7-T003）以零 RNG 确定性生成器产生 59,227 事件，在 2k/4k/6k/8k/10k
五个 turn 边界检查点断言（全部结构断言由 closed-form 计数公式钉死，公式家在
soak 测试内，此处不复制）：

- **context 恒界**：每检查点恰好 1+64=65 条消息、估计 token ≤32k、
  `dropped + retained === 历史长度` 精确对账——10k turn 的会话与 10 turn 的会话
  请求体量相同。
- **注册表恰好线性**：toolExecutions 3600、observations 1428、hypotheses 909、
  plans 769、challenges 588、verifications 434（10k 处）——每个注册表与该检查点
  落档事实数逐一相等，任何超线性泄漏都会立刻失败。
- **折叠合法性**：每检查点 headSeq 连续、ACTIVE、无悬挂结构；任意前缀可重放。

## 折叠成本：线性偏置的已知特征

派生态注册表逐事件**不可变 Map 拷贝**（`upsertToolExecution`），使每事件折叠成本
随规模缓增：2k→10k 实测 **~4.4×**（首测 55ms@2k → 1025ms@10k；重复运行绝对值
浮动 ~2×，比率稳定）。这是正确性无损的已知扩展性特征：

- soak 以 **tripwire ≤10×** 钉死（真二次方在 5× 数据量下应为 ~25×——4.4× 远离）；
- 10k turn 全量重折叠 ~1.0s——恢复/重放路径的量级参考；
- 候选优化（原位注册表或结构共享 Map）已记录于 `docs/subsystems/core.md`，
  属性于后续任务，本报告不改判其优先级。

## 运营含义

1. **会话不需要因长度重置**：context 恒界 ⇒ 长会话每步请求成本平稳；
2. **恢复成本线性**：崩溃后全量重放 10k turn ~1.0s（增量折叠更低，见
   store/agent-loop 恢复编排）；
3. **存储线性**：事件数即 SQLite 行数（事实家：`docs/subsystems/store-sqlite.md`）；
4. **容量规划只看两件事**：落档事实速率（store 行数、派生态大小）与
   `DEFAULT_CONTEXT_BUDGET` 之外的 provider 真实 token 计费——后者是模型侧
   观察值，不在本仓库钉死范围。

## 报告的维护

新增增长相关测量（新 cap、新注册表、新扩展性特征）时：先入 soak 测试（机器家），
再在本文引用。本文出现与 soak/预算常量矛盾的数字即漂移——以测试为准，修报告。
