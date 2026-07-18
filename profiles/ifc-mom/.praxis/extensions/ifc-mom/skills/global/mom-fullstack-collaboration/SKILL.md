---
name: mom-fullstack-collaboration
description: '用于 IFC MOM 工作区的需求总控兼开发执行技能。只要用户在当前仓库里提到 MOM 需求分析、项目落点判断、跨后端/Web/PDA/大屏协作、字段状态语义统一、低代码页面选择、接口联动、联调交付、按现有样例直接实现功能，都应优先使用本技能。若需求明显属于统计报表、领导驾驶舱报表、MagicAPI、积木报表或轻量 ETL 报表链路，应优先转 mom-lightweight-etl-report。它不仅负责拆解需求和分流项目，还负责在信息足够时直接推动实际开发、文档沉淀、验证和交付自检。'
user-invocable: true
---

# MOM Fullstack Collaboration

用于当前 MOM 工作区的总控兼执行 skill。

## 适用场景

出现以下任一情况时使用本技能：

- 一个需求同时涉及后端与某个前端子项目
- 一个需求跨 Web、PDA、大屏中的两个或更多子项目
- 需要先判断某个需求应该落在哪个项目或哪些项目
- 需要判断某个 Web 功能优先走低代码、源码还是混合模式
- 需要判断某个报表需求是否应转专项报表开发流程
- 需要在制造业 MOM 场景下统一接口、字段、状态语义和交付边界
- 需要在整理需求、设计、计划或交付文档时统一根目录文档组织方式
- 需求已经足够明确，希望直接在当前仓库里落地开发，而不是只做分析

## 标准参照

- 后端 skill：`.praxis/extensions/ifc-mom/skills/projects/backend/java-backend-development/SKILL.md`
- 后端本地测试：`.praxis/extensions/ifc-mom/skills/projects/backend/local-test-override/SKILL.md`
- Web skill：`.praxis/extensions/ifc-mom/skills/projects/web/frontend-development/SKILL.md`
- Web API skill：`.praxis/extensions/ifc-mom/skills/projects/web/frontend-api-development/SKILL.md`
- Web 表单 skill：`.praxis/extensions/ifc-mom/skills/projects/web/frontend-form-development/SKILL.md`
- PDA skill：`.praxis/extensions/ifc-mom/skills/projects/pda/pda-development/SKILL.md`
- 大屏 skill：`.praxis/extensions/ifc-mom/skills/projects/big-screen/big-screen-development/SKILL.md`
- 全局规则：`.praxis/extensions/ifc-mom/rules/global/`
- 项目规则：`.praxis/extensions/ifc-mom/rules/projects/`

## 目标

输出结果必须同时满足以下要求：

- 先完成需求拆解、项目落点和边界确认，再进入编码或文档沉淀
- 优先复用现有项目目录、模块、API、组件、样例和部署方式
- 能复用就不新增；需要新增时也优先沿用现有同域结构和命名方式
- 保持后端与前端字段、接口路径、分页结构、状态语义一致
- 对性能保持高度敏感，避免默认全量查询、全量渲染、无界列表和无节制动态图形效果
- 注释不可缺失，复杂业务、关键字段、边界条件、异常路径都要有清晰说明
- 若信息已经足够，不停留在建议层面，应直接推进代码实现、文档更新和验证
- 修改完成后至少给出一轮交付自检结果

## 强制前置确认

开始执行前，必须先确认并记录：

1. 本次需求涉及哪个或哪些子项目。
2. 每个子项目内的功能落点、目录归属和现有样例。
3. 是否涉及新表、改表、接口扩展、页面新增、表单、看板或移动端流程。
4. 哪部分可以复用现有实现，哪部分必须新增。
5. Web 场景是否优先采用低代码、源码，还是低代码加源码混合模式。
6. 是否存在性能敏感点，例如历史数据、大列表、矩阵、日历、图表或移动端动画。
7. 是否需要产出根目录文档，以及文档应如何拆分。

若任一项不明确，先补齐信息，不要直接猜。

## 总体分流规则

- 仅后端开发：转后端 skill。
- 仅后台 Web：转 Web skill。
- 仅 PDA：转 PDA skill，并按 `.praxis/extensions/ifc-mom/rules/projects/pda/README.md` 展开读取页面、API、路由、状态、样式和性能细则。
- 仅大屏：转大屏 skill，并按 `.praxis/extensions/ifc-mom/rules/projects/big-screen/README.md` 展开读取开发、构建和部署细则。
- 后端 + Web：以后端契约为主线，再接 Web。
- 后端 + PDA：以后端契约为主线，再接 PDA。
- 后端 + 大屏：先锁定服务端数据结构，再做大屏消费。
- 多前端并行：先统一接口契约和状态语义，再分别按项目 skill 落地。

### Web 低代码分流

- 列表页、单据页、常规表单页优先判断是否走低代码方案。
- 若页面主体可在线配置，但编辑表单存在复杂交互，优先采用“低代码表格 + 源码表单”混合模式。
- 若当前需求明显属于现有低代码单据模式，优先参考 `bill-pageid-modal-form` 与 `bill-lowcode-sourcecode-form`。
- 只有在现有低代码模式明显不适用时，才转为纯源码页面实现。

### 报表专项分流

- 若需求同时包含需求文档、视图 DDL、`magic-api`、积木报表、低代码混码、菜单 SQL、迁移整理或本地测试闭环，优先转 `mom-lightweight-etl-report`
- 普通列表页不要强行套用报表专项流程；仅当需求确属统计报表或驾驶舱报表时再转

## 文档组织要求

若任务要求产出文档，默认遵循：

- 根目录 `docs/` 下一个需求对应一个独立目录
- 需求目录命名遵循 `.praxis/extensions/ifc-mom/rules/global/05-需求文档组织规范.md`
- 大需求按需求分析、任务规划、开发进度进行目录化和多轮维护
- 不在仓库根目录随意放置临时工作文件

## 执行策略

当需求信息已经足够时，本技能不应停留在分析结论，而应直接推动落地：

1. 先查找同域现有实现、相近业务对象、现有 API、现有页面和现有表单方案。
2. 判断应复用、仿写、扩展还是新增，并优先选择最小正确改动。
3. 若涉及数据库、对象模型或接口契约，先锁定后端结构，再推进前端消费。
4. 若涉及 Web 页面，先判断低代码可行性，再决定采用低代码、源码或混合模式。
5. 若涉及多个子项目，先统一字段和状态语义，再分别落到各项目内。
6. 若任务明确要求实现，应继续完成代码改动、文档补充和基础验证，而不是只输出建议。

## 何时提问，何时直接做

- 若缺的是阻止开发的关键条件，例如业务对象定义冲突、核心状态语义不明、目标项目不明，则先问最小必要问题。
- 若现有代码和规则已足以支撑合理实现，则直接开始开发。
- 不因局部不确定而整体停滞；优先完成已确定部分，并在结果中标注风险或待确认项。

## 核心执行流

1. 先拆需求，明确业务目标与影响范围。
2. 判断涉及哪些项目和模块。
3. 先查找同域现有实现，再决定新增还是增量修改。
4. 判断 Web 是否优先采用低代码、源码或混合模式。
5. 若涉及数据库或接口契约，先锁定后端模型与 API 结构。
6. 再按子项目 skill 分别落地页面、表单、PDA 流程或大屏展示。
7. 补充需求文档或过程文档时，遵循全局需求文档组织规范。
8. 最后统一检查权限、消息提示、国际化、性能和验证结果。

## 性能要求

- 后端优先限制查询范围、分页、聚合，避免把性能压力转给前端。
- Web 避免重复请求、超大组件、无必要全量加载。
- PDA 避免移动端性能杀手，如复杂渐变、多层阴影、`backdrop-filter`、`transition-all`。
- 大屏避免默认一次性拉取所有历史数据，优先按时间窗口、看板粒度和聚合结果加载。

## 完成检查

- 已明确各子项目落点与边界。
- 已优先复用现有实现。
- 已说明是否采用低代码、源码或混合模式。
- 已在信息足够时推进实际代码实现，而不是停留在建议层。
- 已处理关键性能风险。
- 已说明需要查看的项目专属 skill 或 rule。
- 已给出验证方式或说明未验证原因。

## 来源

- 主体骨架来源：`ifc-mom-column-max/.cursor/skills/fullstack-development/SKILL.md`
- 补充来源：`.github/skills/fullstack-development/SKILL.md`
- 本次整理方式：提炼归并，扩展为多项目总控版本
