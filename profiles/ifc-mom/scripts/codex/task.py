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
  task docs -- domain-index
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
  task gate -- validate-verdict quality|delivery <project> <需求名> <json-file>
  task gate -- import-verdict quality|delivery <project> <需求名> <agent-output-json>
  task role -- handoff|lock <quality|delivery|execution|knowledge> <project> <需求名> <summary|路径...>
  task delivery -- status <project> <需求名>
  task delivery -- status-all <需求名>
  task delivery -- precheck-all <需求名>
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
  task project -- status|verify|run|shell|worktree|start|finish|commit-split|deliver|cleanup <project> <args...>
"""

from __future__ import annotations

import argparse
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
    PRAXIS_CONTEXT_DIR,
    command_audit,
    safe_packet_name,
    praxis_check,
    praxis_context_packet,
    praxis_index,
    praxis_write_lock,
    praxis_write_delivery_precheck_packet,
    praxis_write_readiness_report,
    praxis_write_role_handoff,
    praxis_import_verdict_file,
    praxis_require_verdict,
    praxis_validate_verdict_file,
)
from praxislib.project_index import write_project_index_config
from praxislib.codegraph_adapter import run_codegraph
from praxislib.policy import write_policy_report
from momlib.process import fail
from momlib.project_actions import list_projects, run_project, shell_project, status_project, verify_project
from momlib.requirements import start_requirement
from momlib.workflow_checks import change_check, db_plan, docs_check, docs_index, guard_check, migration_check, preflight
from momlib.workflow_checks import write_execution_compliance_evidence
from momlib.praxis_profile import write_praxis_profile_report as praxis_profile_report
from momlib.praxis_templates import render_template, write_template_report as template_check_report


TOP_LEVEL_ACTIONS = {
    "check",
    "index",
    "command-audit",
    "template-check",
    "template-render",
    "req",
    "gate",
    "delivery",
    "role",
    "system",
    "codegraph",
    "docs",
}

PROJECT_ACTIONS = {
    "status",
    "verify",
    "run",
    "shell",
    "worktree",
    "start",
    "preflight",
    "guard",
    "change-check",
    "migration-check",
    "finish",
    "commit-split",
    "deliver",
    "cleanup",
}


def build_parser() -> argparse.ArgumentParser:
    """创建命令行解析器，只描述入口形态，不承载业务逻辑。"""
    parser = argparse.ArgumentParser(description="IFC MOM Codex task dispatcher")
    subparsers = parser.add_subparsers(dest="mode")

    subparsers.add_parser("list", help="list configured projects")

    context_parser = subparsers.add_parser("context", help="print minimal rule/skill context")
    context_parser.add_argument("--brief", action="store_true", help="print low-noise resume summary")
    context_parser.add_argument("project")
    context_parser.add_argument("requirement_name")

    etl_parser = subparsers.add_parser("etl", help="manage ETL asset directories")
    etl_parser.add_argument("args", nargs=argparse.REMAINDER)

    praxis_parser = subparsers.add_parser("praxis", help="run heavy Praxis checks")
    praxis_parser.add_argument("action", nargs="?", default="check")
    praxis_parser.add_argument("args", nargs=argparse.REMAINDER)

    workflow_parser = subparsers.add_parser("workflow", help="compatibility alias to praxis workflow actions")
    workflow_parser.add_argument("action", nargs="?", default="check")
    workflow_parser.add_argument("args", nargs=argparse.REMAINDER)

    # 兼容 `<project> <action>` 的短命令：normalize_argv 会补成 project 子命令。
    project_parser = subparsers.add_parser("project", help=argparse.SUPPRESS)
    project_parser.add_argument("project")
    project_parser.add_argument("action", nargs="?", default="status")
    project_parser.add_argument("args", nargs="*")

    return parser


def normalize_argv(argv: list[str]) -> list[str]:
    """把 `<project> <action>` 归一化为内部 project 子命令。"""
    if not argv or argv[0] in {"-h", "--help", "list", "context", "etl", "praxis", "workflow", "project", *TOP_LEVEL_ACTIONS}:
        return argv
    return ["project", *argv]


def normalize_project_args(project: str, action: str, args: list[str]) -> tuple[str, str, list[str]]:
    """Support both documented `project <action> <project>` and legacy `project <project> <action>`."""
    if project in PROJECT_ACTIONS:
        if action == "status":
            fail(f"usage: task project -- {project} <project> [args...]")
        return action, project, args
    return project, action, args


def run_praxis_action(action: str, args: list[str]) -> int:
    """Run heavy Praxis workflow actions."""
    if args and args[0] == "--":
        args = args[1:]
    if action in {
        "check",
        "index",
        "init-project-index",
        "project-index",
        "policy-check",
        "codegraph",
        "command-audit",
        "template-check",
        "template-render",
        "list",
    }:
        if action == "list":
            config = load_config()
            list_projects(config)
            return 0
        return run_praxis_system_action(action, args)
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
    if action == "role":
        return run_praxis_role_action(config, args)
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
        fail("usage: task req -- <init|iter|check|index|index-all|domain-index|db-plan|tolaria-check|tolaria-publish> ...")
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
    if action == "tolaria-check":
        tolaria_check(config, args[1:])
        return 0
    if action == "tolaria-publish":
        if len(args) < 2:
            fail("usage: task docs -- tolaria-publish <需求名>|--all")
        tolaria_publish(config, args[1:])
        return 0
    fail(f"unknown praxis req action: {action}")


def run_praxis_docs_action(config: dict, args: list[str]) -> int:
    """Run docs-level knowledge actions."""
    if args and args[0] == "--":
        args = args[1:]
    if not args:
        fail("usage: task docs -- <domain-index|domain-candidates|tolaria-check|tolaria-publish|index-all> ...")
    action = args[0]
    if action == "domain-index":
        write_domain_index(config)
        return 0
    if action == "domain-candidates":
        write_domain_candidates(config)
        return 0
    if action == "index-all":
        write_requirement_global_index(config)
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
    project, action, remaining = normalize_project_args(args[0], args[1], args[2:])
    if action in {"status", "verify", "run", "shell", "worktree", "start"}:
        return run_project_action(config, project, action, remaining, via_praxis=True)
    if action == "preflight":
        if not remaining:
            fail("usage: task project -- preflight <project> <需求名>")
        praxis_context_packet(config, project, remaining[0])
        return preflight(config, project, remaining[0])
    if action in {"guard", "change-check", "migration-check"}:
        if not remaining:
            fail(f"usage: task project -- {action} {project} <需求名>")
        return run_praxis_gate_action(config, [action, project, remaining[0]])
    if action in {"finish", "commit-split", "deliver", "cleanup"}:
        if not remaining:
            fail(f"usage: task project -- {action} {project} <需求名>")
        return run_praxis_delivery_action(config, [action, project, remaining[0], *remaining[1:]])
    if project == "docs":
        return run_project_action(config, project, action, remaining, via_praxis=True)
    fail(f"unknown praxis project action: {action}")


def run_praxis_gate_action(config: dict, args: list[str]) -> int:
    """Run Praxis quality gates."""
    if not args:
        fail(
            "usage: task gate -- "
            "<ready|ready-all|guard|change-check|migration-check|validate-verdict|import-verdict> ..."
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
    if action == "validate-verdict":
        if len(args) < 5:
            fail(
                "usage: task gate -- validate-verdict "
                "quality|delivery <project> <需求名> <json-file>"
            )
        return praxis_validate_verdict_file(args[4], args[1], args[2], args[3])
    if action == "import-verdict":
        if len(args) < 5:
            fail(
                "usage: task gate -- import-verdict "
                "quality|delivery <project> <需求名> <agent-output-json>"
            )
        return praxis_import_verdict_file(args[4], args[1], args[2], args[3])
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


def run_praxis_role_action(config: dict, args: list[str]) -> int:
    """Generate machine-readable handoff/lock packets for AI role boundary controls."""
    if len(args) < 4:
        fail(
            "usage: task role -- "
            "<handoff|lock> <role> <project> <需求名> <summary|write_scope...>"
        )
    action, role, project, requirement = args[0], args[1], args[2], args[3]
    context_packet = praxis_context_packet(config, project, requirement)
    if not isinstance(context_packet, Path):
        context_packet = PRAXIS_CONTEXT_DIR / safe_packet_name(project, requirement)
    if action == "handoff":
        if len(args) < 5:
            fail(
                "usage: task role -- handoff "
                "<quality|delivery|execution|knowledge> <project> <需求名> <summary>"
            )
        praxis_write_role_handoff(
            project=project,
            requirement_name=requirement,
            role=role,
            summary=" ".join(args[4:]),
            context_packet=context_packet,
        )
        return 0
    if action == "lock":
        if len(args) < 5:
            fail(
                "usage: task role -- lock "
                "<execution|delivery|quality|knowledge> <project> <需求名> <路径1> [路径2...]"
            )
        praxis_write_lock(
            project=project,
            requirement_name=requirement,
            role=role,
            write_scope=args[4:],
            context_packet=context_packet,
        )
        return 0
    fail(f"unknown praxis role action: {action}")


def run_praxis_delivery_action(config: dict, args: list[str]) -> int:
    """Run Praxis delivery actions."""
    if len(args) < 1:
        fail("usage: task delivery -- <status|status-all|finish|precheck-all|commit-split|commit-split-all|deliver|deliver-all|cleanup|cleanup-all> ...")
    action = args[0]
    if action == "precheck-all":
        if len(args) < 2:
            fail("usage: task delivery -- precheck-all <需求名> [--projects <project,project...>]")
        _, remaining = split_project_filter(args[2:])
        if remaining:
            fail("usage: task delivery -- precheck-all <需求名> [--projects <project,project...>]")
        praxis_write_delivery_precheck_packet(args[1], delivery_target_projects(config, args[1], args[2:]))
        return 0
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
        if praxis_require_verdict("quality", project, requirement):
            return 1
        message = " ".join(args[3:]) if len(args) > 3 else None
        split_commit_requirement(config, project, requirement, message)
        return 0
    if action == "deliver":
        if praxis_require_verdict("quality", project, requirement):
            return 1
        if praxis_require_verdict("delivery", project, requirement):
            return 1
        deliver_requirement(config, project, requirement)
        return 0
    if action == "cleanup":
        if praxis_require_verdict("quality", project, requirement):
            return 1
        if praxis_require_verdict("delivery", project, requirement):
            return 1
        cleanup_requirement(config, project, requirement)
        return 0
    fail(f"unknown praxis delivery action: {action}")


def run_project_action(config: dict, project: str, action: str, args: list[str], via_praxis: bool = False) -> int:
    """根据 action 分发到对应模块，保持 task.py 入口轻量。"""
    if not via_praxis:
        print(
            "[compat] legacy command detected; recommend "
            f"task project -- {action} {project} "
            + (" ".join(args) if args else "")
        )
    if action == "start":
        if len(args) < 2:
            fail("usage: task project -- start <project> <简短中文需求名> <用户原始需求原文>")
        start_requirement(config, project, args[0], " ".join(args[1:]))
        return 0
    if action in {"finish", "commit-split", "deliver", "cleanup"}:
        if not args:
            fail(f"usage: task project -- {action} <project> <简短中文需求名>")
        return run_praxis_delivery_action(config, [action, project, args[0], *args[1:]])
    if action == "preflight":
        if not args:
            fail(f"usage: task project -- {action} <project> <简短中文需求名>")
        praxis_context_packet(config, project, args[0])
        return preflight(config, project, args[0])
    if action in {"guard", "change-check", "migration-check"}:
        if not args:
            fail(f"usage: task project -- {action} <project> <简短中文需求名>")
        return run_praxis_gate_action(config, [action, project, args[0]])
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
    elif project == "docs" and action == "init":
        if len(args) < 2:
            fail("usage: task req -- init <简短中文需求名> <用户原始需求原文>")
        doc_init(config, args[0], " ".join(args[1:]))
    elif project == "docs" and action == "iter":
        if len(args) < 3:
            fail(
                "usage: task req -- "
                "iter <简短中文需求名> analysis|plan|progress <主题>"
            )
        doc_iter(config, args[0], args[1], " ".join(args[2:]))
    elif project == "docs" and action == "check":
        if not args:
            fail("usage: task req -- check <简短中文需求名>")
        raise SystemExit(docs_check(config, args[0]))
    elif project == "docs" and action == "index":
        if not args:
            fail("usage: task req -- index <简短中文需求名>")
        raise SystemExit(docs_index(config, args[0]))
    elif project == "docs" and action == "db-plan":
        if not args:
            fail("usage: task req -- db-plan <简短中文需求名>")
        raise SystemExit(db_plan(config, args[0]))
    else:
        fail(f"unknown action: {action}")
    return 0


def main(argv: list[str]) -> None:
    """加载配置并执行用户请求的 Codex 自动化命令。"""
    if argv and argv[0] in TOP_LEVEL_ACTIONS:
        raise SystemExit(run_praxis_action(argv[0], argv[1:]))
    explicit_project_mode = bool(argv and argv[0] == "project")

    parser = build_parser()
    args = parser.parse_args(normalize_argv(argv))
    config = load_config()

    if args.mode == "list":
        list_projects(config)
        return

    if args.mode == "context":
        if args.brief:
            praxis_context_packet(config, args.project, args.requirement_name)
            context_brief_command(config, args.project, args.requirement_name)
        else:
            praxis_context_packet(config, args.project, args.requirement_name)
            context_command(config, args.project, args.requirement_name)
        return

    if args.mode == "etl":
        run_etl_action(config, args.args)
        return

    if args.mode == "praxis":
        print("[compat] legacy praxis command detected; use task <group> ... instead")
        raise SystemExit(run_praxis_action(args.action, args.args))

    if args.mode == "workflow":
        print("[compat] legacy workflow command detected; use task system -- check or task <group> -- ...")
        raise SystemExit(run_praxis_action(args.action, args.args))

    if args.mode != "project":
        parser.print_help()
        raise SystemExit(0)

    project, action, remaining = normalize_project_args(args.project, args.action, args.args)
    exit_code = run_project_action(config, project, action, remaining, via_praxis=explicit_project_mode)
    if exit_code:
        raise SystemExit(exit_code)


if __name__ == "__main__":
    main(sys.argv[1:])
