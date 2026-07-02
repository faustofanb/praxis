# Flyway 表迁移约定

## 当前约定

- 数据库表迁移使用 Flyway。
- 表结构调整优先直接修改代码生成工具产出的 SQL 文件。
- 当前 MES 模块迁移目录：`ifc-mom-column-max/lamp-support/lamp-boot-server/src/main/resources/db/migration/mes/2026/03`

## 设计表时的步骤

1. 先用 PostgreSQL MCP 查看同域已有表结构。
2. 对齐现有表的字段命名、主键、审计字段、状态字段和索引习惯。
3. 在代码生成后的 SQL 文件中完成建表、改表、索引、唯一约束等修改。
4. 再基于 SQL 结果对齐后端 Entity、VO、Query 与前端 API/页面字段。

## 禁止事项

- 不要跳过 Flyway 目录单独维护临时 SQL。
- 不要先写 Java/前端字段，再反推数据库结构。
- 不要脱离现有模块命名风格单独发明表名和字段名。