---
类型: 系统画像
系统编号: praxis-next
仓库编号: praxis-next
扫描时间: 2026-07-23T15:49:46.588523+00:00
内容哈希: 67a40aa51e35181ebb3402e5f5e0f33c078bc908
---

# Praxis V3插件仓库画像

## 仓库范围与结构

- 仓库类型：`python-plugin`
- 配置路径：`.`
- 已识别文件数：283
- 顶层路径：`.claude-plugin`
- 顶层路径：`.codex-plugin`
- 顶层路径：`.config`
- 顶层路径：`.gitignore`
- 顶层路径：`.mcp.json`
- 顶层路径：`.mise.toml`
- 顶层路径：`.pre-commit-config.yaml`
- 顶层路径：`README.md`
- 顶层路径：`adapters`
- 顶层路径：`docs`
- 顶层路径：`package.json`
- 顶层路径：`pi-extension`
- 顶层路径：`praxis.toml`
- 顶层路径：`pyproject.toml`
- 顶层路径：`scripts`
- 顶层路径：`skills`
- 顶层路径：`src`
- 顶层路径：`tests`
- 顶层路径：`tests-js`
- 顶层路径：`uv.lock`
- 顶层路径：`知识库`

## 技术栈

- Python
- Node.js

## 工程入口与接口面

- 工程入口：`package.json`
- 工程入口：`pyproject.toml`
- 工程入口：`src/praxis/__main__.py`
- 接口面：`src/praxis/cli/__init__.py`
- 接口面：`src/praxis/mcp/__init__.py`
- 接口面：`src/praxis/mcp/broker.py`
- 接口面：`src/praxis/mcp/server.py`

## 数据与配置资产

- `.config/wt.toml`
- `.mise.toml`
- `.pre-commit-config.yaml`
- `package.json`
- `praxis.toml`
- `pyproject.toml`
- `skills/add-mom-magic-api/agents/openai.yaml`
- `skills/add-mom-magic-api/skill.toml`
- `skills/api-permission-migration/agents/openai.yaml`
- `skills/api-permission-migration/skill.toml`
- `skills/build-mes-pda-readonly-overview/agents/openai.yaml`
- `skills/build-mes-pda-readonly-overview/skill.toml`
- `skills/codegraph-impact-analysis/agents/openai.yaml`
- `skills/codegraph-impact-analysis/skill.toml`
- `skills/dbx-database-investigation/skill.toml`
- `skills/minimum-module-compile/agents/openai.yaml`
- `skills/minimum-module-compile/skill.toml`
- `skills/ponytail/agents/openai.yaml`
- `skills/ponytail/skill.toml`
- `skills/praxis-requirement-workflow/agents/openai.yaml`
- `skills/praxis-requirement-workflow/skill.toml`
- `skills/praxis-system-development/agents/openai.yaml`
- `skills/praxis-system-development/references/node-routing.toml`
- `skills/praxis-system-development/skill.toml`
- `skills/uniapp-api-generation/agents/openai.yaml`
- `skills/uniapp-api-generation/skill.toml`
- `src/praxis/storage/migrations/0001_initial.sql`
- `知识库/需求/2026/07/REQ-20260720-001__插件版本命令验收/08-关联关系.yaml`
- `知识库/需求/2026/07/REQ-20260720-001__插件版本命令验收/09-产出物清单.yaml`
- `知识库/需求/2026/07/REQ-20260721-001__节点化技能路由与Agent规则初始化/08-关联关系.yaml`
- `知识库/需求/2026/07/REQ-20260721-001__节点化技能路由与Agent规则初始化/09-产出物清单.yaml`
- `知识库/需求/2026/07/REQ-20260721-002__需求工作空间命名与GrillMe门禁/08-关联关系.yaml`
- `知识库/需求/2026/07/REQ-20260721-002__需求工作空间命名与GrillMe门禁/09-产出物清单.yaml`
- `知识库/需求/2026/07/REQ-20260721-003__快速开发路径与后台治理/08-关联关系.yaml`
- `知识库/需求/2026/07/REQ-20260721-003__快速开发路径与后台治理/09-产出物清单.yaml`
- `知识库/需求/2026/07/REQ-20260722-001__工作流上下文与MOM业务Skill治理优化/08-关联关系.yaml`
- `知识库/需求/2026/07/REQ-20260722-001__工作流上下文与MOM业务Skill治理优化/09-产出物清单.yaml`
- `知识库/需求/2026/07/REQ-20260723-001__需求知识投影与上下文压缩/08-关联关系.yaml`
- `知识库/需求/2026/07/REQ-20260723-001__需求知识投影与上下文压缩/09-产出物清单.yaml`
- `知识库/需求/2026/07/工作流上下文与MOM业务Skill治理优化__REQ-20260722-001/产出物清单.yaml`
- `知识库/需求/2026/07/工作流上下文与MOM业务Skill治理优化__REQ-20260722-001/关联关系.yaml`
- `知识库/需求/2026/07/快速开发路径与后台治理__REQ-20260721-003/产出物清单.yaml`
- `知识库/需求/2026/07/快速开发路径与后台治理__REQ-20260721-003/关联关系.yaml`
- `知识库/需求/2026/07/插件版本命令验收__REQ-20260720-001/产出物清单.yaml`
- `知识库/需求/2026/07/插件版本命令验收__REQ-20260720-001/关联关系.yaml`
- `知识库/需求/2026/07/节点化技能路由与Agent规则初始化__REQ-20260721-001/产出物清单.yaml`
- `知识库/需求/2026/07/节点化技能路由与Agent规则初始化__REQ-20260721-001/关联关系.yaml`
- `知识库/需求/2026/07/需求工作空间命名与GrillMe门禁__REQ-20260721-002/产出物清单.yaml`
- `知识库/需求/2026/07/需求工作空间命名与GrillMe门禁__REQ-20260721-002/关联关系.yaml`
- `知识库/需求/2026/07/需求知识投影与上下文压缩__REQ-20260723-001/产出物清单.yaml`
- `知识库/需求/2026/07/需求知识投影与上下文压缩__REQ-20260723-001/关联关系.yaml`

## 质量与交付命令

- 构建：`uv build`
- 构建：`npm run build`
- Lint：`uv run ruff check .`
- 类型检查：`uv run ty check`
- 测试：`uv run pytest -q`

## 数据库连接引用


## 分支与交付

- 发布分支：`main`
- 模板分支：`codex/praxis-v3-development`

## 运行态

- 已显式扫描：否

## 证据

- Python：工具检测，来源 `pyproject.toml`
- Node.js：工具检测，来源 `package.json`
