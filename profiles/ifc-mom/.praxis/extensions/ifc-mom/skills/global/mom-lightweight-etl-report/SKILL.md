---
name: mom-lightweight-etl-report
description: '用于 IFC MOM 工作区中基于 PostgreSQL 函数/视图、MagicAPI、积木报表的报表、统计、驾驶舱、口径治理、对账排查和轻量 ETL / 逻辑数仓类需求。'
user-invocable: true
---

# MOM Lightweight ETL Report

## 定位

在当前 MOM 工作区中，报表链路默认采用“PostgreSQL 函数沉淀规则、视图沉淀口径、MagicAPI 暴露接口、积木报表负责展示”的轻量 ETL 架构。

详细工作流见 `.rule/global/praxis-workflow/08-轻量ETL报表工作流.md`；按任务需要再读取 `08a-轻量ETL资产与分层.md`、`08b-轻量ETL调查与口径治理.md`、`08c-轻量ETLMagicAPI与积木报表.md`、`08d-轻量ETL产出物与验收.md`；原始设计来源见 `design/01-ELT报表架构设计.md`。

按需读取的 references：

- `references/templates.md`：口径卡、注释、报表拆解、验收、逻辑依赖和产出物模板。
- `references/prompts.md`：元数据调查、业务访谈、视图/函数、MagicAPI、积木报表、口径争议和影响分析提示词。
- `references/dev-db-base-rule-modeling.md`：基于开发库只读调查形成的基础标准化层与公共规则函数层建模说明。
- `references/base-and-rule-modeling.sql`：落在 `public` schema 下的 `v_rpt_base_*` 基础视图和 `fn_rpt_rule_*` 公共函数 SQL 参考稿。

## 适用场景

- 新增或改造 MES 报表、统计表、领导驾驶舱、积木报表数据集。
- 设计 PostgreSQL 报表视图、函数、指标汇总、API 契约视图或参数化函数。
- 开发 MagicAPI 报表查询、分页、导出、对账、口径说明接口。
- 处理报表口径不清、数据对不上、字段来源不明、指标版本变更。
- 需要输出视图 DDL、MagicAPI 脚本、积木报表说明、菜单授权或迁移中间产物。

## 不适用场景

- 只改普通 Java 业务接口且不涉及报表口径。
- 只做前端静态文案或页面样式调整。
- 只整理既有 Flyway 迁移且不涉及报表设计。
- PDA、大屏专项开发但没有报表数据口径或 MagicAPI/积木报表落点。

## 必须遵守

- 不臆造真实业务表、字段、状态码、工序码、质量码、单位和关联关系。
- 涉及表关系、字段来源、真实数据、报表口径、SQL 或迁移时，先按 dbx MCP 只读调查门禁执行；无法查库时明确标注“未连接数据库，待人工确认”。
- 生产库或疑似生产数据不得直接扫大表；数采、日志、流水、历史明细类表必须条件化、小范围、只读调查。
- 迁移脚本、DDL、菜单授权、低代码模型/应用设计和 MagicAPI 迁移 SQL 先写需求目录 `04-产出物/`，收尾确认后才进入正式 Flyway。
- 核心口径不得分散复制到 MagicAPI 或积木报表表达式中。
- 已沉淀 ETL 资产必须维护 `docs/03-etl/资产索引.md` 全局台账；单个需求或单个资产目录不得各自维护同名局部资产索引。
- ETL 资产、指标口径卡和需求目录反链必须兼容 Tolaria：使用 YAML frontmatter 标记 `type`、`title`、`created`、`tags`、`system`、`menu_path` 等元数据；第一行 H1 是展示标题；相对 Markdown 链接是主导航，wikilink 用于关系和知识网络补充。
- 公共函数优先兼容增强既有函数，避免为少量过滤条件、显示字段或排序序号新增 wrapper；签名或返回类型变化必须提供旧函数 drop 策略、旧调用兼容说明和依赖排查清单。
- 多个函数重复使用同一字段集合时，优先沉淀组合类型、视图或稳定公共函数作为字段契约；最终对外 API 可保留平铺字段以兼容报表调用。
- 面向驾驶舱、高频刷新、跨月统计或大表聚合的报表，必须评估实时函数、普通视图、物化视图和汇总表之间的性能方案，并写明刷新/补算策略。

## 默认架构

```text
业务数据库原始对象
  -> 元数据调查层
  -> rpt_base_*   基础标准化视图
  -> rpt_rule_*   公共规则函数
  -> rpt_biz_*    业务口径视图
  -> rpt_metric_* 指标汇总视图/函数
  -> rpt_api_*    API契约视图/函数
  -> MagicAPI     参数、分页、权限、返回结构
  -> 积木报表     展示、导出、打印
```

本项目默认不新增报表 schema，全部使用 `public` schema，并用前缀替代分层：`v_rpt_base_*`、`fn_rpt_rule_*`、`v_rpt_biz_*`、`v_rpt_metric_*`、`v_rpt_api_*`、`v_rpt_debug_*`、`v_rpt_doc_*`。

## 执行流程

1. 判断需求类型和落点：报表、统计、驾驶舱、MagicAPI、视图 DDL、积木报表、口径对账优先走本 skill。
2. 初始化业务需求上下文：业务需求用 `task req -- init` 或 `task project -- start <project>` 保留用户原文；规则维护类变更不写 `docs/02-req/YYYY-MM/`。
3. 初始化 ETL 资产目录：优先执行 `task etl -- init`，再用 `task etl -- subject` 创建主题目录；已有文件不覆盖。
4. 菜单模块归属：先按系统菜单划分 ETL 模块，优先使用菜单 `code` 作为稳定目录标识；无法确认时归入 `unclassified` 并标注待确认。
5. 数据调查：先查元数据、注释、索引、样例、状态枚举、时间字段和单位字段候选，再结合页面、接口、单据和业务确认。
6. 口径建模：每个指标建立口径卡，至少回答“按什么粒度、按什么时间、哪些数据计入、公式是什么”。
7. PostgreSQL 分层：按 `base -> rule -> biz -> metric -> api -> debug/doc` 设计，复杂公共规则抽函数，视图不跨层乱承担职责。
8. MagicAPI：只做参数校验、分页、排序白名单、权限过滤、返回结构和调试接口；普通参数用 `#{}`，`${}` 只用于白名单后的排序字段或方向。进入 MagicAPI 前必须做兼容性门禁：不写 CTE 内嵌套 CTE，复杂窗口函数/多级 CTE 优先下沉 PostgreSQL 视图/函数，最终结果保留 `tenant_id` 等自动过滤字段，避免变量直接参与 interval 等方言表达式。
9. 积木报表：只负责展示、导出、打印和必要表达式；复杂参数、权限、口径版本和对账入口优先走 MagicAPI。
10. 验收与对账：覆盖参数边界、总数对账、明细抽样、异常状态、空数据、权限、分页、排序、导出和口径版本。

## 模块与目录沉淀

ETL 产出必须沉淀到独立资产目录，不只放在单次需求目录：

```text
docs/03-etl/<应用>/<系统>/<一级菜单>/<二级菜单>/.../<中文主题>/
```

要求：

- `<应用>` 使用顶部应用分类：`运营平台`、`基础平台`、`仓库管理`、`供应协同`、`生产制造`、`质量管理`、`设备管理`、`计划排程`。
- `<系统>` 使用 `MES`、`QMS`、`WMS`、`TPM`、`APS` 等中文可读系统名。
- 目录名优先对应真实菜单名称和菜单层级，例如 `生产制造/MES/04-工厂建模/06-班次信息/<主题>/`。
- 菜单 `code/component` 写入口径卡和 README 作为证据，不替代菜单层级目录。
- 旧粗模块目录只作为历史资产兼容和迁移暂存，不作为新主题默认落点。
- `<中文主题>` 使用稳定业务名称，不使用一次性需求长标题。
- 需求目录保留原始需求、调查过程、阶段进度和链接；可复用口径卡、SQL、对账说明、接口契约以 `docs/03-etl` 为主。
- 需求目录和中心 ETL 资产的交付内容默认按可直接复制到正式目录的正式版表述生成；新文件名、标题、状态字段、SQL 注释和 COMMENT JSON 不写“草案”或 `draft`，是否已落库由目录位置、交付说明和收尾确认区分。
- `docs/03-etl/<应用>/<系统>/00-系统业务建模/` 维护菜单模块划分、表对象推断、菜单证据和跨模块引用规则。
- 同一个指标被 MagicAPI、大屏、积木报表复用时，只维护一个中心口径卡，其他需求文档指向它。
- 需求目录的 `04-产出物/ETL资产链接.md` 只保存中心资产反链，不复制中心口径卡正文；中心资产 README 和口径卡必须互链，并保留 Tolaria frontmatter 便于检索和 saved views 聚合。
- `docs/03-etl/资产索引.md` 是全局资产台账，新增或调整资产后必须登记资产编码、资产类型、层级、状态、版本、主要函数/SQL、调用方、验证入口、性能方案和刷新/补算策略。

脚本入口：

```bash
task etl -- init
task etl -- subject <应用> <系统> <一级菜单> <中文主题> --menu-path <一级菜单/二级菜单/...> --requirement <需求名> --menu-code <菜单编码> --menu-name <菜单名称>
task etl -- tree
```

## MagicAPI 兼容要求

PostgreSQL 能跑不等于 MagicAPI 能跑。报表 SQL 若要直接放入 MagicAPI，必须优先采用保守写法：

- 禁止 `AS (WITH ... SELECT ...)` 嵌套 CTE。
- 避免复杂 CTE 链中使用 `ROW_NUMBER`、`LEAD`、`LAG` 等窗口函数；需要这些能力时优先设计 `v_rpt_api_*` 或 `fn_rpt_api_*`。
- 最终查询显式输出 `tenant_id`，避免 MagicAPI 自动追加租户条件后找不到字段。
- 不使用 `SELECT *` 作为最终契约。
- 避免 `${param} - INTERVAL ...`、`${param}::date` 这类 MagicAPI/JSQLParser 兼容性差的参数方言表达式。
- 遇到 `PreparedStatementCallback; bad SQL grammar` 且 PostgreSQL 原 SQL 能跑时，先按“JSQLParser 兼容、自动租户包装、外层字段缺失”排查。

报表口径修复默认同时产出两版思路：

- 快速修复版：MagicAPI 兼容 SQL，短期恢复页面或接口。
- ETL 沉淀版：PostgreSQL 视图/函数 + debug 对账 + 口径卡，是否正式落库由用户收尾确认决定。
- 大表或日期范围报表的 ETL 沉淀版必须优先设计 `fn_rpt_api_*` 参数化函数；函数参数必须进入源表查询分支，禁止用无参 `v_rpt_api_*` 或全量业务口径视图暴露历史后再外层过滤。

## 输出物要求

完整报表需求至少沉淀：

- 需求拆解和数据调查记录。
- 菜单模块归属说明，包含系统、菜单编码、菜单名称、路径或无法确认原因。
- 指标口径卡。
- PostgreSQL 函数/视图 SQL 与 COMMENT 注释脚本。
- `rpt_debug_*` 对账视图或函数。
- `rpt_doc_*` 口径说明入口，或等价口径说明文档。
- MagicAPI 脚本和接口说明。
- 积木报表数据集、参数、展示和导出说明。
- 验收 SQL、对账样例、风险与待确认项。

中心 ETL 资产目录至少包含：

- `README.md`：主题说明、菜单归属、当前状态、下游引用和需求来源。
- `指标口径卡.md`：中心口径卡。
- `ETL.sql`：函数/视图/COMMENT。
- `对账说明.md`：对账口径、样例和验收边界。
- 按需补充 `MagicAPI契约.md`、`积木报表契约.md`、`验证SQL.sql`。
- `README.md`、`指标口径卡.md` 和需求反链文档必须带 Tolaria frontmatter；frontmatter 不替代正文中的基本信息、菜单归属、版本和证据。

基础建模起点：

- 开发库第一版基础标准化层优先复用 `references/base-and-rule-modeling.sql` 中的 `public.v_rpt_base_*`。
- 公共规则函数优先复用 `public.fn_rpt_rule_*`，不要在业务视图、MagicAPI 或积木报表中重复复制状态归一、日期归属、空值处理、比例计算和方向符号规则。
- 公共规则函数需要补充通用能力时，优先增强既有函数并兼容旧调用；字段集合复用优先使用组合类型或视图契约。

## 禁止事项

- 禁止未调查就写确定字段映射。
- 禁止一个视图同时承担清洗、口径、聚合和展示四类职责。
- 禁止正式报表直接查询源业务表，debug 接口除外且必须注明原因。
- 禁止在 MagicAPI 中复制复杂公共口径 SQL。
- 禁止大数据量或时间敏感报表用无参 API 视图作为最终数据入口。
- 禁止在积木报表表达式中实现核心指标。
- 禁止无分页或无时间边界查询大明细。
- 禁止没有对账样例就关闭口径争议。
- 禁止口径变更不记录版本、不分析影响范围。

## 完成检查

- 数据来源、字段、状态、单位和时间口径是否有证据或明确待确认。
- 每个指标是否有口径卡和版本。
- PostgreSQL 层是否按职责分层，函数/视图是否有注释。
- MagicAPI 是否有参数校验、分页、排序白名单和对账接口。
- 积木报表是否只消费稳定数据契约，不重复实现核心口径。
- 迁移相关内容是否仍停留在需求目录中间产物，未越过收尾确认。
- 验收是否包含总数、明细抽样、边界、权限、导出和性能风险。

## 来源

- `design/01-ELT报表架构设计.md`
- `.rule/global/praxis-workflow/08-轻量ETL报表工作流.md`
- `.rule/global/praxis-workflow/08a-轻量ETL资产与分层.md`
- `.rule/global/praxis-workflow/08b-轻量ETL调查与口径治理.md`
- `.rule/global/praxis-workflow/08c-轻量ETLMagicAPI与积木报表.md`
- `.rule/global/praxis-workflow/08d-轻量ETL产出物与验收.md`
