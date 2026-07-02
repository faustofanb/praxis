---
name: mom-frontend-pattern-search
description: '用于 IFC MOM Web、低代码、报表页面和前端接口开发前的同域模式搜索。适用于页面、表单、VxeGrid、导出、权限、国际化、API 注释、MagicAPI 约定、低代码源码混合和报表前端实现，要求先查现有样例再编码。'
user-invocable: true
---

# MOM Frontend Pattern Search

## 适用场景

- Web 页面、列表、表单、弹窗、按钮、权限、国际化、导出。
- 低代码页面、源码表单、低代码 + 源码混合。
- 报表、驾驶舱、MagicAPI 前端消费、VxeGrid 或动态表格。
- 前端 API、生成 API、接口注释和返回字段契约。

## 核心约束

- 编码前必须查同域样例，不能凭记忆新建模式。
- 优先复用项目已有 API、组件、hooks、Vben/VxeGrid、权限、i18n、导出和消息模式。
- 报表/Web 需求至少覆盖：页面目录、API 注释、导出能力、VxeGrid 布局、MagicAPI 写法、权限和国际化。
- 找不到同域样例时，必须说明搜索关键词、搜索路径和采用替代方案的原因。

## 搜索顺序

1. 路由/页面目录：查同业务域、同菜单层级、同页面类型。
2. API：查 `src/api`、生成 API、接口注释、DTO 和分页结构。
3. 表格/表单：查 VxeGrid、Vben Form、Modal、低代码混合样例。
4. 权限/i18n/消息：查按钮权限、菜单权限、国际化 key 和通知模式。
5. 导出/打印/报表：查同类导出、MagicAPI 参数、积木报表或报表数据集调用。
6. 样式：查同域布局、密度、工具栏和响应式方式。

## 推荐搜索

```bash
rg "useVbenVxeGrid|VxeGrid|useDynamicTableBuilder|useVbenForm|useVbenModal" <web-project>/src
rg "export|导出|download|权限|permission|i18n|t\\(" <web-project>/src
rg "magic-api|MagicAPI|/magic/api|db.page|db.select" docs .rule .skill <web-project>/src
```

## 输出证据

- 同域样例路径和可复用点。
- 采用或偏离样例的原因。
- API/权限/i18n/导出/MagicAPI 检查结果。
- 剩余风险和验证命令。
