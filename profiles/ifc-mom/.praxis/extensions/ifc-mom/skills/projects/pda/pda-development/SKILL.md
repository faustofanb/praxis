---
name: pda-development
description: '面向 IFC MOM PDA 仓库族的 PDA 开发技能。用于页面、组件、API 集成、Mock、Pinia store、UnoCSS 样式、路由和主题适配。'
user-invocable: true
---

# PDA Development

用于 `ifc-mes-pad`、`ifc-mes-pda`、`ifc-tpm-pda`、`ifc-qms-pad`、`ifc-wms-pda` 的 PDA 功能开发。

## 适用范围

- 新建或修改 `src/pages/` 下页面
- 开发 `src/components/` 或 `src/business/` 组件
- 接入 `src/api/` 下的 API、Mock、Alova 配置
- 编写 `src/store/` 下的 Pinia store
- 使用 UnoCSS、主题系统、深色模式做样式开发
- 处理文件路由、布局、tabBar 页面跳转

## 默认技术栈

- `uni-app + Vue 3 + TypeScript + wot-design-uni + Alova + Pinia + UnoCSS`

## 实现优先级

### UI 与交互

1. 优先复用项目已有组件
2. 其次使用 `wot-design-uni`
3. 最后再使用原生 `uni-app` 组件

### 样式

1. 优先使用 UnoCSS 原子类
2. 其次复用组件库样式能力
3. 最后才写自定义 CSS/SCSS

## 核心约束

- 开发前必须读取 `.rule/projects/pda/README.md`，再按改动类型展开读取对应细则；不得只依赖本 skill 的摘要。
- 页面放在 `src/pages/`
- 通用组件放在 `src/components/`
- 业务组件放在 `src/business/`
- 复用逻辑放在 `src/composables/`
- 全面使用 TypeScript，优先补齐类型，不随意使用 `any`
- 默认关注深色模式、多端适配和移动端性能
- 扫码、待处理、弱网、长列表和跨页状态属于 PDA 高风险流程，必须先查同域样例，再说明状态流、失败提示、重复触发和性能边界。
- `ifc-qms-pad` 新增或调整接口时，必须运行 `pnpm alova-gen` 生成 API 和 DTO，页面必须直接使用生成 API 和 DTO；禁止新增 `src/api/qmsPad/<业务>.ts` 这类业务接口薄封装。确需复用时，只能在业务 composable 中组合已生成 API 的调用，不重新拼接 URL、HTTP method 或请求/响应 DTO。
- 运行 `pnpm alova-gen` 前必须确认需求 worktree 已通过统一命令从项目 `defaultBranch` 创建，且创建前已同步 `.praxis/projects.toml` 中的 `upstreamBranch -> defaultBranch`；若绕过统一命令，必须先手工 fetch 并对齐对应发布/场景分支，避免把上游接口差异误带入本需求。
- `ifc-qms-pad` 对应 BFF Controller 方法名必须带清晰业务语义，避免 `page`、`submit`、`getDetail` 等泛化命名生成歧义 API key。
- `ifc-mes-pda` 待处理记录“单据来源”必须按检验类型展示和存储；若当前需求主落点是 QMS_PAD 或其他项目，该能力必须拆成独立 MES PDA 需求处理，不混入同一提交或同一交付分支。

## 规范映射

- 页面/路由：`.rule/projects/pda/02-项目结构规范.md`、`03-路由规范.md`
- API/DTO：`.rule/projects/pda/05-API开发规范.md`
- Store/跨页状态：`.rule/projects/pda/06-状态管理规范.md`
- 样式/主题：`.rule/projects/pda/07-样式规范.md`
- 扫码/弱网/长列表性能：`.rule/projects/pda/08-移动端性能规范.md`
- 验证与交付：`.rule/projects/pda/09-开发工作流规范.md`

## 验证方式

- `pnpm lint` 或 `pnpm lint:fix`
- `MOM_PDA_FULL_TYPECHECK=1 pnpm type-check`（仅在用户明确要求或收尾策略要求项目级 type-check 时执行）
- `pnpm alova-gen`

## 来源

- 来源：原 PDA uni-app 仓库 `.cursor/skills/pda-development/SKILL.md`
- 本次整理方式：轻改写，保留原项目执行路径
