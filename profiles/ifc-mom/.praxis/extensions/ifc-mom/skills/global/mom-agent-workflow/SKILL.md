---
name: mom-agent-workflow
description: Use when coordinating IFC MOM work through role-based agents, optimizing Codex workflow responsibilities, dispatching requirement/execution/quality/delivery agents, or reducing main conversation context load.
user-invocable: true
---

# MOM Agent Workflow

## Core Rule

Use role-based agents as workflow responsibilities, not as new runtime agent types. Codex may still dispatch `explorer` or `worker`; the dispatched prompt must explicitly assign one of these MOM roles and follow that role contract.

The current direct user conversation is the Main Agent by default. Treat a conversation as a non-main role only when the input explicitly says it is a delegated `role_agent=requirement|execution|quality|delivery` task.

## Roles

- Main Agent: owns routing, context budget, locks, user confirmations, and final decisions.
- Requirement Agent: owns requirement preservation, decomposition, evidence, database investigation planning, and acceptance criteria.
- Execution Agent: owns scoped source investigation, implementation, and local task verification.
- Quality Agent: owns independent code review, verification-log review, SQL/migration review, and release verdicts.
- Delivery Agent: owns finish/gate-ready/deliver/cleanup readiness, but never bypasses explicit user confirmation.

Read only the role reference needed for the current stage:

- Main Agent: `references/main-agent.md`
- Requirement Agent: `references/requirement-agent.md`
- Execution Agent: `references/execution-agent.md`
- Quality Agent: `references/quality-agent.md`
- Delivery Agent: `references/delivery-agent.md`

## Specialty Skills

Load these only when the task triggers them:

- Command contract drift: `.skill/global/mom-praxis-command-contract/SKILL.md`
- Database investigation: `.skill/global/mom-database-investigation/SKILL.md`
- Delivery branch hygiene: `.skill/global/mom-delivery-branch-hygiene/SKILL.md`
- Frontend pattern search: `.skill/global/mom-frontend-pattern-search/SKILL.md`
- Context budgeting: `.skill/global/mom-context-budgeting/SKILL.md`

## Stage Map

| Stage | Owner | Gate |
| --- | --- | --- |
| Intake and routing | Main Agent | Task type, project, docs/worktree/database/subagent decision is explicit |
| Requirement analysis | Requirement Agent | Requirement evidence and acceptance criteria are written or summarized |
| Planning and implementation | Execution Agent | Write locks, changed files, and verification commands are clear |
| Review and verification | Quality Agent | `BLOCKER/RISK/NIT/VERDICT` result is available |
| Delivery closeout | Delivery Agent | Readiness is audited; action execution waits for explicit user confirmation |

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
- Main Agent automatically plans and dispatches eligible role-agent/subagent work when runtime tools allow it; it does not wait for the user to explicitly ask for subagents on each coding task.
- Requirement and Quality agents are read-only by default.
- Execution agents must own explicit write paths and must not change files outside the lock.
- Delivery agents may prepare commands and readiness conclusions, but commit, push, cherry-pick, deliver, cleanup, branch deletion, and worktree deletion still require explicit user confirmation.
- Any role agent that needs further splitting returns `BLOCKED` or `CHECKPOINT`; it must not dispatch nested agents.

## Result Status

- `PLAN`: intended approach, risks, commands, and document/write targets.
- `CHECKPOINT`: partial finding or decision needed from the Main Agent.
- `RESULT`: completed work with evidence, paths, validation, and residual risk.
- `BLOCKED`: concrete blocker and the smallest decision or external action needed.
