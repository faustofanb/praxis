---
name: local-test-override
description: '用于 IFC MOM 后端在本地开发分支临时开启 Maven 测试并验证指定模块或指定测试类。适用于父 POM 默认跳过 surefire、需要只在本地显式运行单测、验证 controller/module 级测试时使用。'
user-invocable: true
---

# Local Test Override

用于 `ifc-mom-column-max` 的本地测试覆盖说明。

## 适用场景

- 项目默认跳过测试，但需要本地临时开启
- 只想验证某个模块或某个测试类
- 需要避免把临时测试改动或试验配置推送到远端

## 背景

当前项目父 POM 默认跳过测试，但可以通过 Maven 属性在本地显式开启。

对应属性：

- `-Difc.surefire.skip=false`
- `-Difc.surefire.skipTests=false`

## 使用原则

1. 默认只在本地开发分支使用。
2. 优先跑最小范围：指定模块、指定测试类。
3. 目标模块依赖上游模块产物时优先带 `-am`。
4. 使用 `-Dtest=...` 且带 `-am` 时，通常补 `-Dsurefire.failIfNoSpecifiedTests=false`。

## 常用命令模板

### 只编译某模块

```bash
mvn -pl <module-path> -am -DskipTests compile
```

### 本地显式开启某模块所有测试

```bash
mvn -pl <module-path> -am -Difc.surefire.skip=false -Difc.surefire.skipTests=false test
```

### 本地显式运行某个测试类

```bash
mvn -pl <module-path> -am \
  -Dtest=<TestClassName> \
  -Dsurefire.failIfNoSpecifiedTests=false \
  -Difc.surefire.skip=false \
  -Difc.surefire.skipTests=false \
  test
```

## 不建议推送的内容

- 临时测试类
- 为了本地测试而加的试验性 mock 代码
- 只服务本地验证的测试配置

## 输出要求

回答本地测试问题时优先给出：

1. 当前模块路径
2. 是否需要 `-am`
3. 是否需要 `-Dtest=...`
4. 是否需要 `-Dsurefire.failIfNoSpecifiedTests=false`
5. 最终完整命令

## 来源

- 来源：`ifc-mom-column-max/.github/skills/local-test-override/SKILL.md`
- 本次整理方式：轻改写，保留原命令模板和使用原则
