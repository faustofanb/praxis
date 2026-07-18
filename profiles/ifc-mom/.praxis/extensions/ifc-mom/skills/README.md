# MOM Skills

本目录统一沉淀 IFC MOM 工作区的 skill。

## 目录说明

- `global/`: 跨项目通用 skill
- `projects/`: 按子项目拆分的专属 skill

## 使用原则

- 先使用全局 skill 判断项目归属、协作边界、文档组织方式
- 再按实际落点切换到后端、Web、PDA 或大屏专属 skill
- 项目专属 skill 优先保留原项目成熟执行流，只做最小统一化整理

## 设计说明

### 全局 Skill

- `mom-agent-workflow/`: 负责角色化 Agent 调度、职责边界、输出契约和交付质量协作
- `mom-code-quality-compliance/`: 负责后端/Web 代码规范执行、自检和复核证据
- `mom-context-budgeting/`: 负责主对话上下文预算、worker 派发阈值、长日志摘要和证据落盘
- `mom-database-investigation/`: 负责真实库只读调查、生产库边界、大表查询、字段口径和 SQL 证据
- `mom-delivery-branch-hygiene/`: 负责 defaultBranch/upstreamBranch、feature 基线、cherry-pick、test commit 隔离和 cleanup 分支卫生
- `mom-doc-organization/`: 负责根目录文档输出方式，强调索引、拆分和命名一致性
- `mom-frontend-pattern-search/`: 负责 Web/低代码/报表页面开发前同域模式搜索
- `mom-lightweight-etl-report/`: 负责 PostgreSQL 函数/视图、MagicAPI、积木报表、口径治理、对账和迁移协作的轻量 ETL 报表链路
- `mom-praxis-command-contract/`: 负责 Taskfile、.praxis/commands.toml、.praxis/manifest.toml、task.py 和规则文档命令契约一致性
- `mom-tolaria-vault/`: 负责 docs Tolaria vault 的 note、type、relationship、wikilink、frontmatter 和 saved view 维护

### 项目 Skill

- backend: Java 后端开发、本地测试覆盖
- web: 前端开发、API、表单、低代码、API 生成
- pda: uni-app PDA 开发
- big-screen: 大屏看板、ECharts、共享资源、数据加载、构建和部署验证

## 维护原则

- 优先改主版本 skill，不新增近似重复版本
- 新增 skill 前先判断现有 skill 是否已覆盖
- 新增后同步更新对应目录的 `README.md`

## 导航

- `global/README.md`
- `projects/README.md`
