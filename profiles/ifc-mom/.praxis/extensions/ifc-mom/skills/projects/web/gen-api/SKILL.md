---
name: gen-api
description: '面向 ifc-web-mom-max API 包生成与接线的技能。用于根据 Swagger/OpenAPI 文档生成 packages/@ifc/api/<module> 模块代码，并完成构建校验和前端接线。'
user-invocable: true
---

# Gen API

仅处理生成或补齐 API 包并接入前端的任务。

## 前置确认

1. Swagger/OpenAPI 文档地址可访问。
2. 目标模块名明确。
3. 输出目录明确，优先使用 `packages/@ifc/api/<module>`。
4. 生成命令真实存在。
5. 前端接线位置明确。

## 核心约束

- 优先对齐现有 API 包模板与命名风格
- 包目录结构、导出和构建方式要完整
- 不在未确认命令存在时直接假设 `pnpm gen-api` 可用

## 来源

- 来源：`ifc-web-mom-max/docs/skills/gen-api/SKILL.md`
- 本次整理方式：轻改写，保留生成与接线链路要求
