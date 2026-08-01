---
name: minimum-module-compile
description: Select and run the smallest safe compile check for changed source code after TDD GREEN. Use for Java/Maven backend modules, Vue/pnpm workspace packages, UniApp targets, Python packages, and other compilable modules before implementation is recorded.
---

# 最小模块编译

在 TDD GREEN 之后编译最小受影响模块，尽早发现语法、类型、依赖解析和条件编译错误。禁止把
这一步自动扩大为全仓构建、发布打包或完整回归。

## 执行顺序

1. 用 `rtk git status --short` 和 `rtk git diff --name-only` 确认变更文件。
2. 从变更文件向上寻找最近的 `pom.xml`、`package.json`、`tsconfig.json` 或 Python 包边界。
3. 读取仓库声明的包管理器精确版本和已有 scripts；禁止猜测脚本名、联网安装或升级依赖。
4. 所有外部命令必须先由 RTK 代理。优先使用 `rtk rg`、`rtk mvn` 等专用子命令；测试用
   `rtk test <原命令>`，只关注错误的编译用 `rtk err <原命令>`，机器 JSON、交互式命令或
   没有专用适配的命令用 `rtk proxy <原命令>` 保留原始输出。保留仓库原生 runner（如
   `uv run` 或精确 pnpm）；RTK 只做代理，不能绕过虚拟环境或包管理器版本。
5. 只有错误能归因于 RTK 自身执行失败（找不到 RTK、spawn/filter/兼容性错误），才允许直接
   命令降级。必须记录原 RTK 命令、RTK 错误和降级命令。子命令返回真实编译或测试失败时不得
   降级重跑，必须按失败处理。
6. 运行一个最小命令。失败时保留完整错误证据并进入系统化调试，不能登记实施完成。
7. Skill outcome 必须记录：项目、模块、精确命令、exit code、结果，以及未执行更大范围命令。

纯文档或不可编译资产变更可以记录 `not_applicable`，但必须附变更文件证据，不能静默跳过。

## Java / Maven 后端

以包含变更源文件的最近叶子 `pom.xml` 为模块边界，从聚合仓库根执行：

```bash
rtk mvn -pl <相对模块路径> -am -DskipTests compile
```

MOM/AOTU 示例：

```bash
rtk mvn -pl lamp-mes-bff/lamp-mes-bff-biz -am -DskipTests compile
```

- 同一变更跨多个叶子模块时，使用逗号连接明确模块，不得退化为无 `-pl` 的根编译。
- 修改测试源码时用 `test-compile`，只编译测试而不执行完整测试：

```bash
rtk mvn -pl <相对模块路径> -am -DskipTests test-compile
```

- 默认禁止 `package`、`install`、`deploy`、全仓 `clean`。只有聚焦编译无法覆盖明确风险且
  获得独立授权时才扩大范围。

### 父 POM 强制跳过测试排查

运行聚焦 Maven 测试前，先检查 effective POM 和父 POM 的自定义跳过属性。MOM/AOTU 仓库可能
默认设置 `ifc.surefire.skip=true` 与 `ifc.surefire.skipTests=true`；这种配置下仅传
`-DskipTests=false` 仍可能只编译测试而不执行测试。用户已授权且目标正是 MOM TPM 聚焦测试时，
使用以下覆盖命令：

```bash
rtk mvn -pl lamp-tpm/lamp-tpm-biz -am \
  -Difc.surefire.skip=false \
  -Difc.surefire.skipTests=false \
  -Dtest=TpmEquipmentRushRepairMessageServiceTest,TpmEquipmentRushRepairUnfinishedMessageJobTest \
  -Dsurefire.failIfNoSpecifiedTests=false test
```

原因是两个父 POM 属性同时关闭 Surefire 跳过开关，`-Dtest` 将执行范围限制为原定的两个
聚焦用例，`-Dsurefire.failIfNoSpecifiedTests=false` 避免某个聚合模块不持有指定用例时产生
误报。必须记录完整命令、实际执行模块和 exit code；如果输出显示没有测试被执行，不得把结果
写成测试通过。Web 管理端获批的最小类型检查仍使用
`rtk err pnpm --filter @vben/web-antd run typecheck`，并单独记录其环境依赖。

## Vue / pnpm 前端

读取根 `package.json#packageManager`、最近 package 的 `name` 和 scripts。优先执行 package
自己的类型编译，不运行整个 Turbo workspace：

```bash
rtk err pnpm --filter <package-name> run typecheck
```

MOM/AOTU 管理端的最小默认命令：

```bash
rtk err pnpm --filter @vben/web-antd run typecheck
```

只有改动涉及 Vite 打包、资源解析、环境变量或插件时，才在独立授权下升级为：

```bash
rtk err pnpm --filter @vben/web-antd run build
```

共享 package 没有 `typecheck` 时，优先使用其已声明的 `build`；两者都没有时停止并要求登记
项目命令，不得自动执行根级 `pnpm build` 或 `turbo build`。

## UniApp

UniApp 通常是单 package，最小通用语法和 Vue 类型编译为：

```bash
rtk err pnpm run type-check
```

若变更涉及条件编译、`manifest.config.ts`、`pages.config.ts`、原生插件或平台 API，还必须选择
一个真实目标构建。先读取 scripts，再按当前项目和目标选择：

| 项目/目标 | 建议命令 |
|---|---|
| MOM MES_PDA 通用 H5 | `rtk err pnpm run build:h5` |
| MOM MES_PDA App Android | `rtk err pnpm run build:app-android` |
| AOTU MES_PDA 默认开发 H5 | `rtk err pnpm run build:dev:h5` |
| AOTU MES_PDA 默认开发 Android | `rtk err pnpm run build:dev:app-android` |
| AOTU 五金环境 | 选择已声明的 `build:wj:dev[:app-android]` |
| AOTU 弹簧环境 | 选择已声明的 `build:th:dev[:app-android]` |
| 微信/支付宝等小程序 | 选择 package 中已声明的对应 `build:*:mp-*` |

不得用 H5 成功代替 App 或小程序条件分支验证，也不得同时构建所有平台。没有匹配 script 时
停止并报告缺项。

## Python

对最小受影响 package 执行语法编译：

```bash
rtk err python -m compileall -q <package-path>
```

存在 `uv.lock` 或项目由 uv 管理时，必须保留 uv runner：

```bash
rtk err uv run --no-sync python -m compileall -q <package-path>
```

沙箱禁止用户级 uv 缓存时显式传入当前任务的可写缓存：

```bash
rtk err env UV_CACHE_DIR=<writable-uv-cache> uv run --no-sync \
  python -m compileall -q <package-path>
```

不要把整个虚拟环境或仓库加入 `compileall`。

## 完成凭证示例

```text
project=backend; module=lamp-mes-bff/lamp-mes-bff-biz;
command=rtk mvn -pl lamp-mes-bff/lamp-mes-bff-biz -am -DskipTests compile;
exit code=0; result=passed; broader_checks=not_run
```
