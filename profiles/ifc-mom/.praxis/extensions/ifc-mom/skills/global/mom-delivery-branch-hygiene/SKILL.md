---
name: mom-delivery-branch-hygiene
description: '用于 IFC MOM 交付分支卫生、defaultBranch/local 与 upstreamBranch/develop 或场景分支区分、feature 分支基线、cherry-pick 生产提交、test commit 隔离、delivery finish/deliver/cleanup 门禁和收口复核。'
user-invocable: true
---

# MOM Delivery Branch Hygiene

## 适用场景

- 用户要求提交、收口、交付、推送、清理 worktree 或创建 feature 分支。
- 需要判断 worktree 基准分支、feature 基准分支、提交是否应进入交付。
- 当前分支含 `test:`、临时验证提交、多需求提交或非交付文件。

## 核心约束

- 实现/修复与提交/交付收尾必须拆开；未获明确确认前不执行 `commit`、`push`、`cherry-pick`、`deliver`、`cleanup`。
- Codeup HTTPS Git 操作优先使用 `task`/`rtk` 工作流入口；必须手工执行底层 Git 时使用 `rtk git ...` 或 `/usr/bin/git ...`，禁止裸 `git ...`。
- 需求 worktree 从项目 `defaultBranch` 创建，通常是 `local`。
- 交付 feature 从 `origin/<upstreamBranch>` 创建，后端/Web 常见为 `develop`，PDA 按场景分支配置。
- 创建 feature 优先使用 `git switch --no-track -c feature/<需求名> origin/<upstreamBranch>`；创建后立即检查 `git branch -vv --list feature/<需求名>`，误跟踪 `origin/<upstreamBranch>` 时先 unset upstream。
- feature 只通过 cherry-pick 纳入生产提交，不直接合并 `local` 或需求 worktree，避免提交噪音。
- cherry-pick 前必须比较需求 worktree 基座提交与 `origin/<upstreamBranch>`：说明是否依赖 local 上未进入上游的历史提交、预计新增/修改文件、历史修复/测试/上下文是必要依赖还是应拆分重做。
- 正式交付只使用 `task delivery -- finish` 生成并经复核的显式哈希清单 `.praxis/out/delivery/<project>/<需求名>/confirmed-commits.txt`；不得以“非 `test:` 提交”作为默认筛选。
- `test:`、`test-support:`、`local-test-support:`、临时验证、实验提交、`src/test`、test-scope `pom.xml` 依赖和非交付文件不得进入 feature，除非用户逐项确认。
- `commit-split`、`deliver` 和 `cleanup` 前展示目标、变更、验证证据与风险，并等待用户明确确认。
- 用户明确说“直接收尾”时，不再新增需求文档、分析记录、README 索引等非代码产物；已有文档变更不带入业务 feature，并在最终说明中列出。

## 执行流程

1. 读取 `praxis.projects.toml`，确认 `defaultBranch` 和 `upstreamBranch`。
2. 检查当前分支、worktree、未提交变更和 `defaultBranch..HEAD` 提交列表。
3. 将提交分类为生产提交、测试提交、本地测试辅助、临时提交、无关提交。
4. 交付前运行 `task delivery -- finish <project> <需求名>` 获取收口提示和显式候选哈希清单，并补充 `origin/<upstreamBranch>...HEAD` 或等价基线差异审计。
5. 对最终 cherry-pick 清单逐个核对 `git show --stat`；发现 test-scope `pom.xml`、`src/test`、临时验证或 codex-only 文件时阻断或要求用户逐项确认。
6. 运行 `task gate -- ready <project> <需求名>` 聚合 preflight/guard 收口门禁；专项排查时才单跑 `guard/change-check/migration-check`。
7. 需要提交拆分时运行 `task delivery -- commit-split <project> <需求名> <结构化提交信息>`。
8. 获得用户确认后才执行 `deliver`、`push` 或 `cleanup`。
9. `deliver` 后检查正式 feature 是否被测试文件、本地测试依赖、临时验证或本地专用文件污染；有污染则阻断 push。

## 冲突与验证

- cherry-pick 冲突时，先判断是上游缺少 local 前置修复、同文件并行修改，还是测试文件在上游不存在；再按用户确认的保留范围解决。
- 代码修复必须保留；用户要求带 spec 时 spec 必须保留；需求文档、本地配置不得进入 feature。
- 冲突解决后运行冲突标记扫描和目标测试。
- 已提交 feature 上若 `task project -- verify` 返回 “No git changes found” 或等价空跑结果，改用 `git diff --name-only origin/<upstreamBranch>...HEAD` 的文件清单执行 scoped 验证，并报告替代命令。

## 必查命令

```bash
task delivery -- finish <project> <需求名>
task gate -- ready <project> <需求名>
task delivery -- deliver <project> <需求名>
task delivery -- cleanup <project> <需求名>
```

## 输出证据

- `defaultBranch`、`upstreamBranch`、feature 基线。
- 需求基座与 `origin/<upstreamBranch>` 差异、隐含 local 依赖、预计 cherry-pick 文件清单。
- 显式确认的 cherry-pick 哈希清单、生产提交与排除提交清单。
- 每个确认提交的 `git show --stat` 复核结论，以及 local-only/test-support 判定。
- `ready` 结果、代码复核结论和未验证项。
- `task verify` 是否空跑及替代验证命令。
- 需要用户确认的具体动作。
