# tools-local

`@praxis/tools-local` 当前实现行为。模块定位的唯一权威是 `docs/02-system-design.md` §4.5；工具生命周期硬规则见 §8.2。

## 当前内容（M2-T003 起）

只依赖 `@praxis/contracts`；入口唯一 `src/index.ts`。v1 只提供绑定到 workspace root 的只读工具，`localReadTools(root, options?)` 返回工具集。

- **read_file**（`src/read-tools.ts`）：输入 `{path}`；UTF-8 文本读取，超出 `maxResultBytes`（默认 64 KiB）保头截断并附 `…[+N bytes truncated]` 标记，`truncatedBytes` 随结果记录。结果 JSON：`{path, content, truncatedBytes?}`。
- **list_dir**：输入 `{path}`；列出目录条目并按名字排序（确定性），kind 归并为 `file | dir | symlink | other`。
- **路径约束**：`resolveWithinRoot` 先词法检查（resolve 后必须仍在 root 之下），再 realpath 双重检查（symlink 不能逃逸）。任何逃逸以 `failed`（"escapes the workspace root"）结束，绝不读外部。
- 不存在/类型不符 → `failed`（read_only 可安全快速失败）；不产生 INDETERMINATE（本地读无外部副作用）。

## 测试

- 安全：`tests/security/tools-local.security.test.ts`（相对/绝对路径逃逸、symlink 逃逸、越界 list_dir、root 内正常路径）。门：`mise run test:security`。
- 集成：`tests/integration/tool-runtime.integration.test.ts`（read_file 经执行器成为 durable 事实并进入下一次 context）。门：`mise run test:integration`。
