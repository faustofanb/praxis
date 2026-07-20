# Praxis V2

Praxis V2 is a clean-room, code-owned workflow kernel for bounded AI-assisted business development. It is a Python modular monolith: the CLI and MCP gateway call the same application service and return the same result envelope.

V2 contains no V1 profile, capability, extension, Rule runtime, migration layer, legacy module, `task` shim, Orca integration, or MOM/AOTU/IFC-MOM knowledge. The complete design contract is in [the V2 blueprint](docs/praxis-v2-blueprint.md).

## Development

```bash
mise install
mise run setup
mise run verify
uv run praxis version --json
```

The locked toolchain includes Worktrunk, uv, ruff, ty, pytest, coverage, xdist, Hypothesis, pre-commit, and pip-audit.

## Workspace and requirements

```bash
praxis workspace init \
  --workspace-id aotu \
  --product-family ifc-manufacturing \
  --project backend:java-maven:../backend:main \
  --json

praxis workspace bootstrap --json
praxis requirement create \
  --id REQ-42 \
  --title "优化工序报表" \
  --request "保留的用户原始需求" \
  --tag manufacturing \
  --json
```

`praxis.toml` stores workspace and project facts. Tolaria-compatible Markdown in the configured vault stores Requirement, RequirementSection, BusinessDomain, system portrait, and artifact context. SQLite under `.praxis/` stores runtime state, freshness, locks, and audit records only.

## Worktrunk and CodeGraph

Worktrunk is the only worktree implementation:

```bash
praxis worktree create feature/example --base main --json
praxis worktree list --json
praxis worktree install-hooks --project backend --json
praxis worktree merge main --json       # run inside the source worktree
praxis worktree remove feature/example --json
```

Installed hooks enforce the CodeGraph lifecycle at post-start, pre-merge, post-merge, and post-remove. Task/context, preflight, verify, and every graph query also call `ensure-fresh`. Freshness includes Git HEAD plus staged, unstaged, and untracked content. A failed sync blocks graph use; a simple task may explicitly allow an `rg` fallback, but never reads a stale graph.

```bash
praxis codegraph status --project backend --json
praxis codegraph ensure-fresh --project backend --initialize --json
praxis codegraph query OrderService --project backend --json
praxis codegraph affected --project backend --json
```

## Skills and DBX

Skill routing, provenance, license, version, content hash, required tools, risk, and context budget are code-managed:

```bash
praxis skill route "核对数据库表结构" --json
praxis skill inspect dbx-database-investigation --json
praxis skill candidate --project backend --json
praxis skill approve backend-development --catalog-root ./assets/skills --yes --json
```

DBX is deliberately not integrated as a Praxis service. Praxis does not start, proxy, configure, or store DBX MCP connections or secrets and has no `praxis dbx` command. The read-only `dbx-database-investigation` Skill checks external DBX tools and connection configuration when it runs.

## MCP and platform adapters

```bash
praxis mcp serve
```

The official MCP Python SDK exposes the shared service plus fresh CodeGraph read operations and `praxis://skills/{type}/{id}` resources. `.codex-plugin` and `.claude-plugin` expose the same gateway. Oh My Pi can install the repository as a local Pi package:

```bash
pi install /absolute/path/to/praxis-next
# then use /praxis workspace inspect in Pi
```

Its package manifest exposes the shared Skills and a thin `/praxis` CLI command; business behavior stays in Python.

WITR is opt-in through `praxis runtime diagnose`. RTK wraps human shell output only; machine JSON bypasses it. Ponytail is a routed workflow Skill and emits only non-blocking diff-growth guidance.
