---
name: java-backend-development
description: '用于 IFC-MOM-MAX 项目的 Java 后端开发、模块新增、接口实现、CRUD 生成功能、分层改造和事务边界控制。适用于 Controller、Service、Manager、Mapper、Entity、VO、Query、Facade 的设计与编码。'
user-invocable: true
---

# Java Backend Development

用于 `ifc-mom-column-max` 的 Java 后端开发。

## 适用场景

- 新增或修改后端业务功能
- 新建或调整 Entity、VO、Query、Manager、Service、Controller、Facade
- 标准 CRUD、树形、状态、编码、租户等能力开发
- Spring Boot 3 + Java 17 + MyBatis-Plus 技术栈下的项目规范落地

## 标准参照

- `.skill/global/mom-code-quality-compliance/SKILL.md`
- `.rule/projects/backend/01-架构分层规范.md`
- `.rule/projects/backend/02-父类继承与特性接口规范.md`
- `.rule/projects/backend/03-命名与建模规范.md`
- `.rule/projects/backend/04-开发规范.md`
- `.rule/projects/backend/05-注解与事务规范.md`
- `.rule/projects/backend/06-功能设计规范.md`
- `.rule/projects/backend/07-数据库迁移与Flyway规范.md`

## 目标

- 严格遵循 Controller -> Service -> Manager -> Mapper 分层
- 命名、包结构、注解、继承体系与现有项目一致
- Service 承担业务编排与事务边界
- Manager 负责单表能力与复用性数据访问能力
- Controller 只处理请求转发、参数校验和轻量逻辑
- 不直接把 Entity 暴露给前端

## 开发前检查

1. 业务归属哪个模块，例如 mes、mdm、wms、qms、aps。
2. 是否已有相近领域对象、表结构、接口或 facade 可复用。
3. 是单模块内部能力，还是需要跨服务/跨模块调用。
4. 是否属于标准 CRUD，还是包含树形、状态、编码、租户等特性。
5. 查询参数是否应封装为 Query。
6. 至少查 1 个同模块同类型 Controller/Service/Manager/Mapper/VO/Query 样例；没有样例时写明搜索路径。

## 标准流程

1. 先输出 compliance plan：同域样例、已读规则、修改边界、要证明的规范项和最小验证命令。
2. 再明确建模：Entity、SaveVO、UpdateVO、ResultVO、PageQuery、DTO。
3. 判断父类、接口和特性选择。
4. 先写模型层，再写 Mapper 与 Manager。
5. 再写 Service，明确事务边界。
6. 最后写 Controller。
7. 只有明确跨模块抽象时再评估 Facade。

## 强制约束

- 使用项目既有父类和特性接口
- 使用 JSR-303 校验注解和 Swagger v3 注解
- 查询避免 N+1、循环查库和无分页大查询
- 复杂业务与关键字段需要补中文注释
- 日志使用 SLF4J，禁止 `System.out.println`
- 面向 QMS_PAD 的 BFF Controller 方法名必须带清晰业务语义，避免 `page`、`submit`、`getDetail` 等泛化命名生成 `qms.page`、`qms.submit` 一类歧义前端 API key

## 输出要求

1. 先说明功能所属模块与分层范围。
2. 列出计划新增或修改的类。
3. 说明父类、接口和特性选择依据。
4. 再开始生成代码。
5. 结束前给出自检结果。

自检结果必须包含：同域样例路径、分层边界、事务位置、查询/N+1 风险、Entity 暴露检查、主数据唯一口径检查、测试或未测原因。

## 来源

- 来源：`ifc-mom-column-max/.github/skills/java-backend-development/SKILL.md`
- 本次整理方式：轻改写，保留原执行骨架并改为根目录统一引用
