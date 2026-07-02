# API 编写规范

## 目录结构

标准结构：

```text
src/api/
├── [模块名]/
│   ├── [功能名].ts
│   ├── model/
│   │   └── [功能名]Model.ts
│   └── index.ts
```

## 类型规范

- Entity 继承 `BaseEntity`
- SaveVO、UpdateVO、ResultVO、PageQuery 按职责拆分
- 所有 `int64` 字段使用 `string`
- 不定义 `ApiResponse<T>` 包装类型

## API 方法规范

- 使用 `requestClient`
- 返回类型直接标注真实业务类型
- 请求方法、路径和导出方式与同域文件一致

## 注释要求

- 公共方法提供 JSDoc
- 类型字段给出必要说明

## 来源

- `ifc-web-mom-max/docs/API编写规范.md`
- `ifc-web-mom-max/.github/skills/frontend-api-development/SKILL.md`
