# tools-local

`@praxis/tools-local` 当前实现行为。模块定位的唯一权威是 `docs/02-system-design.md` §4.5；工具生命周期硬规则见 §8.2；capability 分层见 §9.3（本包是第 2 层）。

## 当前内容（M2-T003 起；写工具 M3-T003 起）

只依赖 `@praxis/contracts`；入口唯一 `src/index.ts`。工具集绑定到 workspace root：`localReadTools(root, options?)` 只读集，`localWriteTools(root, options?)` 写能力集（M3-T003 起）。

- **read_file**（`src/read-tools.ts`）：输入 `{path}`；UTF-8 文本读取，超出 `maxResultBytes`（默认 64 KiB）保头截断并附 `…[+N bytes truncated]` 标记，`truncatedBytes` 随结果记录。结果 JSON：`{path, content, truncatedBytes?}`。
- **list_dir**：输入 `{path}`；列出目录条目并按名字排序（确定性），kind 归并为 `file | dir | symlink | other`。
- **write_file**（`src/write-tools.ts`，M3-T003 起）：`reconcilable_write`，`requiredCapability fs.write`（scope 绑定 root）。输入 `{path, content}`；父目录必须存在（不隐式 mkdir）；同目录临时文件（`.praxis-tmp-<uuid>`）+ 原子 rename——读者只会看到旧内容或新内容，绝无半写。结果 `{path, bytes}`。执行失败（含 ENOENT/权限）= 效果确证未发生的 `failed`（rename 是最后一步且原子）；执行器中途崩溃由 Core 按 effect 类落 INDETERMINATE。
- **write_file reconcile**（ADR-0011；M3-T005 起认知矩阵对齐 contracts tool 端口——`failed` 必须是观察到的事实，绝不是推断）：读目标文件比对内容——内容一致 → `succeeded {path, verified: true, bytes}`（写入确已发生）；resolve 成功且目标缺失（ENOENT）/被目录占用（EISDIR）/内容不同 → `failed`"the write did not take effect"（**观察到**的未发生）；路径策略拒绝（词法逃逸/symlink 违规/root 消失）或其他不可读（如 EACCES）→ `indeterminate`"cannot verify"——策略拒绝不证明未发生：symlink 状态是外部可变状态，崩溃前后可能被改写，而 `failed` 是唯一能解锁重执行的结论（contracts tool port），绝不可由"拒绝查看"推断。只验证、零副作用：崩溃遗留的 `.praxis-tmp-*` 不清理（清理由恢复编排/宿主决定），验证不改变 mtime。
- **bash**（M3-T003 起）：`non_idempotent_write`，`requiredCapability shell.exec`。输入 `{command, timeoutMs?}`（默认 30s，上限 120s）；cwd 钉在 realpath(root)；硬超时 SIGKILL；stdout/stderr 各自字节截断（默认 64 KiB，保头 + 截断标记 + `stdoutTruncatedBytes/stderrTruncatedBytes` 计数，采集期即封顶防内存耗尽）。结果映射：exit 0 → `succeeded {exitCode, stdout, stderr, …truncated}`；完成的非零退出 → `failed "command exited with code N"`（附 stderr 尾部 ≤512 字节）；超时/turn 中止/被信号杀死 → `indeterminate "effects unknown"`——绝不把未知强转为失败。以 `exit` 而非 `close` 收口（被杀命令的孤儿子进程可能占住管道）。无 reconcile（non_idempotent_write 无可验证事实）。
- **v1 诚实边界**（docs/02 §9.3）：bash 不做路径限制、不声称 OS sandbox——控制权在第 1 层 shell.exec capability；write_file/read_file 的路径限制是词法 + realpath 双重检查（`src/path-policy.ts`，M3-T003 起独立模块并支持"目标尚不存在"的写入路径：realpath 解析最深存在的祖先后按词法重接缺失尾段）。
- **参数说明**（M2-T004 起）：所有工具携带静态 `parametersJson`（与 `inputSchema` 同形），经 ContextBuilder/ModelRequest 原样透传；Core 只校验合法 JSON。
- 不存在/类型不符 → `failed`（read_only 与已证未发生的 write 可安全快速失败）；本地读不产生 INDETERMINATE。

## 测试

- 安全：`tests/security/tools-local.security.test.ts`（读：相对/绝对路径逃逸、symlink 逃逸、越界 list_dir）；`tests/security/tools-local-write.security.test.ts`（M3-T003：写 traversal/绝对路径/symlink 文件/symlink 目录逃逸全部拒绝且 root 外零写入；M3-T005 起 reconcile 逃逸路径 → 诚实 indeterminate——拒绝查看≠确证未发生；bash cwd/诚实边界）。门：`mise run test:security`。
- 安全：`tests/security/bypass-composition.security.test.ts`（M3-T005 组合层对抗：授权齐全 + 逃逸路径经真实 runtime → 可证 ToolFailed 且 root 外零效果；崩溃后 symlink 改指 → reconcile indeterminate、failed-解锁-重执行攻击被阻断；伪造 INDETERMINATE 流携带逃逸 recorded input → 不落任何定论；symlink 别名 root 不能满足词法 capability scope；bash 无 shell.exec 在 ToolStarted 前拒绝且无文件产生）。
- 单元：`tests/tools-local-write.test.ts`（M3-T003：原子写与字节统计、覆盖写无临时残留、拒绝写 root/目录、reconcile 内容比对三态且 mtime 不变、bash cwd/退出码/stderr 尾部/超时 INDETERMINATE/输出截断、requiredCapability 声明与注册校验通过）。
- 集成：`tests/integration/tool-runtime.integration.test.ts`（read_file 经执行器成为 durable 事实并进入下一次 context）；`tests/integration/agent-loop-recovery.integration.test.ts`（read_file 经 runTurn 全链路 + 崩溃恢复不重执行）；`tests/integration/write-tools.integration.test.ts`（M3-T003：授权写/bash 经 capabilityAuthorizer 执行落事实、未授权在 ToolStarted 前拒绝、rename 后崩溃 → INDETERMINATE → reconcile → SUCCEEDED 且 reconciliationCount=1）。门：`mise run test:integration`。
