---
name: frontend-form-development
description: '面向 ifc-web-mom-max 的表单开发技能。用于 Vben 表单、弹窗表单、编辑页表单、动态加载表单、schema 拆分、useVbenForm、zod 条件校验和后端规则合并。'
user-invocable: true
---

# Frontend Form Development

仅处理表单相关前端任务。

## 标准参照

- `.rule/projects/web/03-表单开发规范.md`
- `.rule/projects/web/04-权限国际化与消息规范.md`

## 核心约束

- 使用 `useVbenForm` 管理表单实例与 schema
- 组件使用 `script setup`，导入统一使用 `#/`
- 直接产出正式表单实现，不先写临时表单
- 简单校验直接声明，复杂条件校验使用 `zod`
- 后端已定义校验规则时，优先合并，不手工重复复制

## 来源

- 来源：`ifc-web-mom-max/.github/skills/frontend-form-development/SKILL.md`
- 本次整理方式：轻改写，保留原执行约束
