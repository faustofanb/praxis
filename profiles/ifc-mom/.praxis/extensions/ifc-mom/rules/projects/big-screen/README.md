# Big Screen Rules

适用于 `LargeVisualizationScreen` 的大屏项目规范。

## 执行入口

大屏需求不能只读本 README。Execution/Quality Agent 必须按改动类型展开读取下列细则，并在回报中列出已检查的规则文件。

## 规则清单

- `01-大屏开发规范.md`：Vue 2.7、ECharts、多看板目录、资源路径、页面初始化和数据加载约束。
- `02-大屏构建与部署规范.md`：全量构建、单看板构建、部署资源、Nginx/API 代理和验证建议。

## 必读组合

- 新增或修改看板：读取 `01-大屏开发规范.md` 和 `02-大屏构建与部署规范.md`。
- 只改图表、数据接口或刷新逻辑：读取 `01-大屏开发规范.md`，并结合 `.praxis/extensions/ifc-mom/rules/global/03-性能与稳定性规范.md` 的大屏条目。
- 涉及部署、静态资源、字体或代理：读取 `02-大屏构建与部署规范.md`。
