---
name: magic-api-development
description: '用于 IFC MOM 后端的 magic-api 接口开发与维护。适用于当前工作区中涉及 magic-api 接口新增、脚本修改、在线调试、数据源配置、分页结果、自定义结果、权限控制、Swagger 暴露和发布同步的场景。只要用户提到 magic-api、脚本式接口、无需新增 Controller/Service/Mapper 的快速接口开发，或要维护现有 magic-api 接口，都应优先使用本技能。若需求本质上更适合标准 Java 分层后端开发，则转 java-backend-development。'
user-invocable: true
---

# Magic API Development

用于 `ifc-mom-column-max` 的 `magic-api` 后端开发与维护。

## 适用场景

- 新增或修改 `magic-api` 接口
- 在 `magic-api` 中实现脚本式 HTTP 接口，而不是新增标准 Java 分层文件
- 排查 `magic-api` 的数据源、SQL、分页、自定义结果结构、权限或拦截器配置
- 调试、发布、同步或校验现有 `magic-api` 脚本
- 让 `magic-api` 输出结构对齐 Web、PDA 或第三方调用方

## 不适用场景

- 需求明显属于标准 Java 分层后端开发
- 业务编排复杂，必须依赖清晰的 `Service`、事务边界和强类型对象沉淀
- 需求需要长期沉淀到常规模块代码，而不是以脚本方式快速交付

若命中以上情况，优先转 `.skill/projects/backend/java-backend-development/SKILL.md`。

## 背景

`magic-api` 是基于 Java 的接口快速开发框架，可通过在线 UI 编写脚本并直接映射为 HTTP 接口。

在合适场景下，它可以减少 `Controller`、`Service`、`Mapper` 等常规分层文件的新增成本，并支持分页、自定义结果、数据源配置、权限控制、Swagger 文档和在线调试能力。

## 开发前检查

1. 当前后端项目里 `magic-api` 的实际落点、模块位置和现有样例。
2. 本次需求是否应继续放在 `magic-api`，还是应改为标准 Java 分层开发。
3. 接口的入参、返回结构、异常结构和分页要求。
4. 目标数据源、是否涉及动态数据源切换，以及 SQL 是否需要缓存。
5. 是否涉及权限、拦截器、接口分组、发布同步或 Swagger 暴露。
6. 调用方是谁，是否需要和 Web、PDA 或第三方约定字段语义。
7. 如何验证接口，包括在线调试、本地联调或受管环境验证方式。

## 标准流程

1. 先查当前项目里已有的 `magic-api` 模块、目录、脚本命名和相似接口实现。
2. 优先锁定接口契约，再修改脚本逻辑、SQL 和结果结构。
3. 仅做最小正确改动，不把适合常规后端模块的复杂逻辑硬塞进 `magic-api`。
4. 明确处理分页、自定义结果、权限、拦截器、异常路径和调试方式。
5. 若发现需求已超出 `magic-api` 合适边界，及时转交标准 Java 后端开发方案。

## 脚本语法约束

`magic-api` 脚本不是完整 JavaScript 运行时，编写脚本时必须优先遵循官方脚本语法，而不是按浏览器/Node.js 习惯猜写。

### 函数定义

- 优先使用 lambda / 箭头函数形式定义局部函数。
- 推荐写法：`var fn = (arg) => { ... };`
- 需要多参数时：`var fn = (a, b) => { ... };`
- 简单表达式也可用：`var fn = (a) => a + 1;`

避免直接按常规 JavaScript 函数声明风格扩展复杂逻辑，尤其是在需要与 `magic-api` 的集合循环、lambda、内建对象配合时。

示例：

```javascript
var escapeSqlText = (value) => {
    if (value == null) {
        return '';
    }
    return ('' + value).trim().replace(/'/g, "''");
};
```

### for 循环

- `magic-api` 的 `for` 只支持：
  - 循环集合：`for(item in list)` 或 `for(index, item in list)`
  - 循环 Map：`for(key, value in map)`
  - 循环次数：`for(value in range(0, 10))`
- 不要使用 JavaScript/C 风格三段式循环：
  - `for (var i = 0; i < list.length; i++) { ... }`
- 若只是遍历查询结果集合，优先写成：
  - `for(row in rows) { ... }`

示例：

```javascript
for(row in resultRows) {
    data.add({
        lineCode: row.line_code
    });
}
```

反例：

```javascript
for (var i = 0; i < resultRows.length; i++) {
    var row = resultRows[i];
}
```

### 集合处理

- 查询结果通常按集合处理，优先使用 `for(item in list)`、展开运算符、`list.add(...)` 等 `magic-api` 支持的能力。
- 不要默认认为所有标准 JavaScript 数组方法、对象方法、语法糖都完全可用；不确定时先查官方脚本语法文档或现有项目样例。
- 若脚本需要排序、映射、异步或 lambda，优先先确认当前语法是否在 `magic-api` 文档中明确支持。

### 运行时对象兼容性

- `magic-api` 不是浏览器/Node.js 运行时，不要默认 `Number(...)`、`isNaN(...)`、`Math.round(...)`、`Math.max(...)`、`new Date(...)` 等 JavaScript 内建调用都可直接使用。
- 数值转换优先使用 `::double(0)`、`::int(0)` 等类型转换语法，而不是 `Number(...)`。
- 需要兜底时优先用显式 `if` 判断，不要依赖 `Math.max`、`Math.min` 这类 JS 内建。
- 查询结果里的日期字段往往已经是 Java 侧对象，例如 `java.sql.Date`、`java.sql.Timestamp`；若需要时间戳，优先直接调用对象方法，如 `workDate.getTime()`，不要再 `new Date(workDate)`。
- 出现“找不到函数 / 找不到构造器 / can not found constructor”这类提示时，先怀疑把 `magic-api` 运行时误当成普通 JavaScript 了。

示例：

```javascript
var toNumber = (value) => {
    if (value == null || value === '') {
        return 0;
    }
    return ('' + value)::double(0);
};

var time = workDate == null ? 0 : workDate.getTime();
```

### SQL 解析器兼容性

- `magic-api` 的 `db.select` / `db.page` / `db.update` 在执行前可能经过 SQL 解析器，不是所有 PostgreSQL 方言特性都能被正常解析。
- 即使目标数据库是 PostgreSQL，也不能默认 `magic-api` 侧支持全部 PostgreSQL 语法。
- 遇到 CTE、窗口函数、类型转换、方言关键字时，要优先考虑 `magic-api` SQL 解析兼容性。
- 当前已知限制之一：避免在 `magic-api` SQL 中使用 `WITH ... AS MATERIALIZED (...)`；应改写为普通 `WITH ... AS (...)`，否则可能触发 `JSQLParserException`。
- 当前已踩坑限制之一：即使数据库本身支持 PostgreSQL 方言，`magic-api` 解析器也可能对 `DISTINCT ON (...)` 这类 PostgreSQL 专有语法兼容较差，出现 `PreparedStatementCallback; bad SQL grammar` 时应优先改写为更保守的 `GROUP BY + MIN(id) + 回表`、窗口函数外包一层，或其他通用 SQL 写法。
- 若出现 `net.sf.jsqlparser.JSQLParserException`、`ParseException` 等错误，先怀疑 SQL 被 `magic-api` 解析器拦截，而不是先怀疑数据库本身不支持。
- 某些场景下 `magic-api` 还可能对 SQL 自动追加租户过滤条件，例如在最终查询后拼接 `WHERE tenant_id = ?`。
- 因此只要 SQL 最终结果需要被 `magic-api` 再包装或追加条件，结果集里应尽量保留 `tenant_id` 等租户字段，避免出现“SQL 本身能跑，但包装后字段不存在”的语法或列错误。
- 若为兼容 `magic-api` 自动追加条件而在聚合查询的 `SELECT` 中新增了字段，例如 `tenant_id`，必须同步检查并补齐 `GROUP BY`；否则很容易被统一包装成 `bad SQL grammar`，表面上像语法问题，实质上是聚合字段不完整。
- 参数为空时，优先显式写成 `CAST(NULL AS varchar)`、`CAST(NULL AS date)` 等确定类型的空值，不要依赖裸 `NULL` 让解析器自行推断；尤其是在 `WITH params AS (...)`、可选过滤条件和联合查询中，这类未定型空值很容易被统一包装成 `bad SQL grammar`。
- 可选过滤条件优先尽早下推到各个分支查询中，不要过度依赖最外层再写 `WHERE (NULL::varchar IS NULL OR ...)` 这类条件；对 `magic-api` 来说，越晚做的可选条件越容易与自动追加租户过滤一起形成解析歧义。

### 返回结果结构兼容

- 若调用方需要小驼峰结果，优先使用 `db.camel().select(...)`，并让 SQL `SELECT` 输出下划线字段名，例如 `equipment_code`、`source_bill_code`，由 `camel()` 自动转换。
- 使用 `db.camel().select(...)` 时，不要再混用一批手写驼峰别名，一批下划线字段；统一交给 `camel()` 处理，避免结果结构和脚本可读性都变得混乱。

### bad SQL grammar 排查顺序

- 先判断是否是 `magic-api` SQL 解析器拦截，而不是直接怀疑数据库表或字段不存在。
- 优先对可疑 SQL 做二分排查：
  1. 先只保留一个分支查询，看是否可跑。
  2. 再逐段恢复 `JOIN`、CTE、聚合和可选过滤。
  3. 优先剔除 PostgreSQL 专有语法、未定型 `NULL`、最外层可选过滤、复杂别名或嵌套子查询。
- 当一个报表由多个 `UNION ALL` 分支组成时，不要一次性整体猜；应先让每个分支单独可跑，再合并。

### 编写原则

- 先看现有 `.ms` 样例，再决定脚本写法。
- 先查官方文档，再使用不常见语法。
- 一旦涉及函数定义、循环、lambda、集合转换，不要把 `magic-api` 当成普通 JavaScript。
- 一旦出现报错，先区分是三类问题中的哪一类：脚本语法兼容、SQL 解析兼容、数据库真实 SQL 错误；不要混在一起猜。
- 对报表脚本，优先从仓库里已经成功运行的 `.ms` 样例复制参数构造、`db.camel().select(...)`、CTE 组织方式和空值写法，而不是自己重新发明一种“理论上可行”的 SQL 风格。

## 强制约束

- 优先复用现有 `magic-api` 样例、脚本结构和命名方式
- 先确认接口边界，再写脚本和 SQL
- 避免在 `magic-api` 中承载过重的跨领域业务编排
- 输出结构、分页字段和状态语义要与调用方保持一致
- 无法验证时要明确说明阻塞点和建议验证路径
- 遇到脚本语法实现时，必须以 `magic-api` 官方脚本语法和现有 `.ms` 样例为准，不能直接套用普通 JavaScript 语法

## 输出要求

1. 先说明当前需求为什么适合或不适合 `magic-api`。
2. 说明本次接口落点、调用方和关键约束。
3. 列出计划修改的脚本、配置或关联模块。
4. 再进入具体实现或修改建议。
5. 结束前给出验证方式与自检结果。

## 协作关系

- 标准 Java 后端开发：转 `.skill/projects/backend/java-backend-development/SKILL.md`
- 本地 Maven 测试覆盖：转 `.skill/projects/backend/local-test-override/SKILL.md`
- 若需求同时涉及后端与 Web/PDA：优先由 `.skill/global/mom-fullstack-collaboration/SKILL.md` 总控分流

## 来源

- 官方参考：`https://www.ssssssss.org/magic-api/pages/quick/intro/`
- 本次整理方式：结合 MOM 后端 skill 结构，提炼为仓库内 `magic-api` 专项执行技能
