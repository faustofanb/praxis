---
name: mom-migration-script-generation
description: '用于 IFC MOM 工作区中根据用户提供的模型设计SQL、应用设计SQL和菜单SQL，补全并生成可重复执行的迁移脚本。只要用户提到“生成迁移脚本”“整理低代码迁移SQL”“补全授权/接口SQL”“按现有迁移风格输出 SQL”，尤其是涉及 core_model_table、core_app_page、def_resource、magic_api_file 等对象时，都应优先使用本技能。'
user-invocable: true
---

# MOM Migration Script Generation

用于 IFC MOM 工作区生成标准幂等迁移脚本。

## 适用场景

- 用户已经有一部分 SQL，需要你整理成最终迁移脚本
- 用户只提供了模型设计 SQL、应用设计 SQL、菜单 SQL，希望你补全剩余部分
- 需求涉及低代码模型、页面、菜单、权限、`magic_api_file` 等对象一起迁移
- 用户明确要求“参考现有迁移脚本风格”而不是自由发挥
- 目标是先输出到需求目录中间产物，收尾确认后再迁移到 `db/migration/<module>/<year>/<month>/` 的正式迁移文件

## 迁移落盘门禁

- 开发和调查阶段禁止直接写正式 Flyway 迁移目录。
- 新 v2 需求必须先把迁移草案、拆分稿和复核说明写入 `docs/02-req/YYYY-MM/YYYY-MM-DD-需求名/04-产出物/SQL/`；老需求已有 `中间文档/` 时可沿用既有目录。
- `04-产出物/SQL/` 或老需求 `中间文档/` 是正式确认前的唯一参考来源，不允许对话里口头确认后直接绕过。
- 迁移产出物必须按类型拆分目录或文件：新表 DDL、视图 DDL、菜单/授权 SQL、配置数据 SQL、迁移总稿分开维护；MagicAPI `.ms` 脚本放入 `04-产出物/MAGIC-API脚本草案/`，不混入 `.sql` 文件。
- 用户只要求 MagicAPI `.ms` 脚本时，只输出 `.ms` 和接口说明；不得额外生成 `magic_api_file` 更新 SQL，除非用户明确要求迁移 `magic_api_file` 或完整 Flyway 迁移脚本。
- SQL 产出文件只保留 SQL 草案、注释和必要执行说明；执行前检查、SQL-only 验证结论、风险复核等应单独放入 `.md` 文件，不混入 `.sql`。
- 只有收尾环节，且中间产物已经确认、来源和差异已经复核后，才允许写入正式 Flyway 迁移目录。
- 输出正式迁移文件时，必须同时说明中间产物路径、正式迁移路径、差异复核结论。

## 必须先拿到的输入

开始前优先向用户索取以下内容；若对话里已经给出，则直接复用，不重复问：

1. 模型设计复制 SQL
2. 应用设计复制 SQL
3. 菜单 SQL

若用户没有一次给全，按这个顺序补问。

## 建议补充确认

在不阻塞工作的前提下，优先确认：

1. 目标迁移目录
2. 参考迁移脚本路径
3. 是否包含 `magic-api` 脚本迁移
4. 是否需要补 `def_resource_api`
5. 授权以 `def_tenant_resource_rel` 为准，还是另有角色授权要求

若用户未明确，但仓库和开发库现状足够判断，则直接按现状落地，并在结果中说明依据。

若当前任务来自 `mom-lightweight-etl-report` 流程，优先从需求目录中间产物读取并核对以下输入，再进入迁移整理：

1. 视图 DDL 草案
2. `magic-api` 脚本或接口设计
3. 菜单与授权说明
4. 用户从低代码页面复制出的模型设计 SQL
5. 用户从低代码页面复制出的应用设计 SQL

## 核心目标

把用户给出的零散 SQL 整理成一个可交付迁移脚本，并补全以下常见缺失部分：

- 删除顺序与插入顺序
- 幂等支持
- 菜单授权 SQL
- 接口资源 SQL
- `magic_api_file` SQL
- 视图 SQL 和注释
- 页面设计 / 发布历史关联 SQL

## 固定工作流

1. 先读取目标目录下同模块现有迁移脚本，确认风格。
2. 从用户提供的三段 SQL 中提取固定 ID、对象名、路径、页面编码、模型编码。
3. 判断脚本应覆盖哪些对象：
   - `core_model_table`
   - `core_model_column`
   - `core_model_table_index`
   - 视图 DDL
   - `core_app_page`
   - `core_app_page_design`
   - `core_app_page_history`
   - `magic_api_file`
   - `def_resource`
   - `def_resource_api`
   - `def_tenant_resource_rel`
4. 按外键依赖顺序先删后插，整理为单文件。
5. 检查脚本是否可重复执行。
6. 先输出需求目录中间产物，并说明哪些 SQL 来自用户，哪些是补全生成的。
7. 收尾确认后，才从中间产物迁移到正式 Flyway 文件。

## 幂等要求

默认按 MOM 当前常见风格处理：

- 优先使用 `DELETE FROM ... WHERE id IN (...)` 再 `INSERT`
- 视图优先使用 `DROP VIEW IF EXISTS ...` 再 `CREATE VIEW ...`
- 不默认改成 `ON CONFLICT` 风格，除非参考脚本明确就是这么做
- 低代码生成的新建物理表 DDL 可在中间产物确认后按导出版本进入正式迁移；`DROP TABLE IF EXISTS` 是项目内用于重复执行和结构重建的常见幂等写法，不能仅因包含该语句就归类为破坏性迁移
- 凡使用固定主键 ID 插入菜单、接口、字典、低代码页面等配置数据，默认按固定 ID 或业务键先删后插；不得只依赖 `not exists` 避免重复执行，因为半执行或业务键不完整时仍可能主键冲突
- 删除顺序必须先子表后主表，例如：
  - `def_tenant_resource_rel`
  - `def_resource_api`
  - `def_resource`
  - 页面历史 / 页面设计 / 页面主表
  - 模型索引 / 模型字段 / 模型主表

## 补全规则

### 1. 授权 SQL

- 默认优先补 `def_tenant_resource_rel`
- 不要凭空补角色授权
- 若当前开发库或参考脚本没有 `base_role_resource_rel`，则不要自行新增
- 若菜单 SQL 只给了页面资源，需同步检查完整父级链路是否也要授权，至少覆盖“当前页面菜单 + 直接父菜单 + 授权树中必需的祖先菜单”

### 2. 接口 SQL

- 若菜单对应的是普通后端 Controller 页面，检查是否应补 `def_resource_api`
- 若页面本质走 `magic-api`，且现有风格没有给 `def_resource_api`，可保留为空
- 不要为了“看起来完整”强行捏造接口资源

### 3. magic-api SQL

- 若用户明确要求迁移 `magic-api`，优先要求其提供脚本正文，或从开发库当前记录提取
- 目标表为 `magic_api_file`
- 主键依据为 `file_path`
- 采用 `DELETE FROM magic_api_file WHERE file_path = ...` 再 `INSERT`

### 4. 页面设计 SQL

- 保留 `core_app_page_design` 与 `core_app_page_history` 的版本号对应关系
- 若 `design_json` 与 `snapshot_json` 相同，可复用同一 JSON 内容
- JSON 很长时，优先使用 PostgreSQL dollar-quoted 文本，避免转义失控

### 5. 视图与模型 SQL

- 若用户提供的是“模型设计复制 SQL”，优先以其中固定 ID 和字段元数据为准
- 若视图只用于低代码字段建模，可接受 `WHERE 1 = 0` 的空视图
- 视图注释按用户要求保留 `列名;详细注释` 风格

## 不要做的事

- 不要擅自修改用户提供的固定 ID
- 不要脱离参考迁移脚本另起一套风格
- 不要自行补角色授权、按钮权限、接口权限，除非有明确依据
- 不要把“开发库当前值”与“用户提供 SQL”混写得来源不清
- 不要遗漏父菜单授权链
- 不要在开发/调查阶段直接写入 `db/migration/...` 正式迁移目录
- 不要绕过 `04-产出物/SQL/` 或老需求 `中间文档/` 这个正式确认前的唯一参考来源

## 推荐输出结构

建议按以下段落组织最终脚本：

1. 脚本说明
2. 模型元数据 SQL
3. 视图 SQL
4. 页面元数据 SQL
5. `magic_api_file` SQL
6. 菜单与权限 SQL

## 交付前检查

- 是否已经拿到模型设计 SQL、应用设计 SQL、菜单 SQL
- 是否说明了参考脚本依据
- 是否所有删除语句都在插入前
- 是否子表先删、主表后删
- 是否补齐 `def_tenant_resource_rel`
- 是否补齐资源树展示所需的祖先菜单授权，而不只是当前页面菜单
- 是否仅在有依据时补 `def_resource_api`
- 是否 `magic_api_file` 用 `file_path` 幂等处理
- 是否保留用户给出的固定 ID
- 开发/调查阶段是否输出到了需求目录 `04-产出物/SQL/` 或老需求既有 `中间文档/`
- 如已写正式 `db/migration/...` 目录，是否处于收尾环节，且已列出中间产物路径、正式迁移路径和差异复核结论

## 回应模板

当用户只说“生成迁移脚本”但没有给齐输入时，优先用类似下面的话索取：

```text
先把这三段给我，我按现有迁移风格帮你整理成一个幂等脚本：
1. 模型设计复制 SQL
2. 应用设计复制 SQL
3. 菜单 SQL

如果还要一起迁移 magic-api，也把脚本内容或开发库当前记录一并给我。
```

## 来源

- 来源：当前 MOM 工作区迁移整理实践
- 适用对象：低代码模型 + 页面 + 菜单 + 授权 + magic-api 组合迁移
