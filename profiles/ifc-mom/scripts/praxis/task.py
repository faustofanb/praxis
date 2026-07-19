#!/usr/bin/env python3
"""IFC MOM Codex task dispatcher.

这个文件只负责命令行参数解析和分发；具体逻辑放在 momlib 子模块中，
避免单个入口文件继续膨胀。

Run with:
  task list
  task system -- check
  task context -- [--brief] <project> <需求名>
  task req -- init <需求名> <原始需求...>
  task req -- iter <需求名> analysis|plan|progress <主题>
  task req -- check <需求名>
  task req -- index <需求名>
  task req -- index-all
  task req -- domain-index
  task req -- db-plan <需求名>
  task docs -- domain-candidates
  task docs -- tolaria-check [<需求名>|--all]
  task docs -- tolaria-publish <需求名>|--all
  task etl -- init
  task etl -- subject <应用> <系统> <一级菜单> <主题> --menu-path <一级菜单/二级菜单/...>
  task etl -- tree
  task project -- verify <project> <需求名>
  task gate -- guard <project> <需求名>
  task gate -- ready <project> <需求名>
  task gate -- ready-all <需求名>
  task delivery -- status <project> <需求名>
  task delivery -- status-all <需求名>
  task delivery -- finish <project> <需求名>
  task delivery -- commit-split-all <需求名> <production-message>
  task delivery -- deliver-all <需求名>
  task delivery -- cleanup-all <需求名>
  task system -- index
  task system -- praxis-profile
  task gate -- change-check <project> <需求名>
  task gate -- migration-check <project> <需求名>
  task system -- command-audit
  task system -- template-check
  task system -- template-render rule|skill <slug> <title> <description> <output>
  task project -- preflight <project> <需求名>
  task project -- status|verify|run|shell|worktree|start <project> <args...>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from momlib.config import load_config
from momlib.context import context_brief_command, context_command
from momlib.docs import doc_init, doc_iter, tolaria_check, tolaria_publish, write_domain_candidates, write_domain_index, write_requirement_global_index
from momlib.etl import run_etl_action
from momlib.finish import cleanup_requirement, deliver_requirement, delivery_status, finish_requirement, split_commit_requirement
from momlib.git_worktree import create_worktree, project_worktree_dirs
from momlib.praxis import (
    command_audit,
    praxis_check,
    praxis_context_packet,
    praxis_index,
    praxis_write_readiness_report,
)
from praxislib.project_index import write_project_index_config
from praxislib.codegraph_adapter import run_codegraph
from praxislib.policy import write_policy_report
from momlib.process import fail
from momlib.project_actions import list_projects, run_project, shell_project, status_project, verify_project
from momlib.requirements import start_requirement
from momlib.quick_tasks import check_quick_task, start_quick_task
from momlib.workflow_checks import change_check, db_plan, docs_check, docs_index, guard_check, migration_check, preflight
from momlib.workflow_checks import write_execution_compliance_evidence
from momlib.praxis_profile import write_praxis_profile_report as praxis_profile_report
from momlib.praxis_templates import render_template, write_template_report as template_check_report


TOP_LEVEL_ACTIONS = {
    "req",
    "docs",
    "project",
    "context",
    "etl",
    "gate",
    "delivery",
    "system",
}

def run_praxis_action(action: str, args: list[str]) -> int:
    """Run one canonical Praxis command group."""
    if args and args[0] == "--":
        args = args[1:]
    if action == "system":
        if args and args[0] == "--":
            args = args[1:]
        if not args:
            fail(
                "usage: task system -- "
                "<check|index|init-project-index|project-index|policy-check|codegraph|praxis-profile|command-audit|template-check|template-render>"
            )
        return run_praxis_system_action(args[0], args[1:])
    config = load_config()
    if action == "req":
        return run_praxis_requirement_action(config, args)
    if action == "docs":
        return run_praxis_docs_action(config, args)
    if action == "project":
        return run_praxis_project_action(config, args)
    if action == "context":
        brief = False
        if args and args[0] in {"--brief", "brief"}:
            brief = True
            args = args[1:]
        if len(args) < 2:
            fail("usage: task context [--brief] <project> <需求名>")
        praxis_context_packet(config, args[0], args[1])
        if brief:
            context_brief_command(config, args[0], args[1])
        else:
            context_command(config, args[0], args[1])
        return 0
    if action == "etl":
        run_etl_action(config, args)
        return 0
    if action == "gate":
        return run_praxis_gate_action(config, args)
    if action == "delivery":
        return run_praxis_delivery_action(config, args)
    fail(f"unknown praxis action: {action}")


def run_praxis_system_action(action: str, args: list[str]) -> int:
    """Run Praxis system-level control-plane actions."""
    if action == "check":
        return praxis_check()
    if action == "index":
        praxis_index(scan="--scan" in args)
        return 0
    if action == "init-project-index":
        allowed = {"--force"}
        if any(arg not in allowed for arg in args):
            fail("usage: task system -- init-project-index [--force]")
        path = write_project_index_config(Path.cwd(), force="--force" in args)
        print(f"Praxis project index config: {path}")
        return 0
    if action == "project-index":
        allowed = {"--scan"}
        if any(arg not in allowed for arg in args):
            fail("usage: task system -- project-index [--scan]")
        praxis_index(scan="--scan" in args)
        return 0
    if action == "policy-check":
        if args:
            fail("usage: task system -- policy-check")
        path = write_policy_report(Path.cwd())
        status = json.loads(path.read_text(encoding="utf-8")).get("status", "FAIL")
        return 0 if status == "PASS" else 1
    if action == "codegraph":
        return run_codegraph(Path.cwd(), args)
    if action == "praxis-profile":
        path = praxis_profile_report()
        print(f"Praxis profile report: {path}")
        return 0
    if action == "command-audit":
        if len(args) > 1:
            fail("usage: task system -- command-audit [auto|python|bun]")
        if args and args[0] not in {"auto", "python", "bun"}:
            fail("usage: task system -- command-audit [auto|python|bun]")
        command_audit(args[0] if args else "auto")
        return 0
    if action == "template-check":
        if args:
            fail("usage: task system -- template-check")
        path = template_check_report()
        print(f"Praxis template report: {path}")
        return 0
    if action == "template-render":
        if len(args) != 5:
            fail("usage: task system -- template-render rule|skill <slug> <title> <description> <output>")
        kind, slug, title, description, output = args
        path = render_template(kind=kind, slug=slug, title=title, description=description, output=Path(output))
        print(f"Praxis template rendered: {path}")
        return 0
    fail(f"unknown praxis system action: {action}")


def run_praxis_requirement_action(config: dict, args: list[str]) -> int:
    """Run Praxis requirement-document actions."""
    if args and args[0] == "--":
        args = args[1:]
    if not args:
        fail("usage: task req -- <init|iter|check|index|index-all|domain-index|db-plan> ...")
    action = args[0]
    if action == "init":
        if len(args) < 3:
            fail("usage: task req -- init <需求名> <用户原始需求原文>")
        doc_init(config, args[1], " ".join(args[2:]))
        return 0
    if action == "iter":
        if len(args) < 4:
            fail("usage: task req -- iter <需求名> analysis|plan|progress <主题>")
        iter_args = args[3:]
        body: str | None = None
        if "--body-file" in iter_args:
            index = iter_args.index("--body-file")
            if index + 1 >= len(iter_args):
                fail("usage: task req -- iter <需求名> analysis|plan|progress <主题> [--body-file <md-file>]")
            body_path = Path(iter_args[index + 1])
            if not body_path.is_file():
                fail(f"body file not found: {body_path}")
            body = body_path.read_text(encoding="utf-8")
            iter_args = [*iter_args[:index], *iter_args[index + 2:]]
        if not iter_args:
            fail("usage: task req -- iter <需求名> analysis|plan|progress <主题> [--body-file <md-file>]")
        doc_iter(config, args[1], args[2], " ".join(iter_args), body)
        return 0
    if action == "check":
        if len(args) < 2:
            fail("usage: task req -- check <需求名>")
        return docs_check(config, args[1])
    if action == "index":
        if len(args) < 2:
            fail("usage: task req -- index <需求名>")
        return docs_index(config, args[1])
    if action == "index-all":
        write_requirement_global_index(config)
        return 0
    if action == "domain-index":
        write_domain_index(config)
        return 0
    if action == "db-plan":
        if len(args) < 2:
            fail("usage: task req -- db-plan <需求名>")
        return db_plan(config, args[1])
    fail(f"unknown praxis req action: {action}")


def run_praxis_docs_action(config: dict, args: list[str]) -> int:
    """Run docs-level knowledge actions."""
    if args and args[0] == "--":
        args = args[1:]
    if not args:
        fail("usage: task docs -- <domain-candidates|tolaria-check|tolaria-publish> ...")
    action = args[0]
    if action == "domain-candidates":
        write_domain_candidates(config)
        return 0
    if action == "tolaria-check":
        tolaria_check(config, args[1:])
        return 0
    if action == "tolaria-publish":
        if len(args) < 2:
            fail("usage: task docs -- tolaria-publish <需求名>|--all")
        tolaria_publish(config, args[1:])
        return 0
    fail(f"unknown praxis docs action: {action}")


def run_praxis_project_action(config: dict, args: list[str]) -> int:
    """Run Praxis project actions by delegating to existing project handlers."""
    if len(args) < 2:
        fail("usage: task project -- <action> <project> [args...]")
    action, project, remaining = args[0], args[1], args[2:]
    if action in {"status", "verify", "run", "shell", "worktree", "start", "quick", "quick-check"}:
        return run_project_action(config, project, action, remaining)
    if action == "preflight":
        if not remaining:
            fail("usage: task project -- preflight <project> <需求名>")
        praxis_context_packet(config, project, remaining[0])
        return preflight(config, project, remaining[0])
    fail(f"unknown praxis project action: {action}")


def run_praxis_gate_action(config: dict, args: list[str]) -> int:
    """Run Praxis quality gates."""
    if not args:
        fail(
            "usage: task gate -- "
            "<ready|ready-all|guard|change-check|migration-check> ..."
        )
    action = args[0]
    if action == "ready-all":
        if len(args) < 2:
            fail("usage: task gate -- ready-all <需求名> [--projects <project,project...>]")
        return run_grouped_action(config, "ready", args[1], args[2:], run_praxis_gate_single_action)
    return run_praxis_gate_single_action(config, args)


def run_praxis_gate_single_action(config: dict, args: list[str]) -> int:
    """Run a single-project Praxis gate action."""
    action = args[0]
    if action == "ready":
        if len(args) < 3:
            fail("usage: task gate -- ready <project> <需求名>")
        project, requirement = args[1], args[2]
        context_packet = praxis_context_packet(config, project, requirement)
        results = {
            "preflight": preflight(config, project, requirement),
            "guard": guard_check(config, project, requirement),
        }
        praxis_write_readiness_report(project, requirement, context_packet, results)
        return 0 if all(code == 0 for code in results.values()) else 1
    if len(args) < 3:
        fail("usage: task gate -- <guard|change-check|migration-check> <project> <需求名>")
    project, requirement = args[1], args[2]
    if action == "guard":
        praxis_context_packet(config, project, requirement)
        return guard_check(config, project, requirement)
    if action == "change-check":
        praxis_context_packet(config, project, requirement)
        return change_check(config, project, requirement)
    if action == "migration-check":
        praxis_context_packet(config, project, requirement)
        return migration_check(config, project, requirement)
    fail(f"unknown praxis gate action: {action}")


def split_project_filter(extra_args: list[str] | None = None) -> tuple[list[str], list[str]]:
    """Split optional --projects filter from remaining command arguments."""
    args = list(extra_args or [])
    explicit: list[str] = []
    remaining: list[str] = []
    index = 0
    while index < len(args):
        if args[index] == "--projects":
            if index + 1 >= len(args):
                fail("usage: --projects <project,project...>")
            explicit = [item.strip() for item in args[index + 1].split(",") if item.strip()]
            index += 2
        else:
            remaining.append(args[index])
            index += 1
    return explicit, remaining


def delivery_target_projects(config: dict, requirement_name: str, extra_args: list[str] | None = None) -> list[str]:
    """Return projects affected by a multi-project delivery action."""
    explicit, _ = split_project_filter(extra_args)
    projects = config.get("projects", {})
    if explicit:
        unknown = [project for project in explicit if project not in projects]
        if unknown:
            fail("unknown project(s): " + ", ".join(unknown))
        return explicit

    matched = [
        project
        for project in projects
        if project != "docs" and project_worktree_dirs(config, project, requirement_name, include_feature=True)
    ]
    if matched:
        return matched
    return [project for project in projects if project != "docs"]


def run_grouped_action(
    config: dict,
    action: str,
    requirement_name: str,
    extra_args: list[str],
    runner: Any,
    allow_remaining: bool = False,
) -> int:
    """Run one action for all target projects and summarize partial failures."""
    projects = delivery_target_projects(config, requirement_name, extra_args)
    _, remaining = split_project_filter(extra_args)
    if remaining and not allow_remaining:
        fail("usage: [--projects <project,project...>]")
    if not projects:
        fail("no target projects detected")
    exit_code = 0
    print(f"Praxis grouped action: {action} / {requirement_name}")
    for project in projects:
        print(f"== {project} ==")
        code = runner(config, [action, project, requirement_name, *remaining])
        status = "PASS" if code == 0 else "FAIL"
        print(f"{project}: {status}")
        if code != 0:
            exit_code = 1
    return exit_code


def run_praxis_delivery_action(config: dict, args: list[str]) -> int:
    """Run Praxis delivery actions."""
    if len(args) < 1:
        fail("usage: task delivery -- <status|status-all|finish|commit-split|commit-split-all|deliver|deliver-all|cleanup|cleanup-all> ...")
    action = args[0]
    if action in {"status-all", "commit-split-all", "deliver-all", "cleanup-all"}:
        if len(args) < 2:
            fail(f"usage: task delivery -- {action} <需求名> [--projects <project,project...>]")
        single_action = action.removesuffix("-all")
        return run_grouped_action(
            config,
            single_action,
            args[1],
            args[2:],
            run_praxis_delivery_single_action,
            allow_remaining=single_action == "commit-split",
        )
    if len(args) < 3:
        fail("usage: task delivery -- <status|finish|commit-split|deliver|cleanup> <project> <需求名> [args...]")
    return run_praxis_delivery_single_action(config, args)


def run_praxis_delivery_single_action(config: dict, args: list[str]) -> int:
    """Run a single-project Praxis delivery action."""
    action, project, requirement = args[0], args[1], args[2]
    praxis_context_packet(config, project, requirement)
    if action == "status":
        delivery_status(config, project, requirement)
        return 0
    if action == "finish":
        write_execution_compliance_evidence(config, project, requirement)
        finish_requirement(config, project, requirement)
        return 0
    if action == "commit-split":
        message = " ".join(args[3:]) if len(args) > 3 else None
        split_commit_requirement(config, project, requirement, message)
        return 0
    if action == "deliver":
        deliver_requirement(config, project, requirement)
        return 0
    if action == "cleanup":
        cleanup_requirement(config, project, requirement)
        return 0
    fail(f"unknown praxis delivery action: {action}")


def run_project_action(config: dict, project: str, action: str, args: list[str]) -> int:
    """根据 action 分发到对应模块，保持 task.py 入口轻量。"""
    if action == "start":
        if len(args) < 2:
            fail("usage: task project -- start <project> <简短中文需求名> <用户原始需求原文>")
        start_requirement(config, project, args[0], " ".join(args[1:]))
        return 0
    if action == "quick":
        if len(args) != 1:
            fail("usage: task project -- quick <project> <简短任务名>")
        start_quick_task(config, project, args[0])
        return 0
    if action == "quick-check":
        if len(args) != 1:
            fail("usage: task project -- quick-check <project> <简短任务名>")
        return check_quick_task(config, project, args[0])
    if action == "status":
        status_project(config, project, args)
    elif action == "verify":
        verify_project(config, project, args)
    elif action == "run":
        run_project(config, project, args)
    elif action == "shell":
        shell_project(config, project, args)
    elif action == "worktree":
        task_name = args[0] if args else "task"
        base_branch = args[1] if len(args) > 1 else None
        create_worktree(config, project, task_name, base_branch)
    else:
        fail(f"unknown action: {action}")
    return 0


def main(argv: list[str]) -> None:
    """加载配置并执行用户请求的 Praxis 自动化命令。"""
    if not argv or argv[0] in {"-h", "--help"}:
        print(__doc__)
        return
    if argv[0] == "list":
        list_projects(load_config())
        return
    if argv[0] in TOP_LEVEL_ACTIONS:
        exit_code = run_praxis_action(argv[0], argv[1:])
        if exit_code:
            raise SystemExit(exit_code)
        return
    fail(f"unknown task group: {argv[0]}")


if __name__ == "__main__":
    main(sys.argv[1:])
