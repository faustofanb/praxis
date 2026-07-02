# API 开发规范

## 基础约束

- API 统一通过 Alova 管理
- 核心实例、处理器和中间件放在 `src/api/core/`
- Mock 数据放在 `src/api/mock/modules/`
- Mock 数据结构应尽量与真实接口一致

## 常用命令

```bash
pnpm alova-gen
pnpm alova-gen -f
```

## 最佳实践

- 优先使用 `useRequest` 管理请求状态
- 合理配置缓存策略，避免重复请求
- 使用 TypeScript 确保接口类型安全

## QMS_PAD 约束

- `ifc-qms-pad` 新增或调整接口时，必须通过 `pnpm alova-gen` 生成 API 和 DTO；页面不得手写 `Method`、请求路径或 DTO 类型。
- 页面必须直接使用 `pnpm alova-gen` 生成的 API 和 DTO；禁止新增 `src/api/qmsPad/<业务>.ts` 这类业务接口薄封装。确需复用时，只能在业务 composable 中组合已生成 API 的调用，不重新拼接 URL、HTTP method 或请求/响应 DTO。
- 对应 BFF Controller 方法名必须带清晰业务语义，避免 `page`、`submit`、`getDetail` 等泛化命名直接生成 `qms.page`、`qms.submit` 这类歧义 API key。

## MES_PDA 约束

- `ifc-mes-pda` 待处理记录“单据来源”必须按检验类型展示和存储；若当前需求主落点是 QMS_PAD 或其他项目，该能力必须拆成独立 MES PDA 需求处理，不混入同一提交或同一交付分支。

## 来源

- 原 PDA uni-app 仓库 `.cursor/rules/api-development.mdc`
- 原 PDA uni-app 仓库 `.cursor/skills/pda-development/SKILL.md`
