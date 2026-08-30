# SQLite Corruption & Recovery Policy（M7-T008）

本文件回答：**SQLite 事件库损坏时，系统做什么、操作员能做什么、v1 明确不做什么。**
分层陈述，每条规范性语句追溯到已钉死的测试或法则——本文不复制任何法则表
（一条事实一个家）：

- 运行时恢复法则（9 步编排 + 崩溃矩阵 + 绝对禁止清单）：`docs/02-system-design.md` §17；
- 单写者法则：docs/02 §16；
- store 当前行为：`docs/subsystems/store-sqlite.md`；
- 引擎决策（bun:sqlite、无 ORM）：ADR-0004。

## 预防层——损坏面按构造收窄

| 机制 | 出处 | 收窄的损坏面 |
| --- | --- | --- |
| WAL journal mode | `db.ts` `journal_mode = WAL` | torn write 容忍；崩溃后 WAL 自动回放 |
| append-only 公共面 | store 仅 `append/readStream/listSessions/close`，无事件 UPDATE/DELETE 路径 | 运行内代码无法改写已落盘事实；行级损坏只能来自进程外因素（磁盘、外部工具） |
| 单写者 per session | docs/02 §16 | 无并发写交错损坏；SQLite 多 session 并发、同 session seq 串行 |
| 单事务 append | 乐观 head 检查 + 无间隙 seq + 元数据同事务更新；冲突/间隙原子回滚 | 半途批次不可见；不一致前缀不可落盘 |
| 显式单调 migration | `schema_migrations` 版本分歧（降级/未知版本）fail-closed | 异构 schema 打开即拒绝，不带病运行 |

## 检测层——持久化字节是不可信边界

- `readStream` 对**每行**经 `SessionEventUnionSchema.parse` 重校验：坏 JSON、
  未知事件类型、不合 schema 的 payload 在**读取时**即抛错——不静默跳过、
  不猜测缺失事件（测试钉死：`tests/store/store-sqlite.bun.test.ts`
  "corrupted actor JSON fails validation on read"）。
- migration 版本分歧在**打开时**失败（同上表）。
- 原则：检测即 fail closed。损坏的库不会产生半可信读——要么完整校验通过，
  要么显式异常。

## 恢复层——两级分治

### 运行时级（dangling 结构、崩溃后恢复）

**法则全权在 docs/02 §17**：九步恢复编排、六格崩溃矩阵
（`tests/fault/crash-matrix.fault.test.ts` 逐格注入 + `tests/store/crash-recovery.bun.test.ts`
真实 SQLite 跨进程持久性证据）、恢复四法则（前缀合法折叠/恢复事实诚实/
execute 计数不增/恢复幂等）、绝对禁止清单。本文件不复制——运行时恢复与
文件损坏无关：**只要前缀字节完整，恢复就是纯 reducer 重放 + dangling 处理，
SQLite 层无需特殊动作。**

### 文件级（page corruption、torn write、磁盘错误）

v1 立场（规范性，属 v1 限制声明）：

1. **runtime 不修复、不裁剪、不绕过**。事件流是唯一事实源（ADR-0003/0004 的
   直接推论）：任何"修一半"的库都会产生更危险的状态失真——被 runtime 采信的
   伪造前缀比不可用的库更糟。
2. **操作员动作 = 从文件系统备份恢复整个库文件**（含 WAL 伴生文件），随后
   正常打开。恢复后的行为已有测试背书：重开库 migration 幂等 + 前缀逐字节
   回放一致（store 套件）、跨进程 dangling 恢复恰好一次 side effect
   （crash-recovery 套件）。
3. **损坏报告即真**：readStream 的校验异常应原样上报操作员，不得在应用层
   吞掉重试。

v1 明确**不提供**（后置，非疏漏）：在线修复工具、逐行校验和列、自动备份
工具、部分流恢复。触发重估的证据：真实损坏事件、多用户/多机部署需求、
或 §16 单写者边界被扩展。

## 测试证据索引

| 层 | 声明 | 钉死处 |
| --- | --- | --- |
| 检测 | 损坏行读取即抛，不跳过 | `tests/store/store-sqlite.bun.test.ts` |
| 预防 | 冲突/间隙原子回滚、migration 幂等+重放一致 | 同上 |
| 运行时恢复 | 崩溃矩阵全格 + 人工解锁环 | `tests/fault/crash-matrix.fault.test.ts` |
| 文件级前提 | 跨进程前缀逐字节回放 + 恰好一次 side effect | `tests/store/crash-recovery.bun.test.ts` |

## 维护

新增预防机制、检测路径或恢复能力时：先落测试（机器家），再在对应层追加一行
并链接。本文出现与测试/法则矛盾的声明即漂移——以测试为准，修本文。
