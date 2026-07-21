from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from praxis.application import PraxisApplication
from praxis.result import Result


def _json_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="praxis")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    commands = parser.add_subparsers(dest="group", required=True)

    init = commands.add_parser("init")
    init.add_argument("--workspace-id", required=True)
    init.add_argument("--name", required=True)
    init.add_argument("--knowledge-root", default="知识库")
    _json_flag(init)

    _json_flag(commands.add_parser("doctor"))

    version = commands.add_parser("version")
    _json_flag(version)

    workspace = commands.add_parser("workspace").add_subparsers(dest="action", required=True)
    for action in ("inspect", "show", "validate", "guidance"):
        _json_flag(workspace.add_parser(action))
    bootstrap = workspace.add_parser("bootstrap")
    bootstrap.add_argument("--approve-skills", action="store_true")
    _json_flag(bootstrap)
    add_workspace = workspace.add_parser("add")
    add_workspace.add_argument("--system", required=True)
    add_workspace.add_argument("--id", required=True)
    add_workspace.add_argument("--name", required=True)
    add_workspace.add_argument("--kind", required=True)
    add_workspace.add_argument("--path", required=True)
    add_workspace.add_argument("--default-branch", default="main")
    for option in (
        "database-connection",
        "production-database-connection",
        "deployment-command",
        "release-branch",
        "template-branch",
        "lint-command",
        "typecheck-command",
        "test-command",
    ):
        add_workspace.add_argument(f"--{option}", action="append", default=[])
    _json_flag(add_workspace)

    system = commands.add_parser("system").add_subparsers(dest="action", required=True)
    system_add = system.add_parser("add")
    system_add.add_argument("--id", required=True)
    system_add.add_argument("--name", required=True)
    system_add.add_argument("--domain", action="append", default=[])
    _json_flag(system_add)
    for action in ("scan", "show", "diff"):
        child = system.add_parser(action)
        child.add_argument("--project", required=True)
        _json_flag(child)

    domain = commands.add_parser("domain").add_subparsers(dest="action", required=True)
    domain_add = domain.add_parser("add")
    domain_add.add_argument("--system", required=True)
    domain_add.add_argument("--id", required=True)
    domain_add.add_argument("--name", required=True)
    _json_flag(domain_add)
    _json_flag(domain.add_parser("list"))
    domain_merge = domain.add_parser("merge")
    domain_merge.add_argument("source")
    domain_merge.add_argument("target")
    _json_flag(domain_merge)

    requirement = commands.add_parser("requirement").add_subparsers(dest="action", required=True)
    new = requirement.add_parser("new")
    new.add_argument("--name", required=True)
    new.add_argument("--request", required=True)
    new.add_argument("--system", action="append", default=[])
    new.add_argument("--domain", action="append", default=[])
    _json_flag(new)
    for action in (
        "show",
        "analyze",
        "plan",
        "ready",
        "start",
        "verify",
        "complete",
        "archive",
        "cancel",
    ):
        child = requirement.add_parser(action)
        child.add_argument("id")
        _json_flag(child)
    progress_requirement = requirement.add_parser("progress")
    progress_requirement.add_argument("id")
    progress_requirement.add_argument("message")
    _json_flag(progress_requirement)
    rename_requirement = requirement.add_parser("rename")
    rename_requirement.add_argument("id")
    rename_requirement.add_argument("name")
    _json_flag(rename_requirement)

    task = commands.add_parser("task").add_subparsers(dest="action", required=True)
    start = task.add_parser("start")
    start.add_argument("--id", required=True)
    start.add_argument("--title", required=True)
    start.add_argument("--project", required=True)
    start.add_argument("--requirement")
    start.add_argument("--graph-required", action="store_true")
    _json_flag(start)
    for action in ("resume", "inspect"):
        child = task.add_parser(action)
        child.add_argument("id")
        _json_flag(child)
    progress = task.add_parser("progress")
    progress.add_argument("id")
    progress.add_argument("message")
    _json_flag(progress)

    skill = commands.add_parser("skill").add_subparsers(dest="action", required=True)
    for action in ("list", "verify", "dedupe"):
        _json_flag(skill.add_parser(action))
    inspect = skill.add_parser("inspect")
    inspect.add_argument("id")
    _json_flag(inspect)
    route = skill.add_parser("route")
    route.add_argument("intent")
    route.add_argument("--budget", type=int, default=2000)
    _json_flag(route)
    route_node = skill.add_parser("route-node")
    route_node.add_argument("--node", required=True)
    route_node.add_argument("--intent", default="")
    route_node.add_argument("--requirement")
    route_node.add_argument("--project")
    route_node.add_argument("--system")
    route_node.add_argument("--repository-kind")
    route_node.add_argument("--agent-role")
    route_node.add_argument("--domain", action="append", default=[])
    route_node.add_argument("--artifact", action="append", default=[])
    route_node.add_argument("--risk", action="append", default=[])
    route_node.add_argument("--available-skill", action="append", default=[])
    route_node.add_argument("--approved-skill", action="append", default=[])
    route_node.add_argument("--budget", type=int, default=4000)
    _json_flag(route_node)
    invoke_skill = skill.add_parser("invoke")
    invoke_skill.add_argument("id")
    invoke_skill.add_argument("--requirement", required=True)
    invoke_skill.add_argument("--node", required=True)
    invoke_skill.add_argument("--session")
    invoke_skill.add_argument("--approved", action="store_true")
    _json_flag(invoke_skill)
    complete_skill = skill.add_parser("complete")
    complete_skill.add_argument("invocation_id")
    complete_skill.add_argument("--outcome", default="completed")
    _json_flag(complete_skill)
    skill_gate = skill.add_parser("gate")
    skill_gate.add_argument("--requirement", required=True)
    skill_gate.add_argument("--node", required=True)
    _json_flag(skill_gate)
    search = skill.add_parser("search")
    search.add_argument("query")
    _json_flag(search)
    import_skill = skill.add_parser("import")
    import_skill.add_argument("--source", type=Path, required=True)
    import_skill.add_argument("--system", required=True)
    _json_flag(import_skill)
    candidate = skill.add_parser("candidate")
    candidate.add_argument("--project", required=True)
    _json_flag(candidate)
    generate = skill.add_parser("generate")
    generate.add_argument("--project", required=True)
    _json_flag(generate)
    approve = skill.add_parser("approve")
    approve.add_argument("id")
    approve.add_argument("--catalog-root", type=Path, required=True)
    approve.add_argument("--yes", action="store_true")
    _json_flag(approve)

    codegraph = commands.add_parser("codegraph").add_subparsers(dest="action", required=True)
    status = codegraph.add_parser("status")
    status.add_argument("--project")
    status.add_argument("--binding")
    status.add_argument("--worktree", type=Path)
    _json_flag(status)
    for action in ("build", "sync", "affected"):
        child = codegraph.add_parser(action)
        child.add_argument("--project", required=True)
        _json_flag(child)
    fresh = codegraph.add_parser("ensure-fresh")
    fresh.add_argument("--project", required=True)
    fresh.add_argument("--initialize", action="store_true")
    _json_flag(fresh)
    for action in ("query", "explore", "node"):
        child = codegraph.add_parser(action)
        child.add_argument("target")
        child.add_argument("--project", required=True)
        _json_flag(child)

    worktree = commands.add_parser("worktree").add_subparsers(dest="action", required=True)
    _json_flag(worktree.add_parser("list"))
    _json_flag(worktree.add_parser("status"))
    create_worktree = worktree.add_parser("create")
    create_worktree.add_argument("requirement_id")
    create_worktree.add_argument("--repository", required=True)
    create_worktree.add_argument("--stage")
    _json_flag(create_worktree)
    remove_worktree = worktree.add_parser("remove")
    remove_worktree.add_argument("branch")
    _json_flag(remove_worktree)
    merge = worktree.add_parser("merge")
    merge.add_argument("target", nargs="?", default="main")
    merge.add_argument("--branch")
    _json_flag(merge)
    hooks = worktree.add_parser("install-hooks")
    hooks.add_argument("--project", required=True)
    _json_flag(hooks)

    hook = commands.add_parser("hook").add_subparsers(dest="action", required=True)
    for action in (
        "post-start",
        "task-context",
        "change-preflight",
        "verify",
        "pre-merge",
        "post-merge",
        "post-remove",
        "before-tool",
        "after-tool",
        "session-stop",
    ):
        child = hook.add_parser(action)
        child.add_argument("--project", required=True)
        child.add_argument("--worktree", type=Path)
        child.add_argument("--initialize", action="store_true")
        child.add_argument("--allow-rg-fallback", action="store_true")
        _json_flag(child)

    lifecycle = commands.add_parser("lifecycle").add_subparsers(dest="action", required=True)
    for action in (
        "worktree-pre-start",
        "worktree-post-start",
        "pre-commit",
        "pre-merge",
        "post-merge",
        "post-remove",
    ):
        child = lifecycle.add_parser(action)
        child.add_argument("--stdin-json", action="store_true", required=True)
        child.add_argument("--session")

    portrait = commands.add_parser("portrait").add_subparsers(dest="action", required=True)
    scan_portrait = portrait.add_parser("scan")
    scan_portrait.add_argument("--project", required=True)
    scan_portrait.add_argument("--runtime-process", action="append", default=[])
    for option in ("pid", "port", "file", "container"):
        scan_portrait.add_argument(f"--runtime-{option}", action="append", default=[])
    _json_flag(scan_portrait)
    for action in ("show", "diff", "verify"):
        child = portrait.add_parser(action)
        child.add_argument("--project", required=True)
        _json_flag(child)

    database = commands.add_parser("database").add_subparsers(dest="action", required=True)
    _json_flag(database.add_parser("discover"))
    connections = database.add_parser("connections")
    connections.add_argument("--project", required=True)
    _json_flag(connections)
    query = database.add_parser("query")
    query.add_argument("--project", required=True)
    query.add_argument("--connection", required=True)
    query.add_argument("--sql", required=True)
    query.add_argument("--approve-write", action="store_true")
    query.add_argument("--requirement")
    query.add_argument("--stage")
    query.add_argument("--purpose")
    query.add_argument("--parameters-json", default="{}")
    query.add_argument("--precheck")
    query.add_argument("--postimpact")
    query.add_argument("--approval")
    _json_flag(query)
    configure = database.add_parser("configure")
    configure.add_argument("--project", required=True)
    configure.add_argument("--connection-ref", action="append", default=[])
    configure.add_argument("--production-connection-ref", action="append", default=[])
    _json_flag(configure)

    context = commands.add_parser("context").add_subparsers(dest="action", required=True)
    build_context = context.add_parser("build")
    build_context.add_argument("--requirement", required=True)
    build_context.add_argument("--project", required=True)
    build_context.add_argument("--stage", required=True)
    build_context.add_argument("--agent-role", required=True)
    build_context.add_argument("--workflow-node", default="in_progress")
    build_context.add_argument("--token-budget", type=int, default=24_000)
    build_context.add_argument("--allow-path", action="append", default=[])
    build_context.add_argument("--forbid-path", action="append", default=[])
    build_context.add_argument("--artifact", action="append", default=[])
    build_context.add_argument("--risk", action="append", default=[])
    build_context.add_argument("--available-skill", action="append", default=[])
    build_context.add_argument("--approved-skill", action="append", default=[])
    _json_flag(build_context)
    show_context = context.add_parser("show")
    show_context.add_argument("id")
    _json_flag(show_context)
    diff_context = context.add_parser("diff")
    diff_context.add_argument("id")
    diff_context.add_argument("previous_id")
    _json_flag(diff_context)

    runtime = commands.add_parser("runtime").add_subparsers(dest="action", required=True)
    diagnose = runtime.add_parser("diagnose")
    diagnose.add_argument("--process", action="append", default=[])
    for option in ("pid", "port", "file", "container"):
        diagnose.add_argument(f"--{option}", action="append", default=[])
    for option in ("tree", "warnings", "env", "verbose"):
        diagnose.add_argument(f"--{option}", action="store_true")
    _json_flag(diagnose)

    gate = commands.add_parser("gate").add_subparsers(dest="action", required=True)
    _json_flag(gate.add_parser("list"))
    explain_gate = gate.add_parser("explain")
    explain_gate.add_argument("event")
    _json_flag(explain_gate)
    history_gate = gate.add_parser("history")
    history_gate.add_argument("--limit", type=int, default=100)
    _json_flag(history_gate)
    gate_run = gate.add_parser("run")
    gate_run.add_argument(
        "event",
        choices=(
            "task_start",
            "change_preflight",
            "verify",
            "worktree_pre_merge",
            "delivery",
            "workspace_scan",
        ),
    )
    gate_run.add_argument("--project", required=True)
    gate_run.add_argument("--worktree", type=Path)
    gate_run.add_argument("--allow-rg-fallback", action="store_true")
    gate_run.add_argument("--added-lines", type=int, default=0)
    gate_run.add_argument("--deleted-lines", type=int, default=0)
    _json_flag(gate_run)
    commit_message = gate.add_parser("commit-message")
    commit_message.add_argument("--message-file", type=Path, required=True)
    _json_flag(commit_message)

    mcp = commands.add_parser("mcp").add_subparsers(dest="action", required=True)
    mcp.add_parser("serve")
    _json_flag(mcp.add_parser("list"))
    add_mcp = mcp.add_parser("add")
    add_mcp.add_argument("--id", required=True)
    add_mcp.add_argument("--command", action="append", default=[], required=True)
    add_mcp.add_argument("--capability", action="append", default=[], required=True)
    add_mcp.add_argument(
        "--risk",
        choices=("read", "workspace_write", "external_write", "destructive"),
        required=True,
    )
    add_mcp.add_argument("--approve", action="store_true")
    _json_flag(add_mcp)
    grant = mcp.add_parser("grant")
    grant.add_argument("--session", required=True)
    grant.add_argument("--role", required=True)
    grant.add_argument("--capability", action="append", default=[], required=True)
    grant.add_argument("--requirement")
    grant.add_argument("--worktree")
    grant.add_argument("--approve-external", action="store_true")
    _json_flag(grant)
    render_mcp = mcp.add_parser("render")
    render_mcp.add_argument("--session", required=True)
    _json_flag(render_mcp)

    agent = commands.add_parser("agent").add_subparsers(dest="action", required=True)
    install_agent = agent.add_parser("install")
    install_agent.add_argument(
        "--agent", choices=("codex", "claude-code", "oh-my-pi"), required=True
    )
    _json_flag(install_agent)
    start_agent = agent.add_parser("start")
    start_agent.add_argument("--type", choices=("codex", "claude-code", "oh-my-pi"), required=True)
    start_agent.add_argument("--role", required=True)
    start_agent.add_argument("--requirement", required=True)
    start_agent.add_argument("--context", required=True)
    start_agent.add_argument("--worktree", required=True)
    start_agent.add_argument("--capability", action="append", default=[], required=True)
    start_agent.add_argument("--skill", action="append", default=[])
    start_agent.add_argument("--approve-external", action="store_true")
    _json_flag(start_agent)
    render_agent = agent.add_parser("render")
    render_agent.add_argument("session_id")
    _json_flag(render_agent)
    launch_agent = agent.add_parser("launch")
    launch_agent.add_argument("session_id")
    launch_agent.add_argument("--execute", action="store_true")
    _json_flag(launch_agent)
    finish_agent = agent.add_parser("finish")
    finish_agent.add_argument("session_id")
    finish_agent.add_argument("--status", default="completed")
    _json_flag(finish_agent)
    _json_flag(agent.add_parser("sessions"))

    artifact = commands.add_parser("artifact").add_subparsers(dest="action", required=True)
    add_artifact = artifact.add_parser("add")
    add_artifact.add_argument("--requirement", required=True)
    add_artifact.add_argument("--type", required=True)
    add_artifact.add_argument("--source", type=Path, required=True)
    add_artifact.add_argument("--stage", required=True)
    add_artifact.add_argument("--metadata-json", default="{}")
    _json_flag(add_artifact)
    list_artifact = artifact.add_parser("list")
    list_artifact.add_argument("--requirement")
    _json_flag(list_artifact)
    verify_artifact = artifact.add_parser("verify")
    verify_artifact.add_argument("artifact_id")
    _json_flag(verify_artifact)

    audit = commands.add_parser("audit").add_subparsers(dest="action", required=True)
    list_audit = audit.add_parser("list")
    list_audit.add_argument("--limit", type=int, default=100)
    _json_flag(list_audit)
    show_audit = audit.add_parser("show")
    show_audit.add_argument("audit_id")
    _json_flag(show_audit)
    _json_flag(audit.add_parser("verify"))

    repair = commands.add_parser("repair").add_subparsers(dest="action", required=True)
    _json_flag(repair.add_parser("projections"))
    _json_flag(repair.add_parser("indexes"))
    return parser


def _operation(args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    values = vars(args)
    if args.group == "init":
        return "init", {
            "workspace_id": args.workspace_id,
            "name": args.name,
            "knowledge_root": args.knowledge_root,
        }
    if args.group == "doctor":
        return "doctor", {}
    if args.group == "version":
        return "version", {}
    if args.group == "workspace":
        if args.action == "add":
            return "workspace.add", {
                "system_id": args.system,
                "project_id": args.id,
                "name": args.name,
                "kind": args.kind,
                "path": args.path,
                "default_branch": args.default_branch,
                "database_connections": args.database_connection,
                "production_database_connections": args.production_database_connection,
                "deployment_commands": args.deployment_command,
                "release_branches": args.release_branch,
                "template_branches": args.template_branch,
                "lint_commands": args.lint_command,
                "typecheck_commands": args.typecheck_command,
                "test_commands": args.test_command,
            }
        return f"workspace.{args.action}", (
            {"approve_skills": args.approve_skills} if args.action == "bootstrap" else {}
        )
    if args.group == "system":
        if args.action != "add":
            return f"system.{args.action}", {"project_id": args.project}
        return "system.add", {
            "system_id": args.id,
            "name": args.name,
            "domains": args.domain,
        }
    if args.group == "domain":
        if args.action == "add":
            return "domain.add", {
                "system_id": args.system,
                "domain_id": args.id,
                "name_zh": args.name,
            }
        if args.action == "list":
            return "domain.list", {}
        return "domain.merge", {"source": args.source, "target": args.target}
    if args.group == "requirement":
        if args.action == "new":
            return "requirement.new", {
                "short_name": args.name,
                "request": args.request,
                "systems": args.system,
                "domains": args.domain,
            }
        payload = {"requirement_id": args.id}
        if args.action == "progress":
            payload["message"] = args.message
        if args.action == "rename":
            payload["short_name"] = args.name
        return f"requirement.{args.action}", payload
    if args.group == "task":
        if args.action == "start":
            return "task.start", {
                "task_id": args.id,
                "title": args.title,
                "project_id": args.project,
                "requirement_id": args.requirement,
                "graph_required": args.graph_required,
            }
        payload = {"task_id": args.id}
        if args.action == "progress":
            payload["message"] = args.message
        return f"task.{args.action}", payload
    if args.group == "skill":
        if args.action in {"list", "verify", "dedupe"}:
            return f"skill.{args.action}", {}
        if args.action == "search":
            return "skill.search", {"query": args.query}
        if args.action == "import":
            return "skill.import", {"source_root": args.source, "system_id": args.system}
        if args.action in {"candidate", "generate"}:
            return "skill.candidate", {"project_id": args.project}
        if args.action == "approve":
            return "skill.approve", {
                "id": args.id,
                "catalog_root": args.catalog_root,
                "approved": args.yes,
            }
        if args.action == "route-node":
            return "skill.route-node", {
                "node": args.node,
                "intent": args.intent,
                "requirement_id": args.requirement or "",
                "project_id": args.project or "",
                "system_id": args.system or "",
                "repository_kind": args.repository_kind or "",
                "agent_role": args.agent_role or "",
                "business_domains": args.domain,
                "artifact_types": args.artifact,
                "risks": args.risk,
                "available_skills": args.available_skill,
                "approved_skills": args.approved_skill,
                "budget": args.budget,
            }
        if args.action == "invoke":
            return "skill.invoke", {
                "skill_id": args.id,
                "requirement_id": args.requirement,
                "node": args.node,
                "session_id": args.session or "",
                "approved": args.approved,
            }
        if args.action == "complete":
            return "skill.complete", {
                "invocation_id": args.invocation_id,
                "outcome": args.outcome,
            }
        if args.action == "gate":
            return "skill.gate", {
                "requirement_id": args.requirement,
                "node": args.node,
            }
        key = "id" if args.action == "inspect" else "intent"
        payload = {key: getattr(args, key)}
        if args.action == "route":
            payload["budget"] = args.budget
        return f"skill.{args.action}", payload
    if args.group == "codegraph":
        payload = {}
        if getattr(args, "project", None):
            payload["project_id"] = args.project
        if getattr(args, "binding", None):
            payload["binding_id"] = args.binding
        if getattr(args, "worktree", None):
            payload["worktree"] = args.worktree
        if hasattr(args, "target"):
            payload["target"] = args.target
        if hasattr(args, "initialize"):
            payload["initialize"] = args.initialize
        return f"codegraph.{args.action}", payload
    if args.group == "worktree":
        if args.action == "install-hooks":
            return "worktree.install-hooks", {"project_id": args.project}
        if args.action == "create":
            return "worktree.create", {
                "requirement_id": args.requirement_id,
                "repository_id": args.repository,
                "stage": args.stage,
            }
        if args.action == "status":
            return "worktree.list", {}
        keys = ("branch", "target")
        return f"worktree.{args.action}", {key: values[key] for key in keys if key in values}
    if args.group == "hook":
        return f"hook.{args.action}", {
            "project_id": args.project,
            "worktree": args.worktree,
            "initialize": args.initialize,
            "graph_required": not args.allow_rg_fallback,
            "added_lines": args.added_lines,
            "deleted_lines": args.deleted_lines,
        }
    if args.group == "lifecycle":
        return f"lifecycle.{args.action}", {"context": args.context}
    if args.group == "portrait":
        payload = {"project_id": args.project}
        if args.action == "scan":
            runtime_arguments = list(args.runtime_process)
            for option in ("pid", "port", "file", "container"):
                for value in getattr(args, f"runtime_{option}"):
                    runtime_arguments.extend([f"--{option}", value])
            if runtime_arguments:
                payload["runtime_arguments"] = runtime_arguments
        return f"portrait.{args.action}", payload
    if args.group == "database":
        if args.action == "discover":
            return "database.discover", {}
        if args.action == "configure":
            return "database.configure", {
                "project_id": args.project,
                "connection_refs": args.connection_ref,
                "production_connection_refs": args.production_connection_ref,
            }
        payload = {"project_id": args.project}
        if args.action == "query":
            payload.update(
                {
                    "connection_ref": args.connection,
                    "sql": args.sql,
                    "approved": args.approve_write,
                }
            )
            if args.approve_write:
                payload["write_context"] = {
                    "requirement_id": args.requirement,
                    "stage": args.stage,
                    "purpose": args.purpose,
                    "parameters": json.loads(args.parameters_json),
                    "precheck": args.precheck,
                    "postimpact": args.postimpact,
                    "approval": args.approval,
                }
        return f"database.{args.action}", payload
    if args.group == "context":
        if args.action == "build":
            return "context.build", {
                "requirement_id": args.requirement,
                "project_id": args.project,
                "stage": args.stage,
                "agent_role": args.agent_role,
                "token_budget": args.token_budget,
                "allowed_paths": args.allow_path,
                "forbidden_paths": args.forbid_path,
                "workflow_node": args.workflow_node,
                "artifact_types": args.artifact,
                "risks": args.risk,
                "available_skills": args.available_skill,
                "approved_skills": args.approved_skill,
            }
        if args.action == "show":
            return "context.show", {"context_id": args.id}
        return "context.diff", {
            "context_id": args.id,
            "previous_context_id": args.previous_id,
        }
    if args.group == "runtime":
        arguments = list(args.process)
        for option in ("pid", "port", "file", "container"):
            for value in getattr(args, option):
                arguments.extend([f"--{option}", value])
        for option in ("tree", "warnings", "env", "verbose"):
            if getattr(args, option):
                arguments.append(f"--{option}")
        return "runtime.diagnose", {"arguments": arguments}
    if args.group == "gate":
        if args.action == "list":
            return "gate.list", {}
        if args.action == "explain":
            return "gate.explain", {"event": args.event}
        if args.action == "history":
            return "gate.history", {"limit": args.limit}
        if args.action == "commit-message":
            return "gate.commit-message", {"message_file": args.message_file}
        return "gate.run", {
            "event": args.event,
            "project_id": args.project,
            "worktree": args.worktree,
            "graph_required": not args.allow_rg_fallback,
        }
    if args.group == "mcp":
        if args.action == "list":
            return "mcp.list", {}
        if args.action == "add":
            return "mcp.add", {
                "server_id": args.id,
                "command": args.command,
                "capabilities": args.capability,
                "risk": args.risk,
                "approved": args.approve,
            }
        if args.action == "render":
            return "mcp.render", {"session_id": args.session}
        return "mcp.grant", {
            "session_id": args.session,
            "role": args.role,
            "capabilities": args.capability,
            "requirement_id": args.requirement,
            "worktree": args.worktree,
            "approved_external": args.approve_external,
        }
    if args.group == "agent":
        if args.action == "install":
            return "agent.install", {"agent_type": args.agent}
        if args.action == "start":
            return "agent.start", {
                "agent_type": args.type,
                "role": args.role,
                "requirement_id": args.requirement,
                "context_id": args.context,
                "worktree": args.worktree,
                "capabilities": args.capability,
                "skills": args.skill,
                "approved_external": args.approve_external,
            }
        if args.action == "render":
            return "agent.render", {"session_id": args.session_id}
        if args.action == "launch":
            return "agent.launch", {
                "session_id": args.session_id,
                "execute": args.execute,
            }
        if args.action == "finish":
            return "agent.finish", {"session_id": args.session_id, "status": args.status}
        return "agent.sessions", {}
    if args.group == "artifact":
        if args.action == "add":
            return "artifact.add", {
                "requirement_id": args.requirement,
                "artifact_type": args.type,
                "source_path": args.source,
                "stage": args.stage,
                "metadata": json.loads(args.metadata_json),
            }
        if args.action == "list":
            return "artifact.list", {"requirement_id": args.requirement}
        return "artifact.verify", {"artifact_id": args.artifact_id}
    if args.group == "audit":
        if args.action == "list":
            return "audit.list", {"limit": args.limit}
        if args.action == "show":
            return "audit.show", {"audit_id": args.audit_id}
        return "audit.verify", {}
    if args.group == "repair":
        return f"repair.{args.action}", {}
    raise ValueError(args.group)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.group == "mcp" and args.action == "serve":
        from praxis.mcp.server import serve

        serve(args.root)
        return 0
    if args.group == "lifecycle":
        try:
            args.context = json.load(sys.stdin)
            if args.session:
                args.context.setdefault("session_id", args.session)
        except (json.JSONDecodeError, OSError) as error:
            result = Result(False, "INVALID_HOOK_CONTEXT", data={"message": str(error)})
            print(json.dumps(result.to_dict(), ensure_ascii=False))
            return 2
    operation, values = _operation(args)
    result = PraxisApplication(args.root).execute(operation, values)
    payload = result.to_dict()
    if args.group == "lifecycle" or args.json:
        print(json.dumps(payload, ensure_ascii=False))
    elif operation == "version" and result.ok:
        print(result.data["version"])
    elif result.ok:
        print(json.dumps(result.data, ensure_ascii=False, indent=2))
    else:
        print(f"{result.code}: {result.data.get('message', '')}")
    return 0 if result.ok else 2
