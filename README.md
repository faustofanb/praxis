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

CLI output has two deliberate modes. Human output is compact by default for high-volume route,
context, portrait, requirement, and artifact commands. Use `--summary` for the same compact
single-line JSON, or `--json` for the complete stable result envelope. State, audit records, and MCP
results are never truncated.

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

praxis domain upsert \
  --system ifc-mom \
  --id metal-balance \
  --name "金属平衡" \
  --objective "统一金属投入与产出口径" \
  --responsibility "维护跨工序平衡规则" \
  --entity "金属批次" \
  --process "投入 → 工序流转 → 产出复核" \
  --rule "统计必须限定当前租户" \
  --interface "金属平衡报表 API" \
  --owner "制造运营团队" \
  --json
```

`praxis.toml` stores workspace and system facts. Chinese Markdown/YAML under `知识库/` stores authoritative human knowledge. SQLite at `.praxis/workspace.db` stores requirement state, Outbox projection work, runtime state, and the audit hash chain.

Requirement directories use `<REQ-ID>__<short-name>` and documents use stable numeric prefixes.
Existing workspaces migrate legacy names idempotently with:

```bash
praxis repair requirement-layout --json
```

The repair stops on content conflicts instead of overwriting either copy. Artifact registration
archives an independently hashed snapshot under the requirement's `产出物/` directory; source-path
drift is reported separately and does not invalidate the archived delivery evidence.
Pre-V2 artifact records remain verifiable from their original source and can be explicitly
backfilled without changing successful registrations:

```bash
praxis repair artifact-archives --requirement REQ-20260723-001 --json
```

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

### Small-fix lane

An existing requirement can use the bounded small-fix profile without recreating the standard
development workflow:

```bash
praxis fix start REQ-20260720-001 --repository wms-pda --small --json
# edit only the bounded business files in the returned worktree
praxis fix finish REQ-20260720-001 \
  --test "pnpm vitest run src/views/example/mapping.test.ts" \
  --json
```

`fix start` fetches and resolves the configured template branch to a commit, then creates the
isolated worktree directly from that fixed revision. It does not switch, clean, or merge the root
repository or a template worktree. A verifying requirement is reopened; a ready requirement enters
development.

`fix finish` remains eligible only for one repository, one to three tracked business files, at most
80 added-plus-deleted lines, and no database, migration, API-contract, permission, generated-code,
transaction, concurrency, lock, or shared-component changes. It runs exactly one focused test,
`git diff --check`, and one configured type check. A type-check command containing the standalone
`{files}` argument receives only the changed business files:

```toml
typecheck_commands = ["pnpm exec vue-tsc --noEmit {files}"]
```

Without `{files}`, Praxis caches diagnostics for the fixed template revision and blocks only newly
introduced diagnostics. A missing baseline is reported as inconclusive, never as an incremental
pass. Successful finish records one `code-change` artifact for the complete Git diff and records
implementation; it does not commit, push, run a full build/test suite, invoke a reviewer, or mark
the requirement completed. Governance time above two minutes or twice the coding window is returned
as a warning.

### Risk-driven fast fix

When the root cause is already known and the change is limited to one tracked business file with an
annotation, null guard, condition, or parameter adjustment, finish the work without expanding the
standard verification workflow:

```bash
praxis fix record REQ-20260720-001 \
  --file WmsStocktakingDiffRecordMapper.java \
  --verification declined \
  --reason "用户要求单注解快速修复" \
  --command-count 2 \
  --elapsed-seconds 90 \
  --json
```

`fix record` does not run tests, compilation, full type checking, review, commit, or push. It checks
that exactly one non-risk business file changed, derives or accepts one of
`annotation|null_guard|condition|parameter`, records the omitted verification, creates one
`code-change` artifact, and records implementation in a single application operation. A direct
check can be recorded with `--verification direct --risk ... --evidence ...` without claiming that
tests passed.

Evidence is keyed by the active worktree binding, HEAD, repository-relative target path, and file
fingerprint, so an exact retry reuses the existing receipt and artifact. Micro fixes allow up to two
commands and target two minutes; the fast-fix hard stop is five commands or three minutes. A soft
budget overrun requires `--new-risk-justification`; the hard stop cannot be overridden.

The generated `AGENTS.md` and `CLAUDE.md` managed block requires every command to name the risk it
reduces and the decision changed by success or failure. It also forbids reflection tests for
annotations, source-reading or source-regex pseudo-tests, and tests that only assert one helper
calls another. If the real check requires Spring, MyBatis, or a database and the user chooses
`fast_fix`, record the omitted integration verification instead of creating a substitute test.

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
praxis worktree status --binding WT-REQ-20260720-001--backend --json
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
Removing a bound worktree first cancels that worktree's background graph process, then verifies and,
if necessary, explicitly deletes the exact bound branch. It never trusts Worktrunk's cleanup claim
without a Git ref check.
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

Plan Mode can inspect an already valid project index without a requirement or binding:

```bash
praxis codegraph investigate OrderService --project backend \
  --purpose "trace the cross-module save flow" --json
```

This command never initializes or synchronizes the index and returns a `persisted: false` scope.
It does not replace the binding-scoped impact audit required before high-risk edits.

## Portraits, runtime, and DBX

Static portraits never execute deployment or database commands. Runtime inspection is opt-in and
requires an explicit witr target. The generated portrait includes repository scope and structure,
engineering entrypoints, interface surfaces, data/configuration assets, quality commands, delivery,
runtime, CodeGraph, and evidence:

```bash
praxis portrait scan --project backend --json
praxis portrait scan --project backend --runtime-port 8080 --json
praxis portrait show --project backend --json
praxis portrait diff --project backend --json
praxis portrait verify --project backend --json
```

Projects store DBX references such as `dbx://ifc-mom-dev`, never credentials. Connection listing and
queries use DBX MCP directly; Praxis does not invoke the DBX CLI. Writes require `--approve-write`;
Praxis still blocks DDL, multiple statements, locking reads, unconditional updates/deletes, and
every production write:

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
SkillDock, shared Agent, and Claude Skill directories and records the selected `SKILL.md` path and
content hash.
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

Context compilation keeps original requirements, exact project and database connection facts,
active constraints, verification receipts, task stage, modification scope, and gates as P0 facts.
Database facts do not depend on a portrait and require an explicit registered connection plus a
`select current_database()` precheck. Optional portrait/analysis/skill fragments are fitted to the
remaining budget. `worktree ensure` builds coder bundles automatically; `agent start` can infer the
project from its binding when `--context` is omitted and launches with an explicit handoff/context
reading prompt:

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

Kimi Code CLI picks up the project-level gateway and workflow guidance directly:
`.kimi-code/mcp.json` declares the same `praxis` MCP server for new Kimi sessions, and the
bootstrap-generated root `AGENTS.md` supplies the Praxis workflow rules Kimi reads as workspace
instructions. `--type kimi` / `--agent kimi` is accepted by `agent install`, `agent start`
and `agent launch`; `agent render` writes `kimi.json` with `PostToolUse`/`Stop` hooks that
audit tool completion and close the session through `praxis lifecycle`.

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
Use `--type code-change` for source changes; Praxis captures the Git repository, branch, diff totals,
and hashes of changed files in structured metadata.

WITR is also opt-in through `praxis runtime diagnose`. Commands execute once: uncompressed,
secret-redacted output is retained under `.praxis/raw-logs/`, while RTK filters only the copy returned
to human/Agent contexts. Machine JSON bypasses RTK. Ponytail is a routed workflow Skill and emits only
non-blocking diff-growth guidance.
