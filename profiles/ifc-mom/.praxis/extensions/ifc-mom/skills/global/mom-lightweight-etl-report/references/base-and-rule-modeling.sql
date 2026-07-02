-- IFC MOM 轻量 ETL 报表基础标准化层与公共规则函数层 SQL 草案
-- 来源：postgres_dev 只读元数据调查，2026-06-03
-- 注意：本文件是 skill reference，不直接作为正式 Flyway。业务需求落地时先复制到需求目录 04-产出物/SQL/，确认后再迁移。

-- ---------------------------------------------------------------------------
-- rpt_rule: 公共规则函数层
-- ---------------------------------------------------------------------------

create or replace function public.fn_rpt_rule_bool_flag(p_value smallint)
returns boolean
language sql
immutable
as $$
    select coalesce(p_value, 0) = 1
$$;

comment on function public.fn_rpt_rule_bool_flag(smallint) is
'{"function_type":"rule","subject":"common","purpose":"将 smallint 标志位统一转为 boolean，当前仅 1 视为 true","inputs":"p_value smallint","outputs":"boolean","rule_version":"rpt-rule-v1","stability":"immutable","security":"invoker","boundary_cases":"null 和非 1 均返回 false","used_by":["public.v_rpt_base_*"],"owner":"codex","updated_at":"2026-06-03"}';

create or replace function public.fn_rpt_rule_business_date(
    p_event_time timestamp without time zone,
    p_explicit_date date
)
returns date
language sql
immutable
as $$
    select coalesce(p_explicit_date, p_event_time::date)
$$;

comment on function public.fn_rpt_rule_business_date(timestamp without time zone, date) is
'{"function_type":"rule","subject":"common","purpose":"统一业务日期归属，优先显式业务日期，其次事件时间转日期","inputs":"p_event_time, p_explicit_date","outputs":"date","rule_version":"rpt-rule-v1","stability":"immutable","security":"invoker","boundary_cases":"两个参数均为空时返回 null","used_by":["public.v_rpt_base_*"],"owner":"codex","updated_at":"2026-06-03"}';

create or replace function public.fn_rpt_rule_safe_numeric(p_value numeric)
returns numeric
language sql
immutable
as $$
    select coalesce(p_value, 0::numeric)
$$;

comment on function public.fn_rpt_rule_safe_numeric(numeric) is
'{"function_type":"rule","subject":"common","purpose":"报表数值空值归零","inputs":"p_value numeric","outputs":"numeric","rule_version":"rpt-rule-v1","stability":"immutable","security":"invoker","boundary_cases":"null 返回 0","used_by":["public.v_rpt_base_*","public.v_rpt_metric_*"],"owner":"codex","updated_at":"2026-06-03"}';

create or replace function public.fn_rpt_rule_safe_ratio(
    p_numerator numeric,
    p_denominator numeric,
    p_scale integer default 6
)
returns numeric
language sql
immutable
as $$
    select case
        when coalesce(p_denominator, 0::numeric) = 0 then 0::numeric
        else round(coalesce(p_numerator, 0::numeric) / p_denominator, coalesce(p_scale, 6))
    end
$$;

comment on function public.fn_rpt_rule_safe_ratio(numeric, numeric, integer) is
'{"function_type":"rule","subject":"common","purpose":"统一比例计算，避免分母为 0","inputs":"分子、分母、小数位","outputs":"numeric","rule_version":"rpt-rule-v1","stability":"immutable","security":"invoker","boundary_cases":"分母为 0 或 null 返回 0","used_by":["public.v_rpt_metric_*"],"owner":"codex","updated_at":"2026-06-03"}';

create or replace function public.fn_rpt_rule_inventory_direction_sign(p_direction text)
returns integer
language sql
immutable
as $$
    select case upper(coalesce(p_direction, ''))
        when 'IN' then 1
        when 'OUT' then -1
        else 0
    end
$$;

comment on function public.fn_rpt_rule_inventory_direction_sign(text) is
'{"function_type":"rule","subject":"wms","purpose":"统一库存流水方向符号，开发库 wms_inventory_detail.direction 样例为 IN/OUT","inputs":"p_direction text","outputs":"integer","rule_version":"rpt-rule-v1","stability":"immutable","security":"invoker","boundary_cases":"未知方向返回 0，正式口径需业务确认","used_by":["public.v_rpt_base_wms_inventory_movement"],"owner":"codex","updated_at":"2026-06-03"}';

create or replace function public.fn_rpt_rule_standard_task_status(p_status text)
returns text
language sql
immutable
as $$
    select case upper(coalesce(p_status, ''))
        when 'PENDING' then 'not_started'
        when 'AWAITING_CONFIRM' then 'not_started'
        when 'PRODUCING' then 'running'
        when 'CHANGEOVER' then 'running'
        when 'SUSPENDED' then 'paused'
        when 'END' then 'completed'
        when 'CLOSED' then 'closed'
        when 'CANCEL' then 'cancelled'
        when 'CANCELLED' then 'cancelled'
        else 'unknown'
    end
$$;

comment on function public.fn_rpt_rule_standard_task_status(text) is
'{"function_type":"rule","subject":"mes","purpose":"生产任务单状态粗粒度归一，基于开发库 mes_task_order.task_status 样例","inputs":"p_status text","outputs":"not_started/running/paused/completed/closed/cancelled/unknown","rule_version":"rpt-rule-v1","stability":"immutable","security":"invoker","boundary_cases":"未知状态返回 unknown，正式口径需业务确认","used_by":["public.v_rpt_base_mes_task_order"],"owner":"codex","updated_at":"2026-06-03"}';

create or replace function public.fn_rpt_rule_standard_process_status(p_status text)
returns text
language sql
immutable
as $$
    select case upper(coalesce(p_status, ''))
        when 'PENDING' then 'not_started'
        when 'PRODUCING' then 'running'
        when 'SUSPENDED' then 'paused'
        when 'END' then 'completed'
        when 'CANCEL' then 'cancelled'
        when 'CANCELLED' then 'cancelled'
        else 'unknown'
    end
$$;

comment on function public.fn_rpt_rule_standard_process_status(text) is
'{"function_type":"rule","subject":"mes","purpose":"任务工序状态粗粒度归一，基于开发库 mes_task_order_process.status 样例","inputs":"p_status text","outputs":"not_started/running/paused/completed/cancelled/unknown","rule_version":"rpt-rule-v1","stability":"immutable","security":"invoker","boundary_cases":"未知状态返回 unknown，正式口径需业务确认","used_by":["public.v_rpt_base_mes_task_process"],"owner":"codex","updated_at":"2026-06-03"}';

create or replace function public.fn_rpt_rule_standard_qc_result(p_result text)
returns text
language sql
immutable
as $$
    select case upper(coalesce(p_result, ''))
        when 'OK' then 'qualified'
        when 'PASS' then 'qualified'
        when 'NG' then 'unqualified'
        when 'FAIL' then 'unqualified'
        else 'unknown'
    end
$$;

comment on function public.fn_rpt_rule_standard_qc_result(text) is
'{"function_type":"rule","subject":"qms","purpose":"质量结果粗粒度归一，开发库 qms_qc_process_bill.qc_result 样例为 OK/NG","inputs":"p_result text","outputs":"qualified/unqualified/unknown","rule_version":"rpt-rule-v1","stability":"immutable","security":"invoker","boundary_cases":"让步、复检等结果待业务确认后扩展","used_by":["public.v_rpt_base_qms_process_inspection"],"owner":"codex","updated_at":"2026-06-03"}';

create or replace function public.fn_rpt_rule_standard_execute_status(p_status text)
returns text
language sql
immutable
as $$
    select case upper(coalesce(p_status, ''))
        when 'PENDING' then 'not_started'
        when 'RUNNING' then 'running'
        when 'RECHECKING' then 'checking'
        when 'COMPLETED' then 'completed'
        when 'RUSH_REPAIR' then 'exception'
        else 'unknown'
    end
$$;

comment on function public.fn_rpt_rule_standard_execute_status(text) is
'{"function_type":"rule","subject":"tpm","purpose":"设备任务执行状态粗粒度归一，基于开发库 tpm_equipment_check_task.execute_status 样例","inputs":"p_status text","outputs":"not_started/running/checking/completed/exception/unknown","rule_version":"rpt-rule-v1","stability":"immutable","security":"invoker","boundary_cases":"未知状态返回 unknown，正式口径需业务确认","used_by":["public.v_rpt_base_tpm_equipment_check_task"],"owner":"codex","updated_at":"2026-06-03"}';

create or replace function public.fn_rpt_rule_date_range_is_valid(
    p_start_date date,
    p_end_date date,
    p_max_days integer default 366
)
returns boolean
language sql
immutable
as $$
    select p_start_date is not null
       and p_end_date is not null
       and p_start_date <= p_end_date
       and (p_end_date - p_start_date) <= coalesce(p_max_days, 366)
$$;

comment on function public.fn_rpt_rule_date_range_is_valid(date, date, integer) is
'{"function_type":"rule","subject":"common","purpose":"统一报表日期范围校验，默认不超过 366 天","inputs":"start_date,end_date,max_days","outputs":"boolean","rule_version":"rpt-rule-v1","stability":"immutable","security":"invoker","boundary_cases":"任一日期为空或开始大于结束返回 false","used_by":["MagicAPI"],"owner":"codex","updated_at":"2026-06-03"}';

create or replace function public.fn_rpt_rule_metric_version(p_subject text)
returns text
language sql
immutable
as $$
    select 'rpt-' || coalesce(nullif(lower(trim(p_subject)), ''), 'common') || '-v1'
$$;

comment on function public.fn_rpt_rule_metric_version(text) is
'{"function_type":"rule","subject":"common","purpose":"统一生成第一版报表口径版本号","inputs":"p_subject text","outputs":"text","rule_version":"rpt-rule-v1","stability":"immutable","security":"invoker","boundary_cases":"空主题返回 rpt-common-v1","used_by":["rpt_api","rpt_doc"],"owner":"codex","updated_at":"2026-06-03"}';

-- ---------------------------------------------------------------------------
-- rpt_base: 基础标准化视图层
-- ---------------------------------------------------------------------------

create or replace view public.v_rpt_base_mes_work_report_event as
select
    wrd.tenant_id,
    'MOM'::text as source_system,
    'public.mes_work_report_detail'::text as source_object,
    wrd.id as source_record_id,
    wrd.id as business_object_id,
    wrd.task_id,
    wrd.task_code,
    wrd.task_process_id,
    wrd.process_id,
    wrd.process_code,
    wrd.process_name,
    wrd.process_type_id,
    wrd.process_type_code,
    wrd.process_type_name,
    wrd.process_seq,
    wrd.workshop_id,
    wrd.workshop_name,
    wrd.line_id,
    wrd.line_name,
    wrd.station_id,
    wrd.station_name,
    wrd.equipment_id,
    wrd.equipment_code,
    wrd.equipment_name,
    wrd.material_id,
    wrd.material_code,
    wrd.material_name,
    wrd.material_spec,
    wrd.batch_no,
    wrd.serial_no,
    wrd.container_id,
    wrd.container_code,
    wrd.shift_id,
    wrd.shift_name,
    wrd.operator_id,
    wrd.operator_time as event_time,
    public.fn_rpt_rule_business_date(wrd.operator_time, coalesce(wrd.collect_date, wrd.production_date)) as business_date,
    wrd.collect_date,
    wrd.production_date,
    wrd.report_type as raw_report_type,
    wrd.processing_status as raw_processing_status,
    public.fn_rpt_rule_bool_flag(wrd.is_fix) as is_rework,
    public.fn_rpt_rule_bool_flag(wrd.is_merge) as is_merged,
    public.fn_rpt_rule_bool_flag(wrd.is_half_frame) as is_half_frame,
    wrd.unit_id,
    wrd.unit_name,
    wrd.report_qty,
    wrd.qua_qty,
    wrd.bad_qty,
    wrd.scrap_qty,
    wrd.base_unit_id,
    wrd.base_unit_name,
    wrd.base_report_qty,
    wrd.base_qua_qty,
    wrd.base_bad_qty,
    wrd.base_scrap_qty,
    wrd.aux_unit_id,
    wrd.aux_unit_name,
    wrd.aux_report_qty,
    wrd.aux_qua_qty,
    wrd.aux_bad_qty,
    wrd.aux_scrap_qty,
    wrd.created_time as source_created_at,
    wrd.updated_time as source_updated_at,
    wrd.remark,
    public.fn_rpt_rule_metric_version('mes_work_report') as base_version
from public.mes_work_report_detail wrd;

comment on view public.v_rpt_base_mes_work_report_event is
'{"layer":"base","subject":"mes_work_report","version":"rpt-mes_work_report-v1","status":"draft","grain":"一行代表 mes_work_report_detail 一条报工明细事件","business_purpose":"标准化生产报工事件，供生产过程、产量、质量、在制、对账主题复用","time_rule":"优先 collect_date/production_date，其次 operator_time::date","include_rule":"base 层不过滤业务数据","exclude_rule":"无，后续 biz 层按口径过滤","unit_rule":"保留原单位、基础单位和辅助单位数量，不在 base 层换算","status_rule":"保留 raw_processing_status 和 raw_report_type","upstream":["public.mes_work_report_detail"],"downstream":["rpt_biz"],"debug_entry":"待具体报表创建","owner":"codex","updated_at":"2026-06-03"}';

create or replace view public.v_rpt_base_mes_task_order as
select
    t.tenant_id,
    'MOM'::text as source_system,
    'public.mes_task_order'::text as source_object,
    t.id as source_record_id,
    t.id as business_object_id,
    t.bill_code as task_code,
    t.task_type,
    t.task_status as raw_task_status,
    public.fn_rpt_rule_standard_task_status(t.task_status) as standard_task_status,
    t.priority,
    public.fn_rpt_rule_bool_flag(t.is_urgent) as is_urgent,
    t.source_type,
    t.source_id,
    t.source_bill,
    t.source_entry_id,
    t.source_entry_seq,
    t.mo_code,
    t.material_id,
    t.material_code,
    t.material_name,
    t.material_spec,
    t.unit_id,
    t.base_unit_id,
    t.factory_id,
    t.workshop_id,
    t.line_id,
    t.equipment_id,
    t.mould_id,
    t.shift_id,
    t.plan_date as event_time,
    public.fn_rpt_rule_business_date(t.plan_date, null::date) as business_date,
    t.plan_start_time,
    t.plan_end_time,
    t.actual_start_time,
    t.actual_end_time,
    t.plan_qty,
    t.task_qty,
    t.complete_qty,
    t.inbound_qty,
    t.scrap_qty,
    t.bad_qty,
    t.base_plan_qty,
    t.base_task_qty,
    t.base_complete_qty,
    t.base_inbound_qty,
    t.base_scrap_qty,
    t.base_bad_qty,
    t.task_batch,
    t.container_code,
    t.furnace_no,
    t.created_time as source_created_at,
    t.updated_time as source_updated_at,
    t.remark,
    public.fn_rpt_rule_metric_version('mes_task_order') as base_version
from public.mes_task_order t;

comment on view public.v_rpt_base_mes_task_order is
'{"layer":"base","subject":"mes_task_order","version":"rpt-mes_task_order-v1","status":"draft","grain":"一行代表 mes_task_order 一张生产任务单","business_purpose":"标准化任务单主对象，供订单进度、任务状态、产量汇总主题复用","time_rule":"业务日期暂取 plan_date::date，具体报表可按计划/实际起止时间另定","include_rule":"base 层不过滤业务数据","exclude_rule":"无","unit_rule":"保留原单位与基础单位数量","status_rule":"raw_task_status 通过 fn_rpt_rule_standard_task_status 粗归一","upstream":["public.mes_task_order"],"downstream":["rpt_biz"],"debug_entry":"待具体报表创建","owner":"codex","updated_at":"2026-06-03"}';

create or replace view public.v_rpt_base_mes_task_process as
select
    p.tenant_id,
    'MOM'::text as source_system,
    'public.mes_task_order_process'::text as source_object,
    p.id as source_record_id,
    p.id as business_object_id,
    p.task_id,
    p.step_seq,
    p.process_id,
    p.process_code,
    p.process_name,
    p.process_type_id,
    p.process_type_code,
    p.process_type_name,
    p.status as raw_process_status,
    public.fn_rpt_rule_standard_process_status(p.status) as standard_process_status,
    public.fn_rpt_rule_bool_flag(p.is_first) as is_first_process,
    public.fn_rpt_rule_bool_flag(p.is_last) as is_last_process,
    public.fn_rpt_rule_bool_flag(p.is_equipment) as is_equipment_process,
    p.plan_start_time,
    p.plan_end_time,
    p.actual_start_time,
    p.actual_end_time,
    p.last_time as event_time,
    public.fn_rpt_rule_business_date(p.last_time, null::date) as business_date,
    p.report_qty,
    p.qua_qty,
    p.bad_qty,
    p.scrap_qty,
    p.repair_online_qty,
    p.wait_repair_qty,
    p.base_report_qty,
    p.base_qua_qty,
    p.base_bad_qty,
    p.base_scrap_qty,
    p.base_repair_online_qty,
    p.base_wait_repair_qty,
    p.created_time as source_created_at,
    p.updated_time as source_updated_at,
    p.remark,
    public.fn_rpt_rule_metric_version('mes_task_process') as base_version
from public.mes_task_order_process p;

comment on view public.v_rpt_base_mes_task_process is
'{"layer":"base","subject":"mes_task_process","version":"rpt-mes_task_process-v1","status":"draft","grain":"一行代表 mes_task_order_process 一道任务工序","business_purpose":"标准化任务工序，供工序进度、工序产量、首末工序口径复用","time_rule":"业务日期暂取 last_time::date，具体报表可按计划/实际时间另定","include_rule":"base 层不过滤业务数据","exclude_rule":"无","unit_rule":"保留原数量与基础单位数量","status_rule":"raw_process_status 通过 fn_rpt_rule_standard_process_status 粗归一","upstream":["public.mes_task_order_process"],"downstream":["rpt_biz"],"debug_entry":"待具体报表创建","owner":"codex","updated_at":"2026-06-03"}';

create or replace view public.v_rpt_base_wms_inventory_balance as
select
    i.tenant_id,
    'MOM'::text as source_system,
    'public.wms_inventory'::text as source_object,
    i.id as source_record_id,
    i.id as business_object_id,
    i.warehouse_id,
    i.location_id,
    i.material_id,
    i.owner_id,
    i.owner_type,
    i.supplier_id,
    i.customer_id,
    i.batch_no,
    i.stock_status as raw_stock_status,
    i.production_date,
    coalesce(i.last_in_time, i.last_out_time, i.init_date, i.created_time) as event_time,
    public.fn_rpt_rule_business_date(coalesce(i.last_in_time, i.last_out_time, i.init_date, i.created_time), i.production_date) as business_date,
    i.unit_id,
    i.qty,
    i.lock_qty,
    i.base_unit_id,
    i.base_qty,
    i.lock_base_qty,
    i.aux_unit_id,
    i.aux_qty,
    i.lock_aux_qty,
    i.last_in_time,
    i.last_out_time,
    i.init_date,
    i.expiry_date,
    i.recheck_date,
    i.created_time as source_created_at,
    i.updated_time as source_updated_at,
    i.remark,
    public.fn_rpt_rule_metric_version('wms_inventory') as base_version
from public.wms_inventory i;

comment on view public.v_rpt_base_wms_inventory_balance is
'{"layer":"base","subject":"wms_inventory","version":"rpt-wms_inventory-v1","status":"draft","grain":"一行代表 wms_inventory 一条即时库存余额","business_purpose":"标准化即时库存，供库存余额、在制、容器库存主题复用","time_rule":"优先 production_date，其次最近出入库/初始化/创建时间","include_rule":"base 层不过滤业务数据","exclude_rule":"无","unit_rule":"保留库存单位、基础单位和辅助单位数量","status_rule":"保留 raw_stock_status","upstream":["public.wms_inventory"],"downstream":["rpt_biz"],"debug_entry":"待具体报表创建","owner":"codex","updated_at":"2026-06-03"}';

create or replace view public.v_rpt_base_wms_inventory_movement as
select
    d.tenant_id,
    'MOM'::text as source_system,
    'public.wms_inventory_detail'::text as source_object,
    d.id as source_record_id,
    d.id as business_object_id,
    d.inventory_id,
    d.warehouse_id,
    d.location_id,
    d.material_id,
    d.owner_id,
    d.owner_type,
    d.supplier_id,
    d.customer_id,
    d.container_id,
    d.batch_no,
    d.ref_bill_type,
    d.ref_bill_no,
    d.ref_bill_line,
    d.ref_detail_id,
    d.direction as raw_direction,
    public.fn_rpt_rule_inventory_direction_sign(d.direction) as direction_sign,
    d.stock_status as raw_stock_status,
    d.biz_date,
    d.created_time as event_time,
    public.fn_rpt_rule_business_date(d.created_time, d.biz_date) as business_date,
    d.unit_id,
    d.in_qty,
    d.out_qty,
    d.balance_qty,
    d.base_unit_id,
    d.base_in_qty,
    d.base_out_qty,
    d.base_balance_qty,
    d.aux_unit_id,
    d.aux_in_qty,
    d.aux_out_qty,
    d.aux_balance_qty,
    d.unit_price,
    d.amount,
    d.production_date,
    d.created_time as source_created_at,
    d.updated_time as source_updated_at,
    d.remark,
    public.fn_rpt_rule_metric_version('wms_inventory_movement') as base_version
from public.wms_inventory_detail d;

comment on view public.v_rpt_base_wms_inventory_movement is
'{"layer":"base","subject":"wms_inventory_movement","version":"rpt-wms_inventory_movement-v1","status":"draft","grain":"一行代表 wms_inventory_detail 一条库存流水","business_purpose":"标准化库存出入结存流水，供库存流转、金属平衡、追溯主题复用","time_rule":"优先 biz_date，其次 created_time::date","include_rule":"base 层不过滤业务数据","exclude_rule":"无","unit_rule":"保留原单位、基础单位和辅助单位数量","status_rule":"direction 通过 fn_rpt_rule_inventory_direction_sign 转换方向符号","upstream":["public.wms_inventory_detail"],"downstream":["rpt_biz"],"debug_entry":"待具体报表创建","owner":"codex","updated_at":"2026-06-03"}';

create or replace view public.v_rpt_base_wms_container_operation as
select
    r.tenant_id,
    'MOM'::text as source_system,
    'public.wms_container_record'::text as source_object,
    r.id as source_record_id,
    r.id as business_object_id,
    r.container_id,
    r.material_id,
    r.batch_no,
    r.operation_type as raw_operation_type,
    r.operator_id,
    r.operator_time as event_time,
    public.fn_rpt_rule_business_date(r.operator_time, null::date) as business_date,
    r.before_qty,
    r.after_qty,
    r.before_warehouse_id,
    r.after_warehouse_id,
    r.before_location_id,
    r.after_location_id,
    r.unit_id,
    r.source_type,
    r.source_id,
    r.source_bill,
    r.source_entry_id,
    r.source_entry_seq,
    r.created_time as source_created_at,
    r.updated_time as source_updated_at,
    r.remark,
    public.fn_rpt_rule_metric_version('wms_container_operation') as base_version
from public.wms_container_record r;

comment on view public.v_rpt_base_wms_container_operation is
'{"layer":"base","subject":"wms_container_operation","version":"rpt-wms_container_operation-v1","status":"draft","grain":"一行代表 wms_container_record 一次容器操作","business_purpose":"标准化容器操作流水，供容器追溯、在制和库存对账主题复用","time_rule":"operator_time::date","include_rule":"base 层不过滤业务数据","exclude_rule":"无","unit_rule":"保留源单位和操作前后数量","status_rule":"保留 raw_operation_type","upstream":["public.wms_container_record"],"downstream":["rpt_biz"],"debug_entry":"待具体报表创建","owner":"codex","updated_at":"2026-06-03"}';

create or replace view public.v_rpt_base_qms_process_inspection as
select
    q.tenant_id,
    'MOM'::text as source_system,
    'public.qms_qc_process_bill'::text as source_object,
    q.id as source_record_id,
    q.id as business_object_id,
    q.bill_code,
    q.biz_type,
    q.inspection_type,
    q.qc_status as raw_qc_status,
    q.qc_result as raw_qc_result,
    public.fn_rpt_rule_standard_qc_result(q.qc_result) as standard_qc_result,
    q.qc_qty,
    q.bad_qty,
    q.unit_id,
    q.task_id,
    q.task_code,
    q.mo_code,
    q.batch_no,
    q.material_id,
    q.material_code,
    q.material_name,
    q.material_spec,
    q.workshop_id,
    q.workshop_name,
    q.line_id,
    q.line_name,
    q.station_id,
    q.station_code,
    q.station_name,
    q.process_id,
    q.process_code,
    q.process_name,
    q.mould_id,
    q.mould_code,
    q.equipment_id,
    q.equipment_code,
    q.equipment_name,
    q.shift_id,
    q.shift_name,
    q.inspection_by_id,
    q.inspection_date as event_time,
    public.fn_rpt_rule_business_date(q.inspection_date, q.bill_date) as business_date,
    q.bill_date,
    q.inspection_end_date,
    q.send_check_date,
    q.source_type,
    q.source_id,
    q.source_bill,
    q.source_entry_id,
    q.source_entry_seq,
    q.created_time as source_created_at,
    q.updated_time as source_updated_at,
    q.remark,
    public.fn_rpt_rule_metric_version('qms_process_inspection') as base_version
from public.qms_qc_process_bill q;

comment on view public.v_rpt_base_qms_process_inspection is
'{"layer":"base","subject":"qms_process_inspection","version":"rpt-qms_process_inspection-v1","status":"draft","grain":"一行代表 qms_qc_process_bill 一张过程检验单","business_purpose":"标准化过程检验单，供质量判定、检验统计、质量对账主题复用","time_rule":"优先 bill_date，其次 inspection_date::date","include_rule":"base 层不过滤业务数据","exclude_rule":"无","unit_rule":"保留检验数量和单位","status_rule":"qc_result 通过 fn_rpt_rule_standard_qc_result 粗归一，qc_status 保留原值","upstream":["public.qms_qc_process_bill"],"downstream":["rpt_biz"],"debug_entry":"待具体报表创建","owner":"codex","updated_at":"2026-06-03"}';

create or replace view public.v_rpt_base_tpm_equipment_check_task as
select
    t.tenant_id,
    'MOM'::text as source_system,
    'public.tpm_equipment_check_task'::text as source_object,
    t.id as source_record_id,
    t.id as business_object_id,
    t.bill_code,
    t.execute_status as raw_execute_status,
    public.fn_rpt_rule_standard_execute_status(t.execute_status) as standard_execute_status,
    t.task_result as raw_task_result,
    t.target_type,
    t.equipment_id,
    t.equipment_code,
    t.equipment_name,
    t.category_id,
    t.category_name,
    t.workshop_id,
    t.workshop_name,
    t.line_id,
    t.line_name,
    t.station_id,
    t.station_name,
    t.shift_id,
    t.shift_name,
    t.bill_date,
    coalesce(t.execute_start_time, t.plan_start_time, t.bill_date::timestamp) as event_time,
    public.fn_rpt_rule_business_date(coalesce(t.execute_start_time, t.plan_start_time, t.bill_date::timestamp), t.bill_date) as business_date,
    t.plan_start_time,
    t.plan_end_time,
    t.execute_start_time,
    t.execute_end_time,
    t.duration_minutes,
    t.duration_hours,
    t.executor_by_id,
    t.recheck_result,
    t.recheck_time,
    t.created_time as source_created_at,
    t.updated_time as source_updated_at,
    t.remark,
    public.fn_rpt_rule_metric_version('tpm_equipment_check') as base_version
from public.tpm_equipment_check_task t;

comment on view public.v_rpt_base_tpm_equipment_check_task is
'{"layer":"base","subject":"tpm_equipment_check","version":"rpt-tpm_equipment_check-v1","status":"draft","grain":"一行代表 tpm_equipment_check_task 一张设备点检任务","business_purpose":"标准化设备点检任务，供设备状态、点检完成率、异常统计主题复用","time_rule":"优先 bill_date，其次执行/计划时间","include_rule":"base 层不过滤业务数据","exclude_rule":"无","unit_rule":"保留执行时长分钟/小时","status_rule":"execute_status 通过 fn_rpt_rule_standard_execute_status 粗归一","upstream":["public.tpm_equipment_check_task"],"downstream":["rpt_biz"],"debug_entry":"待具体报表创建","owner":"codex","updated_at":"2026-06-03"}';

create or replace view public.v_rpt_base_tpm_equipment as
select
    e.tenant_id,
    'MOM'::text as source_system,
    'public.tpm_equipment'::text as source_object,
    e.id as source_record_id,
    e.id as business_object_id,
    e.code as equipment_code,
    e.name as equipment_name,
    e.category_id,
    e.type as equipment_type,
    e.grade,
    e.use_status as raw_use_status,
    e.state as raw_state,
    e.enable_time,
    e.disable_time,
    e.workshop_id,
    e.line_id,
    e.station_id,
    e.dept_id,
    e.location,
    e.installation_location,
    e.first_use_date,
    e.last_maintenance_date,
    e.last_inspection_date,
    e.last_repair_date,
    e.created_time as event_time,
    public.fn_rpt_rule_business_date(e.created_time, e.first_use_date) as business_date,
    e.created_time as source_created_at,
    e.updated_time as source_updated_at,
    e.remark,
    public.fn_rpt_rule_metric_version('tpm_equipment') as base_version
from public.tpm_equipment e;

comment on view public.v_rpt_base_tpm_equipment is
'{"layer":"base","subject":"tpm_equipment","version":"rpt-tpm_equipment-v1","status":"draft","grain":"一行代表 tpm_equipment 一台设备","business_purpose":"标准化设备主数据，供设备状态、OEE、点检维修主题复用","time_rule":"优先 first_use_date，其次 created_time::date","include_rule":"base 层不过滤业务数据","exclude_rule":"无","unit_rule":"无","status_rule":"保留 raw_use_status 和 raw_state，启停用语义待确认","upstream":["public.tpm_equipment"],"downstream":["rpt_biz"],"debug_entry":"待具体报表创建","owner":"codex","updated_at":"2026-06-03"}';

create or replace view public.v_rpt_base_mdm_material as
select
    m.tenant_id,
    'MOM'::text as source_system,
    'public.mdm_material'::text as source_object,
    m.id as source_record_id,
    m.id as business_object_id,
    m.code as material_code,
    m.name as material_name,
    m.short_name,
    m.spec,
    m.drawing_no,
    m.material_texture,
    m.material_category_id,
    m.material_type,
    m.material_kind,
    m.base_unit_id,
    m.weight_unit_id,
    m.volume_unit_id,
    m.gross_weight,
    m.net_weight,
    m.length,
    m.width,
    m.height,
    m.volume,
    m.profile_length,
    m.profile_single_weight,
    m.short_stick_single_weight,
    m.section_area,
    m.alloy_no,
    m.film_thickness,
    m.state as raw_state,
    public.fn_rpt_rule_bool_flag(m.is_inventory) as is_inventory,
    public.fn_rpt_rule_bool_flag(m.is_sale) as is_sale,
    public.fn_rpt_rule_bool_flag(m.is_outsourcing) as is_outsourcing,
    public.fn_rpt_rule_bool_flag(m.is_produce) as is_produce,
    public.fn_rpt_rule_bool_flag(m.is_purchase) as is_purchase,
    m.enable_time,
    m.disable_time,
    m.created_time as event_time,
    public.fn_rpt_rule_business_date(m.created_time, null::date) as business_date,
    m.created_time as source_created_at,
    m.updated_time as source_updated_at,
    m.remark,
    public.fn_rpt_rule_metric_version('mdm_material') as base_version
from public.mdm_material m;

comment on view public.v_rpt_base_mdm_material is
'{"layer":"base","subject":"mdm_material","version":"rpt-mdm_material-v1","status":"draft","grain":"一行代表 mdm_material 一个物料","business_purpose":"标准化物料主数据，供生产、库存、质量、单位换算和报表维度复用","time_rule":"created_time::date","include_rule":"base 层不过滤业务数据","exclude_rule":"无","unit_rule":"保留基础单位、重量单位、尺寸单位和物料关键尺寸重量字段","status_rule":"保留 raw_state，允许库存/销售/生产等标志转 boolean","upstream":["public.mdm_material"],"downstream":["rpt_biz"],"debug_entry":"待具体报表创建","owner":"codex","updated_at":"2026-06-03"}';

create or replace view public.v_rpt_base_iot_equipment_metric as
select
    d.tenant_id,
    'MOM'::text as source_system,
    'data.iot_equipment_data_collection'::text as source_object,
    null::bigint as source_record_id,
    null::bigint as business_object_id,
    d.collect_time as event_time,
    public.fn_rpt_rule_business_date(d.collect_time, null::date) as business_date,
    d.equipment_id,
    d.equipment_code,
    d.equipment_type,
    d.metric_code,
    d.value_numeric,
    d.value_text,
    d.workshop_id,
    d.line_id,
    d.tags,
    d.create_time as source_created_at,
    null::timestamp without time zone as source_updated_at,
    public.fn_rpt_rule_metric_version('iot_equipment_metric') as base_version
from data.iot_equipment_data_collection d;

comment on view public.v_rpt_base_iot_equipment_metric is
'{"layer":"base","subject":"iot_equipment_metric","version":"rpt-iot_equipment_metric-v1","status":"draft","grain":"一行代表 data.iot_equipment_data_collection 一条设备指标采集值","business_purpose":"标准化设备数采指标，供设备状态、OEE、能耗和工艺参数主题复用","time_rule":"collect_time::date","include_rule":"base 层不过滤业务数据，但具体报表必须加时间范围","exclude_rule":"无","unit_rule":"数采指标单位需按 metric_code 或标签另行确认","status_rule":"无统一状态，仅保留 value_numeric/value_text","upstream":["data.iot_equipment_data_collection"],"downstream":["rpt_biz"],"debug_entry":"待具体报表创建","owner":"codex","updated_at":"2026-06-03"}';
