# 开发库基础标准化层与公共规则函数层建模

调查时间：2026-06-03 15:20
调查环境：`postgres_dev`
调查方式：只读元数据和小范围枚举聚合查询

## 调查结论

开发库对象分布：

- `public`：633 张基础表，39 个视图。
- `data`：9 张基础表，主要是数采和检测时序数据。
- 高频业务前缀：`mes` 238、`wms` 92、`base` 63、`tpm` 56、`mdm` 46、`def` 34、`qms` 29、`aps` 17、`jimu` 14、`core` 12、`magic` 5。

已存在报表相关视图：

- 多个 `v_*_report_board` 使用 `WHERE 1 = 0` 作为低代码/报表建模骨架。
- 金属平衡、模具盘盈、氧化日报等少量视图已直接写实算 SQL。
- 这些视图当前多数未按 `base -> rule -> biz -> metric -> api -> debug/doc` 分层，后续改造应逐步迁移，不建议一次性重写所有既有视图。

第一版基础标准化层覆盖以下开发库证据充分的主题。按项目约束，不新增 `rpt_base` / `rpt_rule` schema，所有对象落在 `public`，通过 `v_rpt_base_*` 和 `fn_rpt_rule_*` 前缀区分职责。

| 主题 | 源对象 | 证据字段 |
| --- | --- | --- |
| MES 生产报工事件 | `public.mes_work_report_detail` | 任务、工序、产线、设备、批次、报工/合格/不良/报废数量、基础单位数量、操作时间、归集日期、生产日期、班次 |
| MES 任务单 | `public.mes_task_order` | 任务状态、计划/下达/完工/入库/报废/不良数量、计划/实际起止时间、组织、物料、来源单据 |
| MES 任务工序 | `public.mes_task_order_process` | 工序状态、报工/合格/不良/报废数量、计划/实际时间、工序类型 |
| WMS 即时库存 | `public.wms_inventory` | 库存数量、基础数量、辅助数量、锁定数量、库存状态、批次、生产日期、最近出入库时间 |
| WMS 库存流水 | `public.wms_inventory_detail` | 入/出/结存数量、方向、业务日期、来源单据、库存状态、批次 |
| WMS 容器操作 | `public.wms_container_record` | 操作前后数量、操作类型、操作时间、来源单据、容器、物料、批次 |
| QMS 过程检验 | `public.qms_qc_process_bill` | 检验状态、检验结果、检验数量、不良数量、检验时间、送检时间、任务/物料/工序/设备 |
| TPM 设备点检任务 | `public.tpm_equipment_check_task` | 执行状态、任务结果、设备、计划/执行起止时间、执行时长、班次 |
| TPM 设备主数据 | `public.tpm_equipment` | 设备编码、名称、分类、使用状态、启停用时间、组织、产线 |
| MDM 物料主数据 | `public.mdm_material` | 物料编码、名称、属性、单位、重量、长度、状态、启停用时间 |
| MDM 单位换算 | `public.mdm_unit_conversion` | 基本单位、换算单位、分子、分母 |
| 生产日历班次 | `public.mes_production_calendar_shift` | 日期、产线、工作时段 JSON |
| 设备数采 | `data.iot_equipment_data_collection` | 采集时间、设备、指标编码、数值/文本值、车间、产线、标签 |

开发库枚举样例：

- `mes_task_order.task_status`：`CLOSED`、`END`、`SUSPENDED`、`PRODUCING`、`AWAITING_CONFIRM`、`PENDING`、`CHANGEOVER`。
- `mes_task_order_process.status`：`PENDING`、`SUSPENDED`、`END`、`PRODUCING`。
- `qms_qc_process_bill.qc_status`：`FINISHED`、`WAITING`。
- `qms_qc_process_bill.qc_result`：`OK`、`NG`。
- `tpm_equipment_check_task.execute_status`：`PENDING`、`RECHECKING`、`COMPLETED`、`RUNNING`、`RUSH_REPAIR`。
- `tpm_equipment_check_task.task_result`：`OK`。
- `wms_inventory_detail.direction`：`IN`、`OUT`。
- `wms_inventory.stock_status`：`AVAILABLE`。

这些枚举只能作为开发库证据，正式口径仍需业务确认。

## 基础标准化层设计

第一版 `public.v_rpt_base_*` 只做字段标准化和溯源，不做业务聚合：

- 统一输出 `tenant_id`、`source_system`、`source_object`、`source_record_id`、`business_object_id`。
- 统一事件时间：优先使用业务事件时间，其次使用创建时间。
- 统一业务日期：优先使用源表明确日期字段，其次由事件时间截断。
- 统一组织维度：`workshop_id`、`line_id`、`equipment_id`、`station_id` 按源表存在情况输出。
- 统一物料/批次/任务/工序维度：按源表存在情况输出。
- 统一数量字段：保留原单位、基础单位、辅助单位数量；不做跨物料换算。
- 统一状态字段：保留原始状态，并用 `public.fn_rpt_rule_*` 函数给出粗粒度标准状态。
- 保留 `created_time`、`updated_time`、`remark`，便于排查。

建议第一版视图：

- `public.v_rpt_base_mes_work_report_event`
- `public.v_rpt_base_mes_task_order`
- `public.v_rpt_base_mes_task_process`
- `public.v_rpt_base_wms_inventory_balance`
- `public.v_rpt_base_wms_inventory_movement`
- `public.v_rpt_base_wms_container_operation`
- `public.v_rpt_base_qms_process_inspection`
- `public.v_rpt_base_tpm_equipment_check_task`
- `public.v_rpt_base_tpm_equipment`
- `public.v_rpt_base_mdm_material`
- `public.v_rpt_base_iot_equipment_metric`

## 公共规则函数设计

第一版 `public.fn_rpt_rule_*` 只放跨报表稳定规则：

- `fn_rpt_rule_bool_flag(smallint)`：`1` 视为 true，其余 false。
- `fn_rpt_rule_business_date(timestamp, date)`：优先显式业务日期，否则事件时间转日期。
- `fn_rpt_rule_safe_numeric(numeric)`：空值转 0。
- `fn_rpt_rule_safe_ratio(numeric, numeric, integer)`：安全比例。
- `fn_rpt_rule_inventory_direction_sign(text)`：`IN` 为 1，`OUT` 为 -1，其余 0。
- `fn_rpt_rule_standard_task_status(text)`：任务状态粗归一。
- `fn_rpt_rule_standard_process_status(text)`：工序状态粗归一。
- `fn_rpt_rule_standard_qc_result(text)`：质量结果粗归一。
- `fn_rpt_rule_standard_execute_status(text)`：设备任务执行状态粗归一。
- `fn_rpt_rule_date_range_is_valid(date, date, integer)`：报表日期范围校验。
- `fn_rpt_rule_metric_version(text)`：统一返回口径版本前缀。

这些函数应使用 `immutable` 或 `stable`：

- 纯参数计算函数使用 `immutable`。
- 如果未来读取配置表、字典表或权限表，应改为 `stable`，并重新评估依赖。

## SQL 草案

SQL 草案见 `base-and-rule-modeling.sql`。该文件不应直接写入正式 Flyway；报表需求落地时先复制到需求目录 `04-产出物/SQL/`，结合具体报表主题确认后再进入正式迁移。

## 待确认问题

- 状态枚举是否存在跨模块统一字典，还是以各业务表字段注释为准。
- 生产日期与报工归集日期在不同报表中的优先级是否统一。
- `collect_date`、`production_date`、`operator_time` 作为业务日期的适用边界。
- 基础单位、辅助单位和重量单位是否可用 `mdm_unit_conversion` 统一换算。
- 数采表 `data.iot_equipment_data_collection` 是否可作为统一数采入口，还是需要兼容 `iot_*_daq` 专表。
- Debug 视图权限和普通报表权限如何区分。
