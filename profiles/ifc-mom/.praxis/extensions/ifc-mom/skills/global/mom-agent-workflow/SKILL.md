---
name: mom-agent-workflow
description: Use when coordinating IFC MOM work through role-based agents, optimizing platform-neutral workflow responsibilities, dispatching requirement/execution/quality/delivery roles, or reducing main conversation context load.
user-invocable: true
---

# MOM Agent Workflow

## Core Rule

Use role-based agents as workflow responsibilities, not as new runtime agent types. When the current platform offers subagent/task delegation, the dispatched prompt must explicitly assign one of these MOM roles and follow that role contract.

The current direct user conversation is the Main Agent by default. Treat a conversation as a non-main role only when the input explicitly says it is a delegated `role_agent=requirement|execution|quality|delivery` task.

## Controlled Development Boundary

- Tester/Quality 只能作为选项；风险阈值只能触发建议，不能触发自动测试、独立复核或门禁。
- 只有得到用户明确许可后才能派发 Tester/Quality；许可前由 Main Agent 停在编码和代码级检查，并报告未执行项。
- 浏览器、桌面/电脑控制、管理页面、登录态、外部系统联调和发布不属于默认验证范围。

## Runtime-Neutral Capability Routing

Treat delegation as a platform capability, not a model-vendor decision. Use the current runtime's available subagent/task mechanism when it exists and the work is genuinely independent; otherwise the Main Agent executes the role contract serially in the current conversation.

Treat "agent choice" as a routing and evidence decision:

| Lane | Use For | Avoid For |
| --- | --- | --- |
| Main Agent | routing, requirement truth, risk decisions, write-lock ownership, final integration, final answer | bulk source reading, long logs, wide discovery when a read-only delegation capability is available |
| Explore / read-only worker | read-only candidate discovery, same-domain examples, config inventory, long-log root-cause extraction | architectural decisions, code edits, final review conclusions |
| Execution worker | scoped implementation with explicit write locks and verification command | ambiguous requirements, shared-contract changes before the contract owner exists |
| Tester role | focused behavior tests and critical-path assertions | restating implementation details, broad low-signal coverage |
| Reviewer / Quality role | independent diff, SQL, migration, permission, concurrency and verification review | trivial typo fixes, deterministic formatting, unchanged files |
| Tool-only path | dbx schema lookup, LSP references, Code Graph query, grep/glob/read, task verify | asking a model to infer facts available from tools |

Default policy: use tools before agents, use one Main Agent coordinator, spawn workers only when they reduce missed-context risk or isolate independent work, and never hard-code vendor, model, or subscription assumptions. If a task is answer-only, deterministic, below the low-risk threshold, or the runtime has no delegation capability, record `subagent: waived-small-change` or `subagent: unavailable-runtime` instead of fabricating a worker.

## Cost and Context Guardrails

- Do not duplicate the full main conversation into workers.
- Do not spawn speculative workers before target project, requirement boundary,
  数据口径, and read/write sets are known.
- Prefer `explore` or read-only worker for large discovery; reserve editing
  workers for known files and known write locks.
- Prefer tool calls over model calls for schema, references, search, status,
  validation, and command output.
- After user permission, recommend a Quality worker when risk or diff size justifies independence:
  SQL/migration/report 数据口径, permissions, async/concurrency, shared modules,
  production delivery, diff over 300 lines, or more than one project.
- For small single-project changes touching at most three files and no SQL,
  migration, permission, async, shared module or production-data risk, Main may
  execute directly and must state the waiver reason.


## Roles

- Main Agent: owns routing, context budget, locks, user confirmations, and final decisions.
- Requirement Agent: owns requirement preservation, decomposition, evidence, database investigation planning, and acceptance criteria.
- Execution Agent: owns scoped source investigation, implementation, and local task verification.
- Quality Agent: when explicitly authorized, owns independent code review, verification-log review, and SQL/migration review.
- Delivery Agent: owns finish/gate-ready/deliver/cleanup readiness, but never bypasses explicit user confirmation.

Read only the role reference needed for the current stage:

- Main Agent: `references/main-agent.md`
- Requirement Agent: `references/requirement-agent.md`
- Execution Agent: `references/execution-agent.md`
- Quality Agent: `references/quality-agent.md`
- Delivery Agent: `references/delivery-agent.md`

## Specialty Skills

Load these only when the task triggers them:

- Command contract drift: `.praxis/extensions/ifc-mom/skills/global/mom-praxis-command-contract/SKILL.md`
- Database investigation: `.praxis/extensions/ifc-mom/skills/global/mom-database-investigation/SKILL.md`
- Delivery branch hygiene: `.praxis/extensions/ifc-mom/skills/global/mom-delivery-branch-hygiene/SKILL.md`
- Frontend pattern search: `.praxis/extensions/ifc-mom/skills/global/mom-frontend-pattern-search/SKILL.md`
- Context budgeting: `.praxis/extensions/ifc-mom/skills/global/mom-context-budgeting/SKILL.md`

## Stage Map

| Stage | Owner | Gate |
| --- | --- | --- |
| Intake and routing | Main Agent | Task type, project, docs/worktree/database/subagent decision is explicit |
| Requirement analysis | Requirement Agent | Requirement evidence and acceptance criteria are written or summarized |
| Planning and implementation | Execution Agent | Write locks, changed files, and verification commands are clear |
| Review and verification | Main Agent or authorized Quality Agent | Findings and verification evidence are available |
| Delivery closeout | Main Agent or authorized Delivery Agent | Readiness is audited; action execution waits for explicit user confirmation |

## Dispatch Template

```text
role_agent: <requirement|execution|quality|delivery>
runtime_agent_type: <explorer|worker|default>
task_id: <stable id>
goal: <one-sentence completion condition>
scope: <allowed projects, directories, files>
inputs: <requirement dir, latest stage file, context output, rule paths, verification results>
locks:
  write: <exclusive write paths or none>
  read: <read-only paths>
no_nested_agents: true
output_contract: <required structured result>
```

## Operating Constraints

- Main Agent should not load source, long logs, or full diffs when a role agent can return a compressed result.
- Main Agent is the current main conversation and is not dispatched through `role_agent`.
- Main Agent 默认直接执行；只有用户明确要求并行，或主对话无法可靠完成的独立高风险工作，才派发 role-agent/subagent。
- Requirement and Quality agents are read-only by default.
- Execution agents must own explicit write paths and must not change files outside the lock.
- Delivery agents may prepare commands and readiness conclusions, but commit, push, cherry-pick, deliver, cleanup, branch deletion, and worktree deletion still require explicit user confirmation.
- Any role agent that needs further splitting returns `BLOCKED` or `CHECKPOINT`; it must not dispatch nested agents.

## Result Status

- `PLAN`: intended approach, risks, commands, and document/write targets.
- `CHECKPOINT`: partial finding or decision needed from the Main Agent.
- `RESULT`: completed work with evidence, paths, validation, and residual risk.
- `BLOCKED`: concrete blocker and the smallest decision or external action needed.
