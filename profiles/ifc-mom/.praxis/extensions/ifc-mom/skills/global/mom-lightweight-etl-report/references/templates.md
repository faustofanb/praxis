# 轻量 ETL 报表模板

本文件承接 `design/01-ELT报表架构设计.md` 中应在报表任务中反复使用的模板。报表需求落地时，需求过程文档按需复制到需求目录 `01-需求分析拆解/` 或 `04-产出物/`；可复用 ETL 资产应同步沉淀到 `docs/03-etl/<应用>/<系统>/<一级菜单>/<二级菜单>/.../<中文主题>/`。新产出物默认使用可直接复制到正式目录的正式版表述，文件名、标题、状态字段、SQL 注释和 COMMENT JSON 不写“草案”或 `draft`。

## 菜单模块归属

```text
应用：<运营平台/基础平台/仓库管理/供应协同/生产制造/质量管理/设备管理/计划排程>
系统：<MES/QMS/WMS/TPM/APS>
菜单编码：<menu_code，例如 mes:chart>
菜单目录名：<一级菜单/二级菜单/...>
菜单名称：<menu_name>
菜单路径：<menu_path>
菜单组件：<component，可为空>
主题目录：docs/03-etl/<应用>/<系统>/<一级菜单>/<二级菜单>/.../<中文主题>/

归属理由：
<说明为什么该指标主责属于该菜单；跨菜单使用时说明主责菜单和引用菜单>

下游引用：
- MagicAPI: <api_path>
- 大屏/前端: <page_or_dashboard>
- 积木报表: <report_code>

待确认：
<菜单未确认、菜单缺失或跨模块争议>
```

## 中心 ETL 资产 README

```text
# <subject title>

## 模块归属

- 系统：<system>
- 应用：<application>
- 菜单编码：<menu_code>
- 菜单名称：<menu_name>
- 主题编码：<subject>
- 当前状态：CHECKING / CONFIRMED / CHANGED / DEPRECATED

## 资产

- 口径卡：指标口径卡.md
- ETL SQL：ETL.sql
- 对账说明：对账说明.md
- MagicAPI 契约：MagicAPI契约.md
- 积木报表契约：积木报表契约.md
- 验证 SQL：验证SQL.sql

## 需求来源

- <docs/02-req/YYYY-MM/YYYY-MM-DD-需求名/>

## 下游使用

- <MagicAPI / 大屏 / 积木报表 / 导出>

## 维护记录

- <yyyy-mm-dd version change>
```

## 指标口径卡

```text
指标编码：<metric_code>
指标名称：<metric_name>
所属主题：<subject>
所属系统：<system>
所属应用：<application>
所属菜单：<menu_code> <menu_name>
中心资产目录：docs/03-etl/<应用>/<系统>/<一级菜单>/<二级菜单>/.../<中文主题>/
指标版本：<metric_version>
当前状态：CHECKING / BIZ_REVIEW / CONFIRMED / CHANGED / DEPRECATED

业务含义：
<用业务语言解释指标，不写 SQL>

统计粒度：
<按什么对象、什么时间、什么组织、什么业务维度统计>

时间口径：
<按哪个业务事件时间统计，具体字段需调查>

计入规则：
<哪些记录计入>

排除规则：
<哪些记录排除>

状态口径：
<状态如何归一，具体状态码需调查>

单位口径：
<单位如何统一，具体字段需调查>

计算公式：
<业务公式，不引用未确认字段>

数据来源：
<源系统 / 源对象，具体表字段待调查>

上游视图：
<rpt_base / rpt_biz / rpt_metric 对象>

下游使用：
<MagicAPI 接口 / 积木报表 / MES 页面>

对账样例：
<样例编号列表，不写敏感信息>

确认人：
<业务确认人>

维护人：
<技术维护人>

修改记录：
<yyyy-mm-dd 版本 变更原因 影响范围>
```

## PostgreSQL 视图头部注释

```sql
/*
对象类型：PostgreSQL View
对象名称：<schema>.<view_name>
所属层级：base / biz / metric / api / debug / doc
所属主题：<subject>
口径版本：<version>
状态：checking / confirmed / deprecated

业务用途：
<说明该视图服务什么业务主题>

数据粒度：
<说明一行代表什么>

上游依赖：
- <upstream_object_1>
- <upstream_object_2>

下游使用：
- MagicAPI: <api_path>
- JimuReport: <report_code>

核心口径：
1. 时间口径：<待确认或已确认说明>
2. 计入口径：<待确认或已确认说明>
3. 排除口径：<待确认或已确认说明>
4. 单位口径：<待确认或已确认说明>
5. 状态口径：<待确认或已确认说明>

对账方式：
- Debug对象：<debug_view_or_api>
- 样例编号：<sample_keys>

维护信息：
- 创建人：<developer>
- 创建日期：<yyyy-mm-dd>
- 最后修改：<yyyy-mm-dd>
- 修改原因：<reason>
*/
```

## COMMENT 模板

```sql
comment on view <schema>.<view_name> is
'{
  "layer": "<base|biz|metric|api|debug|doc>",
  "subject": "<subject>",
  "version": "<version>",
  "status": "<checking|confirmed|deprecated>",
  "grain": "<一行数据代表什么>",
  "business_purpose": "<业务用途>",
  "time_rule": "<时间口径>",
  "include_rule": "<计入规则>",
  "exclude_rule": "<排除规则>",
  "unit_rule": "<单位规则>",
  "status_rule": "<状态口径>",
  "upstream": ["<object_1>", "<object_2>"],
  "downstream": ["<api_or_report_1>"],
  "debug_entry": "<debug_api_or_view>",
  "owner": "<owner>",
  "updated_at": "<yyyy-mm-dd>"
}';

comment on column <schema>.<view_name>.<column_name> is
'{
  "business_name": "<业务名称>",
  "meaning": "<字段含义>",
  "source": "<来源对象或计算规则>",
  "unit": "<单位或无>",
  "nullable": "<是否允许为空>",
  "metric_version": "<version>",
  "note": "<补充说明>"
}';

comment on function <schema>.<function_name>(<arg_types>) is
'{
  "function_type": "<rule|api|debug|doc>",
  "subject": "<subject>",
  "purpose": "<函数用途>",
  "inputs": "<输入说明>",
  "outputs": "<输出说明>",
  "rule_version": "<version>",
  "stability": "<immutable|stable|volatile>",
  "security": "<invoker|definer>",
  "boundary_cases": "<边界情况>",
  "used_by": ["<view_or_api_1>", "<view_or_api_2>"],
  "owner": "<owner>",
  "updated_at": "<yyyy-mm-dd>"
}';
```

## MagicAPI 接口注释

```javascript
/*
接口路径：/report/<subject>/page
接口名称：<报表名称>
接口类型：报表分页查询

【数据契约】
调用对象：<rpt_api_schema>.<v_or_fn_name>
数据层级：rpt_api
返回粒度：<抽象粒度，待确认>
指标版本：<metric_version>

【业务口径】
时间口径：<待确认>
统计对象：<待确认>
计入口径：<待确认>
排除口径：<待确认>
单位口径：<待确认>
状态口径：<待确认>

【参数】
必填参数：<param_list>
可选参数：<param_list>
分页参数：page, size
排序参数：sortField, sortOrder

【对账】
对账接口：/debug/<subject>/detail
口径说明接口：/doc/metric/detail
样例单据：<待补充>

【修改记录】
v0.1 yyyy-mm-dd 创建接口，未确认口径
v1.0 yyyy-mm-dd 口径确认
*/
```

## MagicAPI 兼容检查

```text
是否直接查询源表：
<是/否；若是，说明为何不能先沉淀到 rpt_api 视图/函数>

是否存在 CTE 内嵌套 CTE：
<不得存在 AS (WITH ... SELECT ...)>

是否存在窗口函数：
<ROW_NUMBER / LEAD / LAG 等；若存在，说明是否已下沉 PostgreSQL 层>

最终 SELECT 是否显式输出 tenant_id：
<是/否；MagicAPI 自动租户过滤需要>

是否存在 SELECT *：
<最终契约不得使用 SELECT *>

是否存在变量参与 PostgreSQL 方言表达式：
<例如 ${startTime} - INTERVAL、${date}::date；应避免>

是否提供降级版 SQL：
<复杂查询需提供少 CTE、少窗口函数、少方言特性的 MagicAPI 兼容版>

PostgreSQL 验证：
<验证命令/SQL/结果>

MagicAPI 验证：
<接口路径/参数/返回摘要/报错记录>
```

## 快速修复版与 ETL 沉淀版

```text
快速修复版：
- 目标：<恢复页面/接口或临时对账>
- 落点：MagicAPI 脚本 / 已有接口
- 兼容策略：<少 CTE、少窗口函数、显式 tenant_id、字段契约不变>
- 风险：<性能/解析/口径复制>

ETL 沉淀版：
- 目标：<长期复用的稳定口径>
- 建议对象：
  - v_rpt_biz_<subject>
  - v_rpt_metric_<subject>
  - fn_rpt_api_<subject>(p_start_date, p_end_date, ...)
  - v_rpt_debug_<subject>
- 口径卡：<路径>
- 对账入口：<debug 视图/函数或验证 SQL>
- 是否本次正式落库：是 / 否
- 参数边界：<必须说明日期/组织/权限等参数如何下推到源表查询分支，禁止全量 API 视图或全量业务视图外层过滤>
```

## 积木报表说明

```text
报表名称：<报表名称>
报表编号：<report_code>
报表版本：<report_version>

数据来源：
- 数据方式：SQL / MagicAPI
- 数据集名称：<dataset_name>
- 调用接口或视图：<api_or_view_name>

业务口径：
- 统计对象：<待确认>
- 时间口径：<待确认>
- 统计粒度：<待确认>
- 指标版本：<metric_version>
- 排除规则：<待确认>
- 单位规则：<待确认>

参数：
- 必填参数：<param_list>
- 可选参数：<param_list>
- 默认值规则：<default_rule>

对账：
- 对账接口：<debug_api>
- 口径说明接口：<doc_api>
- 验收样例：<sample_keys>

修改记录：
- yyyy-mm-dd v0.1 创建
- yyyy-mm-dd v1.0 口径确认
```

## 报表需求拆解

```text
报表名称：<report_name>
报表编号：<report_code>
业务主题：<subject>
使用对象：<user_role>
使用场景：<scene>

报表目标：
<为什么要做这个报表>

统计对象：
<统计什么业务对象>

统计粒度：
<按什么维度形成一行>

时间口径：
<按什么时间归属>

指标：
1. <metric_1>
2. <metric_2>

筛选条件：
1. <filter_1>
2. <filter_2>

展示方式：
- 列表
- 汇总卡片
- 图表
- 明细穿透
- 导出
- 打印

对账样例：
<业务方提供样例>

待确认问题：
1. <question_1>
2. <question_2>
```

## 验收清单

```text
报表编号：<report_code>
接口路径：<api_path>
积木报表：<jimureport_code>
指标版本：<metric_version>

验收项：
[ ] 参数必填校验通过
[ ] 默认参数逻辑正确
[ ] 分页正确
[ ] 排序正确
[ ] 空数据返回正确
[ ] 总数对账通过
[ ] 明细样例对账通过
[ ] 时间边界对账通过
[ ] 状态边界对账通过
[ ] 单位换算对账通过
[ ] 权限范围正确
[ ] 积木报表展示正确
[ ] 导出结果正确
[ ] 指标口径说明完整
[ ] Debug 接口可用
[ ] 变更记录已写

验收结论：
通过 / 不通过

未通过原因：
<reason>

确认人：
<name>

确认日期：
<yyyy-mm-dd>
```

## 逻辑依赖图

```text
<source_object_A> ─┐
                  ├─ v_rpt_base_<subject> ─┐
<source_object_B> ─┘                         │
                                             ↓
                                  fn_rpt_rule_<rule>
                                             ↓
                                  v_rpt_biz_<subject>
                                             ↓
                                  v_rpt_metric_<subject>
                                             ↓
                                  v_rpt_api_<subject>
                                             ↓
                                  MagicAPI /report/<subject>/page
                                             ↓
                                  JimuReport <report_code>

调试链路：
v_rpt_biz_<subject>
        ↓
v_rpt_debug_<subject>
        ↓
MagicAPI /debug/<subject>/detail

口径链路：
v_rpt_doc_metric
        ↓
MagicAPI /doc/metric/detail
```

## 最小闭环产出物

```text
04-产出物/
  关联信息调查/
  口径卡/
  SQL/
    01_base_views.sql
    02_rule_functions.sql
    03_biz_views.sql
    04_metric_views.sql
    05_api_views_or_functions.sql
    06_debug_views.sql
    07_doc_views.sql
    08_comments.sql
    09_test_queries.sql
  MAGIC-API脚本/
  积木报表说明/
  对账样例/
```
