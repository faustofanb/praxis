from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from praxis.application import PraxisApplication


def _json_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="praxis")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    commands = parser.add_subparsers(dest="group", required=True)

    version = commands.add_parser("version")
    _json_flag(version)

    workspace = commands.add_parser("workspace").add_subparsers(dest="action", required=True)
    init = workspace.add_parser("init")
    init.add_argument("--workspace-id", required=True)
    init.add_argument("--product-family", required=True)
    init.add_argument("--vault", default="knowledge")
    init.add_argument("--project", action="append", default=[])
    _json_flag(init)
    for action in ("inspect", "bootstrap"):
        _json_flag(workspace.add_parser(action))

    requirement = commands.add_parser("requirement").add_subparsers(dest="action", required=True)
    create = requirement.add_parser("create")
    create.add_argument("--id", required=True)
    create.add_argument("--title", required=True)
    create.add_argument("--request", required=True)
    create.add_argument("--tag", action="append", default=[])
    _json_flag(create)

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
    inspect = skill.add_parser("inspect")
    inspect.add_argument("id")
    _json_flag(inspect)
    route = skill.add_parser("route")
    route.add_argument("intent")
    route.add_argument("--budget", type=int, default=2000)
    _json_flag(route)
    candidate = skill.add_parser("candidate")
    candidate.add_argument("--project", required=True)
    _json_flag(candidate)
    approve = skill.add_parser("approve")
    approve.add_argument("id")
    approve.add_argument("--catalog-root", type=Path, required=True)
    approve.add_argument("--yes", action="store_true")
    _json_flag(approve)

    codegraph = commands.add_parser("codegraph").add_subparsers(dest="action", required=True)
    for action in ("status", "build", "sync", "affected"):
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
    for action in ("create", "remove"):
        child = worktree.add_parser(action)
        child.add_argument("branch")
        if action == "create":
            child.add_argument("--base", default="main")
        _json_flag(child)
    merge = worktree.add_parser("merge")
    merge.add_argument("target", nargs="?", default="main")
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
    ):
        child = hook.add_parser(action)
        child.add_argument("--project", required=True)
        child.add_argument("--worktree", type=Path)
        child.add_argument("--initialize", action="store_true")
        child.add_argument("--allow-rg-fallback", action="store_true")
        _json_flag(child)

    portrait = commands.add_parser("portrait").add_subparsers(dest="action", required=True)
    portrait_scan = portrait.add_parser("scan")
    portrait_scan.add_argument("--project", required=True)
    _json_flag(portrait_scan)

    runtime = commands.add_parser("runtime").add_subparsers(dest="action", required=True)
    diagnose = runtime.add_parser("diagnose")
    diagnose.add_argument("--process", action="append", default=[])
    for option in ("pid", "port", "file", "container"):
        diagnose.add_argument(f"--{option}", action="append", default=[])
    for option in ("tree", "warnings", "env", "verbose"):
        diagnose.add_argument(f"--{option}", action="store_true")
    _json_flag(diagnose)

    gate = commands.add_parser("gate").add_subparsers(dest="action", required=True)
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

    mcp = commands.add_parser("mcp").add_subparsers(dest="action", required=True)
    mcp.add_parser("serve")
    return parser


def _operation(args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    values = vars(args)
    if args.group == "version":
        return "version", {}
    if args.group == "workspace":
        if args.action == "init":
            projects = []
            for raw in args.project:
                project_id, kind, path, branch = raw.split(":", 3)
                projects.append(
                    {"id": project_id, "kind": kind, "path": path, "default_branch": branch}
                )
            return "workspace.init", {
                "workspace_id": args.workspace_id,
                "product_family": args.product_family,
                "vault": args.vault,
                "projects": projects,
            }
        return f"workspace.{args.action}", {}
    if args.group == "requirement":
        return "requirement.create", {
            "requirement_id": args.id,
            "title": args.title,
            "request": args.request,
            "domain_tags": args.tag,
        }
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
        if args.action == "candidate":
            return "skill.candidate", {"project_id": args.project}
        if args.action == "approve":
            return "skill.approve", {
                "id": args.id,
                "catalog_root": args.catalog_root,
                "approved": args.yes,
            }
        key = "id" if args.action == "inspect" else "intent"
        payload = {key: getattr(args, key)}
        if args.action == "route":
            payload["budget"] = args.budget
        return f"skill.{args.action}", payload
    if args.group == "codegraph":
        payload = {"project_id": args.project}
        if hasattr(args, "target"):
            payload["target"] = args.target
        if hasattr(args, "initialize"):
            payload["initialize"] = args.initialize
        return f"codegraph.{args.action}", payload
    if args.group == "worktree":
        if args.action == "install-hooks":
            return "worktree.install-hooks", {"project_id": args.project}
        keys = ("branch", "base", "target")
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
    if args.group == "portrait":
        return "portrait.scan", {"project_id": args.project}
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
        return "gate.run", {
            "event": args.event,
            "project_id": args.project,
            "worktree": args.worktree,
            "graph_required": not args.allow_rg_fallback,
        }
    raise ValueError(args.group)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.group == "mcp":
        from praxis.mcp.server import serve

        serve(args.root)
        return 0
    operation, values = _operation(args)
    result = PraxisApplication(args.root).execute(operation, values)
    payload = result.to_dict()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False))
    elif operation == "version" and result.ok:
        print(result.data["version"])
    elif result.ok:
        print(json.dumps(result.data, ensure_ascii=False, indent=2))
    else:
        print(f"{result.code}: {result.data.get('message', '')}")
    return 0 if result.ok else 2
