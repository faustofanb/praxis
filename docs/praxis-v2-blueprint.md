# Praxis V2 clean-room blueprint

Praxis 管理 AI 的行为边界，使业务开发自动化、规范化，让业务知识可沉淀复用，并优化 Agent 的上下文工程。

## 重生约束

- V2 在 `codex/praxis-v2-rebuild` 从零实现，发布版本为 `2.0.0`。
- 不复制、迁移、改名、cherry-pick 或参考旧 `src`、profile、capability、extension、rule 或 runtime 实现。
- 不读取旧配置，不提供迁移器、legacy 模块、`task` shim、profile 或 capability 兼容。
- Python 模块化单体；CLI 和 Praxis MCP 调用同一 service。
- Markdown/TOML 保存业务事实，SQLite 保存运行状态、索引和审计。
- Rule Markdown 不参与控制；门禁全部代码化。`SKILL.md` 只作为 Agent 内容资产。

## 模块边界

```text
src/praxis/
├── cli/
├── mcp/
├── workspace/
├── worktree/
├── tasks/
├── knowledge/
├── skills/
├── gates/
├── portraits/
├── codegraph/
├── integrations/
└── storage/
```

Workspace 直接声明 `schema_version = 2`、workspace 身份、产品族、vault 和项目事实，不设计 profile、capability 或 extension 框架。

## 功能契约

- Worktrunk：唯一 worktree 实现，Praxis 只封装稳定 JSON CLI 和生命周期 hooks。
- Tolaria：workspace 内单一 Markdown vault；需求包含 request、analysis、plan、progress 和 artifacts，并用业务域标签关联画像。
- Skill：workflow、system、business 三类；代码管理路由、来源、license、版本、hash 和上下文预算。
- Gate：代码实现 `task_start`、`change_preflight`、`verify`、`worktree_pre_merge`、`delivery`、`workspace_scan`，支持可扩展责任链。
- Portrait：默认静态扫描；进程、数据库和部署调查必须显式触发。
- MCP：统一暴露 Praxis 工作流能力；Codex、Claude Code、OMP 使用薄适配器。
- WITR 只用于显式运行时诊断；RTK 只优化人类输出，机器协议绕过；Ponytail 作为技能资产并提供非阻塞 diff 膨胀提示。

## DBX 边界

Praxis 不代理、启动或配置 DBX MCP，不保存 connection、secret 或查询审计，也不提供 `praxis dbx` 命令。仅提供 `dbx-database-investigation` system Skill：执行时检查只读 DBX 工具、列出并匹配连接；缺少工具或连接立即停止；生产连接再次确认；优先获取 schema context，只调查涉及的表，必要时仅执行有限结果的 `SELECT`、`WITH ... SELECT` 或 `EXPLAIN`。禁止连接增删、写 SQL 和危险 SQL。

## CodeGraph 新鲜度

查询前必须同时满足当前 Git HEAD 和 dirty fingerprint 与索引元数据一致。fingerprint 覆盖 staged、unstaged、untracked 文件路径及内容 hash。不一致先 sync；同步失败后绝不读取旧图。

- `workspace init` 不建索引；`workspace bootstrap` 缺失时 init、已有时 sync。
- Worktrunk `post-start` 执行 `ensure-fresh --initialize`。
- task start/resume、上下文装配、change preflight、verify 均 ensure-fresh。
- pre-merge 同步后执行 impact/affected；post-merge 同步目标；post-remove 删除对应元数据。
- query、explore、node、affected 内部强制 ensure-fresh。
- 架构、跨模块、影响分析任务同步失败即阻塞；简单单文件任务可回退 `rg`，但不得读取旧图。
- project/worktree 独立锁；等待超过 30 秒返回 `CODEGRAPH_SYNC_BUSY`。

## 清理和验收

V2 不存在 Orca、MOM/AOTU/IFC-MOM profile、profile resolver、capability graph、legacy 或 `task` shim。真实业务系统重新扫描生成画像和 Skill candidate，复核后的共通知识才进入 `ifc-manufacturing` catalog。

CLI/MCP 返回同构结果。DBX Skill 只在数据库意图下路由。CodeGraph 对 HEAD、staged、unstaged、untracked 变化和全部生命周期事件有测试，并发同步只执行一次。总覆盖率不低于 85%，Gate、路径和安全模块不低于 95%。

工具链由 mise 管理，Python 使用 uv、ruff、ty、pytest、pytest-cov、pytest-xdist、hypothesis、pre-commit 和 pip-audit。
