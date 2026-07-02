---
name: big-screen-development
description: '面向 IFC MOM LargeVisualizationScreen 的大屏开发技能。用于新增或修改制造业看板、ECharts 图表、共享资源、数据接口、适配、构建和部署验证。'
user-invocable: true
---

# Big Screen Development

用于 `LargeVisualizationScreen` 的大屏功能开发。

## 适用范围

- 新增或修改 `src/dashboards/` 下看板。
- 调整 ECharts 图表、地图、指标卡、列表、轮播或实时刷新。
- 接入大屏 API、MagicAPI、报表函数或聚合数据。
- 调整 `src/shared/` 下共享配置、样式、请求工具和工具函数。
- 修改静态资源、字体、构建输出、部署路径或代理配置。

## 默认技术栈

- `Vue 2.7 + Element UI 2.15 + ECharts 5.4 + Webpack 5 + Babel 7`

## 核心约束

- 开发前必须读取 `.rule/projects/big-screen/README.md`，再按改动类型展开读取具体规则。
- 新看板放在 `src/dashboards/<dashboard>/`，并在 `config/dashboards.config.js` 注册。
- 设计稿默认按 1920x1080 组织，通过既有缩放方案适配屏幕，不为单一分辨率写死散落样式。
- 图片、字体等资源路径遵守项目规范；优先复用 `src/shared/` 的配置、样式和工具。
- ECharts 实例必须处理初始化、resize、数据更新和销毁，避免重复初始化、重复监听和内存泄漏。
- 数据加载优先使用时间窗口、看板粒度和服务端聚合；禁止默认一次性拉取全部历史数据。
- 涉及报表口径、驾驶舱指标、MagicAPI 或积木报表时，先走轻量 ETL/报表 skill 锁定数据契约，再做大屏消费。

## 规范映射

- 看板目录、资源路径、页面初始化：`.rule/projects/big-screen/01-大屏开发规范.md`
- 构建输出、部署、Nginx、API 代理：`.rule/projects/big-screen/02-大屏构建与部署规范.md`
- 性能与稳定性：`.rule/global/03-性能与稳定性规范.md`
- 报表/驾驶舱数据口径：`.skill/global/mom-lightweight-etl-report/SKILL.md`

## 验证方式

- `npm run build:dashboard -- <看板名称>`
- `npm run build:report`
- `npm run build`

## 完成检查

- 已复用同域看板结构、共享配置和请求工具。
- 图表 resize、刷新、销毁路径清晰，没有重复监听或重复渲染风险。
- 数据请求有时间窗口、看板粒度或聚合约束。
- 静态资源、字体、API 代理和部署路径已按规则说明。
- 已给出最小构建验证命令和结果，或说明无法验证原因。

## 来源

- `.rule/projects/big-screen/01-大屏开发规范.md`
- `.rule/projects/big-screen/02-大屏构建与部署规范.md`
- `LargeVisualizationScreen/README.md`
