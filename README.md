# Praxis V3

Praxis V3 is a local-first, Git-native workflow governance and business knowledge platform for bounded AI-assisted development. The CLI and MCP gateway call the same Python application service and return the same result envelope.

V3 evolves the validated V2 integrations into a requirement-centered lifecycle with Chinese knowledge assets, SQLite state and audit, code gates, minimal context, and thin multi-Agent adapters. The V2 baseline remains documented in [the V2 blueprint](docs/praxis-v2-blueprint.md).

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
praxis init \
  --workspace-id ifc-mom-praxis \
  --name "IFC-MOM开发工作空间" \
  --json

praxis system add \
  --id ifc-mom \
  --name "IFC-MOM制造运营系统" \
  --domain metal-balance \
  --json

praxis workspace add \
  --system ifc-mom \
  --id backend \
  --name "后端服务" \
  --kind backend \
  --path services/backend \
  --test-command "pytest -q" \
  --json

praxis requirement new \
  --name "金属平衡块复制" \
  --request "保留的用户原始需求" \
  --system ifc-mom \
  --domain metal-balance \
  --json
```

`praxis.toml` stores workspace and system facts. Chinese Markdown/YAML under `知识库/` stores authoritative human knowledge. SQLite at `.praxis/workspace.db` stores requirement state, Outbox projection work, runtime state, and the audit hash chain.

## Worktrunk and CodeGraph

Worktrunk is the only worktree implementation:

```bash
praxis worktree create REQ-20260720-001 --repository backend --stage backend --json
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

## Portraits, runtime, and DBX

Static portraits never execute deployment or database commands. Runtime inspection is opt-in and
requires an explicit witr target:

```bash
praxis portrait scan --project backend --json
praxis portrait scan --project backend --runtime-port 8080 --json
praxis portrait show --project backend --json
praxis portrait diff --project backend --json
praxis portrait verify --project backend --json
```

Projects store DBX references such as `dbx://ifc-mom-dev`, never credentials. Connection listing and
read queries use the documented DBX JSON CLI. Writes require `--approve-write`; Praxis still blocks
DDL, multiple statements, locking reads, unconditional updates/deletes, and every production write:

```bash
praxis database connections --project backend --json
praxis database query --project backend --connection dbx://ifc-mom-dev --sql "select 1" --json
```

## Skills

Skill routing, provenance, license, version, content hash, required tools, risk, and context budget are code-managed:

```bash
praxis skill route "核对数据库表结构" --json
praxis skill search "生产报表" --json
praxis skill import --source ../legacy-skills --system ifc-mom --json
praxis skill dedupe --json
praxis skill verify --json
praxis skill inspect dbx-database-investigation --json
praxis skill candidate --project backend --json
praxis skill approve business.ifc_mom.backend.development \
  --catalog-root ./skills --yes --json
```

The `dbx-database-investigation` Skill supplies the investigation workflow; the database service owns
connection registration, authorization, SQL safety, execution, and audit.

## Minimal context bundles

Context compilation keeps original requirements, task stage, modification scope, and gates as P0
facts. It then deduplicates, redacts, ranks, fits optional portrait/analysis/skill fragments to the
budget, and persists a source manifest and fingerprint:

```bash
praxis context build \
  --requirement REQ-20260720-001 \
  --project backend \
  --stage backend \
  --agent-role coder \
  --allow-path 'src/**' \
  --allow-path 'tests/**' \
  --json
praxis context show CTX-20260720T152000-1234ABCD --json
```

## MCP and platform adapters

```bash
praxis mcp list --json
praxis mcp grant \
  --session SES-20260720T152000-A1B2C3D4 \
  --role coder \
  --requirement REQ-20260720-001 \
  --worktree req/REQ-20260720-001/02-backend \
  --capability requirement.read \
  --capability artifact.register \
  --json
praxis mcp serve
```

The official MCP Python SDK exposes canonical Praxis tools and resources. Unscoped generic execution
is read-only; state changes pass through session grants. Workspace writes require requirement/worktree
binding, external writes require explicit approval, and destructive capabilities are denied. Agent
configs are generated from the same session:

```bash
praxis agent install --agent codex --json
praxis agent start \
  --type codex \
  --role coder \
  --requirement REQ-20260720-001 \
  --context CTX-20260720T152000-1234ABCD \
  --worktree req/REQ-20260720-001/02-backend \
  --capability requirement.read \
  --json
praxis agent render SES-20260720T152000-A1B2C3D4 --json
praxis agent launch SES-20260720T152000-A1B2C3D4 --json
praxis agent sessions --json
```

`agent launch` prepares and audits a no-shell launch descriptor by default. Supplying `--execute`
explicitly starts the installed executable in the bound worktree, records its PID, and writes output
to `.praxis/raw-logs/`.

`.codex-plugin` and `.claude-plugin` expose the same gateway. Oh My Pi can install the repository as a local Pi package:

```bash
pi install /absolute/path/to/praxis-next
# then use /praxis workspace inspect in Pi
```

Its package manifest exposes the shared Skills and a thin `/praxis` CLI command; business behavior stays in Python.

Requirement artifacts and the append-only audit chain are independently verifiable:

```bash
praxis artifact add --requirement REQ-20260720-001 \
  --type test-report --source ./report.txt --stage verify --json
praxis artifact list --requirement REQ-20260720-001 --json
praxis audit list --json
praxis audit verify --json
```

WITR is also opt-in through `praxis runtime diagnose`. Commands execute once: uncompressed,
secret-redacted output is retained under `.praxis/raw-logs/`, while RTK filters only the copy returned
to human/Agent contexts. Machine JSON bypasses RTK. Ponytail is a routed workflow Skill and emits only
non-blocking diff-growth guidance.
