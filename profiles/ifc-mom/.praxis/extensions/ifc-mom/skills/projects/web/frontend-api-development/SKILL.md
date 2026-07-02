---
name: frontend-api-development
description: '面向 ifc-web-mom-max 的前端 API 开发技能。用于业务 API 文件编写、Entity 和 VO 建模、分页查询、requestClient 接线、BaseEntity 继承和 int64 转 string。'
user-invocable: true
---

# Frontend API Development

仅处理业务 API 文件、类型模型与页面 API 接线任务。

## 标准参照

- `.rule/projects/web/02-API编写规范.md`
- `.rule/projects/web/05-公共包与导入规范.md`

## 核心约束

- API 类型定义按 Entity、VO、Query 分层
- Entity 必须继承 `BaseEntity`
- 所有 `int64` 字段统一建模为 `string`
- 不定义 `ApiResponse<T>` 包装类型
- 路径导入统一使用 `#/`
- 页面接线优先复用 `requestClient` 和现有 API 目录风格

## 来源

- 来源：`ifc-web-mom-max/.github/skills/frontend-api-development/SKILL.md`
- 本次整理方式：轻改写，核心约束保持不变
