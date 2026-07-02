---
name: bill-lowcode-sourcecode-form
description: '面向 ifc-web-mom-max 在线低代码表格的硬编码表单技能。用于低代码页面承载表格 + 动态组件加载源码表单的场景。'
user-invocable: true
---

# Bill Lowcode Sourcecode Form

仅处理给低代码表格提供硬编码表单组件的任务。

## 核心约束

- 页面目录与 API 目录必须在同模块域
- 表单组件对外暴露 `submit`、`setFieldsValue` 和 `formApi`
- 在 `onMounted` 时 `emit('ready')`
- 表单只承担表单职责，不混入 pageId 列表和弹窗开关逻辑

## 来源

- 来源：`ifc-web-mom-max/docs/skills/bill-lowcode-sourcecode-form/SKILL.md`
- 本次整理方式：轻改写，保留关键组件契约
