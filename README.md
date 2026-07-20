# Praxis Next

Praxis Next 是平台无关的执行内核、能力包注册表、声明式 profile 系统和薄平台适配器。本分支是 V2 上线前的短期兼容版。

开发入口统一使用 mise：

```bash
mise install
mise run setup
mise run test
mise run smoke
mise run verify
```

## Worktrunk 工作树

Worktrunk 是唯一工作树实现；Praxis 只封装它的 JSON CLI，不直接创建 Git worktree：

```bash
mise install
wt switch --create feature/example --base main
wt list
wt merge
```

`commands/*.toml` 是命令源，`adapters/render.mjs` 为 Codex 与 Claude Code 生成投影。当前 canonical slash commands：

- `/praxis-help`
- `/praxis-check`
- `/praxis-quick`
- `/praxis-start`
- `/praxis-verify`
- `/praxis-setup`
- `/praxis-doctor`
- `/praxis-tolaria-check`

工作树边界：Worktrunk 负责 create/list/remove/merge 与 hooks；Praxis 管理 task、requirement、verification、delivery 和兼容期 profile/capability。

技术栈边界：开发 Praxis Next 工具时只从 mise 进入，mise 下调用 uv + Python；业务检查由 profile/capability 和 `praxis workspace check --json` 决定。

兼容期的 `mom` 与 `aotu` 只继承公共 `manufacturing` profile，并分别声明 delivery 差异。仓库根不再保存 profile 镜像。V2 会删除整个 profile/capability 体系，从真实系统重新生成画像与技能候选。
