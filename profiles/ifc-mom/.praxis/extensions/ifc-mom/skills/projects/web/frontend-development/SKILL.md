---
name: frontend-development
description: '面向 ifc-web-mom-max 的通用前端开发技能。用于跨页面、组件、路由、状态管理、样式、国际化、消息通知与性能优化的综合前端任务。'
user-invocable: true
---

# Frontend Development

仅处理 `ifc-web-mom-max` 及其同风格前端模块的通用或跨领域开发任务。

## 适用范围

- 新增或改造 Vue 页面、业务组件、列表页、详情页等综合前端功能
- 同时涉及路由、状态管理、权限、消息通知、国际化、样式和性能的页面任务
- 排查页面整体是否符合项目规范，并一次性修正多类问题

## 标准参照

- `.skill/global/mom-code-quality-compliance/SKILL.md`
- `.rule/projects/web/01-前端开发总规范.md`
- `.rule/projects/web/02-API编写规范.md`
- `.rule/projects/web/03-表单开发规范.md`
- `.rule/projects/web/04-权限国际化与消息规范.md`
- `.rule/projects/web/05-公共包与导入规范.md`

## 前置确认

1. 功能属于哪个模块目录。
2. 页面、组件、API 是否处于同一业务域。
3. 是列表页、详情页、表单页还是综合改造。
4. 是否已有现成页面、schema、store、route、hook、utils 可复用。
5. 是否应分流到 API 或表单专项 skill。
6. 至少查 1 个同域页面/API/schema/grid/form 样例；没有样例时写明搜索路径。

## 核心约束

- 组件统一使用 Vue 3 Composition API 与 `script setup`
- 路径导入统一使用 `#/`
- 页面、API、schema、hook、store 分责清晰
- 优先复用 Vben 能力和现有同域实现
- 权限、消息提示、国际化、响应式和性能优化不能缺位

## 强制自检

交付前必须回报：

- 同域样例路径和复用点。
- 页面/API/schema/hook/store/route 分责是否清晰。
- 权限、国际化、消息提示、导出、分页、加载态、禁用态是否按场景处理。
- 是否存在硬编码文本、硬编码权限、手写生成 API、绕过 Vben/VxeGrid 现有模式。
- 最小 lint 命令和结果；包级 typecheck 只有用户明确要求或设置 `MOM_WEB_PACKAGE_TYPECHECK=1` 时执行，否则回报跳过原因。

## 来源

- 来源：`ifc-web-mom-max/.github/skills/frontend-development/SKILL.md`
- 本次整理方式：轻改写，改为根目录统一引用
