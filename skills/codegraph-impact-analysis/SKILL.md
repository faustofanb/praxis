---
name: codegraph-impact-analysis
description: Require fresh CodeGraph call-path and blast-radius evidence before editing high-risk code. Use for transactions, locks, FOR UPDATE or raw SQL, concurrency, shared services, public APIs, cross-module flows, schema migrations, high-fanout changes, and any task explicitly asking for callers or impact analysis.
---

# CodeGraph 影响分析

对高风险改动在编辑前执行语义调用链复核。索引初始化成功不等于已经查询过 CodeGraph，
`rg` 命中列表也不能替代调用路径和 Blast Radius 证据。

## Plan Mode 只读调查

investigating 节点遇到跨模块、公共接口、共享服务、高扇出或影响范围问题时应路由本 Skill。
尚未登记需求且没有 worktree binding 时，使用项目画像中已登记仓库的现有索引：

```bash
rtk proxy praxis codegraph investigate <target> \
  --project <project-id> --purpose <明确调查目的> --json
```

该入口不初始化或同步索引，只接受初始化完成、无 pending refs、无 pending changes、路径匹配
的现有索引，返回 HEAD、dirty fingerprint、索引 fingerprint 和 `persisted: false` 临时
scope。临时结果只能支持诊断；进入实施后必须重新在需求工作树 binding 上执行下述正式审计，
不得把 Plan Mode scope 冒充编辑前凭证。

## 编辑前

1. 从 Praxis binding 解析实际仓库工作树，禁止查询主仓库代替需求工作树。
2. 通过 RTK 检查该 binding 的索引状态：

   ```bash
   rtk proxy praxis codegraph status --binding <binding-id> --json
   ```

3. 后台仍在运行时，在首次编辑前等待当前任务结束。`wait` 必须在后台完成后重新校验当前
   工作树，而不是复用旧任务的完成状态：

   ```bash
   rtk proxy praxis codegraph wait --binding <binding-id> --timeout 300 --json
   ```

4. 无论是否等待过，都按 binding 强制同步并核对当前 HEAD 与 dirty fingerprint：

   ```bash
   rtk proxy praxis codegraph ensure-fresh --binding <binding-id> --json
   ```

   只有返回当前工作树 `fresh=true` 才能继续。旧后台任务的 `completed`、`CODEGRAPH_INITED`
   或 `BUILD SUCCESS` 都不是当前索引新鲜度凭证。

5. 使用 CodeGraph MCP 的 `codegraph_explore`，以实际工作树为 `projectPath`，查询准备修改的
   入口、核心方法、调用者和下游依赖。必须保存：

   - 查询问题和关键 symbol；
   - 入口到目标实现的调用路径；
   - Blast Radius 中的调用者、下游文件和建议测试；
   - 索引对应的 HEAD 与 dirty fingerprint。

6. 先依据证据确认修改范围，再开始编辑。仅有 `status fresh=true` 不能作为本 Skill 的完成凭证。

## 编辑后

运行受影响分析并复核新增或改变的调用边：

```bash
rtk proxy praxis codegraph affected --binding <binding-id> --json
```

若变更后的 dirty fingerprint 使索引失效，先同步，再重新执行 `codegraph_explore` 或
`affected`。不得引用修改前的旧 Blast Radius 作为最终证据。

## 回退边界

只有低风险、单文件、无共享调用者的局部任务可以记录 `rg_fallback`。事务、锁、并发、原生
SQL、公共接口、跨模块、结构迁移和高扇出改动在 CodeGraph 不可用时必须阻断并报告原因，
不能静默回退，也不能声称已有语义证据。

## 完成凭证

记录 `binding_id`、`projectPath`、索引指纹、查询、调用路径、Blast Radius、受影响文件、
建议测试、编辑后 `affected` 结果，以及是否使用回退。缺少任一高风险证据时不得完成本 Skill。
