# 09. 依赖许可证与维护清单

**地位：** 外部直接依赖的事实表（license / 用途 / 维护态势 / 失败影响 / 移除成本）。准入**法则**的唯一权威是根 `AGENTS.md` Dependencies 节；精确版本锁定与依赖方向由 `tests/boundaries.test.ts` 强制；本清单与 manifests 的同步由 `tests/dependency-inventory.test.ts` 强制（unit 门）。三者互不重复。

**范围：** workspace manifests 声明的**直接**外部依赖（根 `package.json` + `packages/*` + `apps/*`；`@praxis/*` workspace 内部引用除外）。传递依赖由 `bun.lock` 精确锁定并经 frozen-install CI 复现，按需可用同一测试机制扩展审计。

**许可允许清单：** MIT、ISC、Apache-2.0（含 `MIT OR Apache-2.0` 双许可）。copyleft 或专有许可进入本树前必须先有 ADR——测试会直接拒绝清单外许可。

## 运行时依赖

| 依赖 | 版本 | 许可 | 用途 | 维护态势 | 失败影响 | 移除成本 |
| --- | --- | --- | --- | --- | --- | --- |
| zod | 4.4.3 | MIT | 唯一运行时外部依赖：contracts 全部事件/端口 schema 与 brand（`asXxx()`），provider-openai wire 边界校验 | colinhacks 维护，发布频繁，TS 生态事实标准 | 全部边界解析失效，包不可运行 | 高：契约层整体重写；同量级替代（valibot/arktype）亦是大迁移 |

## 开发工具链（根 devDependencies）

| 依赖 | 版本 | 许可 | 用途 | 维护态势 | 失败影响 | 移除成本 |
| --- | --- | --- | --- | --- | --- | --- |
| @biomejs/biome | 2.5.10 | MIT OR Apache-2.0 | format + lint 单一工具（零 ESLint/Prettier 双链） | biomejs 团队，活跃 | format/lint 门失效 | 中：退回 prettier+eslint 双工具链 |
| @commitlint/cli | 21.2.2 | MIT | Conventional Commits commit-msg 门 | conventional-changelog 组织，活跃 | commit-msg 门失效 | 低：lefthook 直跑自写脚本 |
| @commitlint/config-conventional | 21.2.2 | MIT | 上项的 conventional 预设 | 同上 | 同上 | 同上 |
| @types/bun | 1.3.14 | MIT | Bun API 类型（配 Bun 1.3.14） | DefinitelyTyped，随 Bun 版本跟踪 | typecheck 对 Bun API 失明 | 低：Bun 内置类型成熟后可移除 |
| @vitest/coverage-v8 | 4.1.11 | MIT | 覆盖率采集（test:coverage） | vitest 仓库同源发布 | 覆盖率报告失效 | 低：仅报告功能 |
| fast-check | 4.9.0 | MIT | 属性测试生成器（property 门三套件 + 影子模型） | dubzzz，活跃（fast-check.dev） | property 门失效 | 高：属性套件整体重写 |
| knip | 6.32.2 | ISC | 未用导出/文件检测（knip 门） | webpro-nl，活跃 | knip 门失效 | 中：手工盘点漂移 |
| lefthook | 2.1.10 | MIT | git hooks 编排（pre-commit biome-staged + commit-msg commitlint） | evilmartians，活跃 | 两道 git 门失效 | 低：husky 或裸脚本 |
| typescript | 7.0.2 | Apache-2.0 | `tsc -b` 严格类型门（typecheck/build） | 微软 | typecheck 与 build 失效 | 高：整个工具链的地基 |
| vitest | 4.1.11 | MIT | 测试运行器（unit/property/integration/replay/fault/security 门） | vitest 团队，活跃 | 除 store/cli（bun test）外全部测试门失效 | 高：测试基础设施 |

## 机器可读同步块

`tests/dependency-inventory.test.ts` 以此块为同步目标：条目集合必须与 workspace manifests 的外部直接依赖双向相等，且版本与许可必须与 pinned 安装（node_modules）一致。增删/升级依赖时同步本块。

```json
{
  "allowlist": ["MIT", "ISC", "Apache-2.0", "MIT OR Apache-2.0"],
  "entries": [
    { "name": "@biomejs/biome", "version": "2.5.10", "license": "MIT OR Apache-2.0", "kind": "dev" },
    { "name": "@commitlint/cli", "version": "21.2.2", "license": "MIT", "kind": "dev" },
    { "name": "@commitlint/config-conventional", "version": "21.2.2", "license": "MIT", "kind": "dev" },
    { "name": "@types/bun", "version": "1.3.14", "license": "MIT", "kind": "dev" },
    { "name": "@vitest/coverage-v8", "version": "4.1.11", "license": "MIT", "kind": "dev" },
    { "name": "fast-check", "version": "4.9.0", "license": "MIT", "kind": "dev" },
    { "name": "knip", "version": "6.32.2", "license": "ISC", "kind": "dev" },
    { "name": "lefthook", "version": "2.1.10", "license": "MIT", "kind": "dev" },
    { "name": "typescript", "version": "7.0.2", "license": "Apache-2.0", "kind": "dev" },
    { "name": "vitest", "version": "4.1.11", "license": "MIT", "kind": "dev" },
    { "name": "zod", "version": "4.4.3", "license": "MIT", "kind": "runtime" }
  ]
}
```
