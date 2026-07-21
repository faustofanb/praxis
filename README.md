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
  --default-branch local \
  --template-branch develop \
  --local-file "apps/web-antd/.env.development" \
  --worktree-setup-command "pnpm install --offline --frozen-lockfile" \
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

`praxis workspace bootstrap` generates or refreshes the Praxis-managed blocks in root-level
`AGENTS.md` for Codex and `CLAUDE.md` for Claude Code. Text outside
`<!-- praxis:managed:start/end -->` is preserved. Existing workspaces can refresh only these files,
without CodeGraph, database discovery, or Skill promotion side effects:

```bash
praxis workspace guidance --json
```

Creating a requirement writes its knowledge documents immediately but does not create a worktree.
Investigation and planning stay in the knowledge vault. Create an isolated worktree only after the
plan confirms that code must change, and always before the first code edit.
If validation reveals more development work, use the audited rollback instead of routing through a
synthetic blocked state:

```bash
praxis requirement reopen REQ-20260720-001 --reason "validation found missing behavior" --json
```

## Worktrunk and CodeGraph

Worktrunk is the only worktree implementation:

```bash
praxis worktree create REQ-20260720-001 --repository backend --stage backend --json
praxis worktree preview REQ-20260720-001 --repository backend --repository web --json
praxis worktree ensure REQ-20260720-001 --repository backend --repository web \
  --confirm WTP-20260721T120000-1234ABCD --json
praxis worktree prepare REQ-20260720-001 --repository web --json
praxis worktree migrate-name REQ-20260720-001 --repository backend --json
praxis worktree list --json
praxis worktree install-hooks --project backend --json
praxis worktree merge main --json       # run inside the source worktree
praxis worktree remove feature/example --json
```

`default_branch` is the persistent local branch that keeps local runtime configuration.
`template_branches` must contain exactly one upstream development or release branch. Before Praxis
creates a requirement worktree, it fetches that branch from `origin`, merges it into the clean local
default branch in the worktree that owns that branch, and then creates the requirement branch from
the updated local default. If the local branch is not checked out, Worktrunk creates a stable template
worktree for it; Praxis never switches the user's current branch for synchronization. Fetch failures,
merge conflicts, dirty template worktrees, and ambiguous template configuration block creation
instead of falling back to another base.

Requirement workspaces keep the aggregate directory and make both Fork-visible names readable:

```text
.worktrees/REQ-20260721-003__汽车件简单时效MES_PDA/
└── REQ-20260721-003__汽车件简单时效MES_PDA__web

praxis/REQ-20260721-003__汽车件简单时效MES_PDA
```

The first generated display slug is persisted in `worktree_group`, so a later requirement-title
rename does not silently move paths or branches. Internal identity remains
`WT-<requirement-id>--<repository-id>`. Existing bindings with legacy names must use
`worktree migrate-name`; create fails closed with `WORKTREE_NAME_MIGRATION_REQUIRED`. Migration
moves the Git worktree, renames the branch, rewrites affected artifact source paths, restores the
binding to `active`, and queues CodeGraph for the new path. Git/path failures compensate back to the
old name; a background graph failure does not invalidate an otherwise usable Git worktree.
The binding remains `migrating` for the full operation and persists its old path, branch, and
status. Re-running the same migration command after a process interruption compensates back to the
old name and rebuilds CodeGraph there before normal creation can continue.

Repositories may declare ignored local runtime files explicitly. Praxis copies only these paths
from the configured main repository into a newly created requirement worktree before CodeGraph
initialization; it never scans `.env*` or copies undeclared files. Paths must be normalized,
repository-relative files and cannot resolve outside either repository:

```toml
local_files = ["apps/web-antd/.env.development"]
worktree_setup_commands = ["pnpm install --offline --frozen-lockfile"]
```

Worktree creation performs only a fast setup preflight and leaves configured dependency installation
deferred. `worktree prepare` runs the configured commands on first build as parsed argument vectors.
It does not invoke a shell, infer an undeclared package manager, or retry a failed offline command with
network access. Command output and environment values are never written to the binding or audit log.
When an explicit command starts with `pnpm`, Praxis reads the repository root
`package.json#packageManager`, resolves that exact pnpm version from PATH or an already-installed pnpm
tool cache, and executes the resolved binary. It never downloads a missing pnpm version. A missing,
invalid, mismatched, or unavailable declaration blocks setup, and a declaration change invalidates the
setup fingerprint.

Git isolation, local-file preparation, and an active binding are the synchronous development boundary.
CodeGraph is queued in a detached worker and exposes persisted status, PID, duration, and log path.
Normal investigation uses `rg`; semantic operations may explicitly wait for the graph:

```bash
praxis codegraph wait --project backend --timeout 30 --json
praxis codegraph run-pending --project backend --binding WT-REQ-20260720-001--backend --json
```

Installed hooks enforce worktree binding, changed-path and secret gates plus the CodeGraph lifecycle
at post-start, pre-commit, pre-merge, post-merge, and post-remove. They never start lint, format, typecheck,
quality review, or tests. Those actions require explicit user approval for the named scope. Task/context,
preflight, verify, and every graph query also call `ensure-fresh`. Freshness includes Git HEAD plus
staged, unstaged, and untracked content. A failed sync blocks graph use; a simple task may explicitly
allow an `rg` fallback, but never reads a stale graph.

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

Node routing combines workflow node, intent, system, business domain, repository kind, Agent role,
risk, artifact type, installed providers, current approvals, and context budget. It distinguishes
required, conditional, approval-required, unavailable, and budget-omitted providers:

```bash
praxis skill route-node \
  --node investigating \
  --requirement REQ-20260721-001 \
  --project backend \
  --agent-role investigator \
  --intent "调查 SQL 缺陷并定位影响范围" \
  --json
praxis skill invoke brainstorming \
  --requirement REQ-20260721-001 --node investigating --json
praxis skill complete SKI-20260721T120000-1234ABCD --json
praxis skill gate --requirement REQ-20260721-001 --node investigating --json
praxis skill complete-node --requirement REQ-20260721-001 --node investigating \
  --project backend --used-skill brainstorming="方案已确认" \
  --used-skill grilling="边界已确认" --used-skill ponytail="复用现有能力" --json
```

`skill.route_planned`, `skill.invoked`, and `skill.completed` are distinct audit events. A command
history or a routed context fragment is not invocation evidence. Requirement transitions and
`worktree create` fail closed when the current node has no route or completed gate evidence, and
every gate outcome is audited. Tests, quality review, reviewer or
tester Agents, subagents, verification, and branch-finishing Skills remain pending until the user
explicitly approves the current scope. Bootstrap reports missing external providers and never
installs them automatically. The router discovers installed providers in the standard Codex,
shared Agent, and Claude Skill directories and records the selected `SKILL.md` path and content hash.
Identical node inputs reuse a route fingerprint; reuse never manufactures invocation or approval
evidence. Direct user authorization can be recorded once for an exact validation matrix, while
evidence, recovery, and retry loops use explicit per-stage budgets:

```bash
praxis approval grant --requirement REQ-20260721-001 --scope verification \
  --entry "uv run pytest -q" --user-evidence "user message id" --authorized-by-user --json
praxis budget consume --requirement REQ-20260721-001 --node in_progress \
  --kind retry --operation-key worktree:web --json
```

The `dbx-database-investigation` Skill supplies the investigation workflow; the database service owns
connection registration, authorization, SQL safety, execution, and audit.

## Minimal context bundles

Context compilation keeps original requirements, task stage, modification scope, and gates as P0
facts. It then deduplicates, redacts, ranks, fits optional portrait/analysis/skill fragments to the
budget, and persists a source manifest and fingerprint:

Subagent sessions default to `fork_turns=none`, render a compact `handoff.json`, and treat the parent
session as the single writer for requirement transitions and Skill gates. A child returns a bounded
parent receipt containing changed paths, decisions, blockers, and requested follow-up.

```bash
praxis context build \
  --requirement REQ-20260720-001 \
  --project backend \
  --stage backend \
  --agent-role coder \
  --workflow-node in_progress \
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

`artifact add` is an upsert keyed by requirement plus normalized source path. Re-adding a modified
file preserves its artifact ID and creation time while refreshing hash, size, stage, and metadata.

WITR is also opt-in through `praxis runtime diagnose`. Commands execute once: uncompressed,
secret-redacted output is retained under `.praxis/raw-logs/`, while RTK filters only the copy returned
to human/Agent contexts. Machine JSON bypasses RTK. Ponytail is a routed workflow Skill and emits only
non-blocking diff-growth guidance.
