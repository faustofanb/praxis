from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from praxis import __version__
from praxis.delivery.service import DeliveryService
from praxis.errors import PraxisError
from praxis.output import emit, envelope, error_envelope
from praxis.profiles.resolver import ProfileResolver
from praxis.projects.registry import ProjectRegistry
from praxis.requirements.service import RequirementService
from praxis.tasks.service import TaskService
from praxis.verification.service import VerificationService
from praxis.workspace.service import WorkspaceService

HELP = """Praxis Next - 平台无关执行内核

用法：praxis <命令组> <命令> [选项]

命令组：
  workspace   工作区 init/inspect/check
  profile     profile list/resolve/check
  project     项目 list/inspect
  task        任务 quick-start/quick-check/resume/formal-start
  requirement 需求 create/inspect/transition/close
  verify      验证 run
  delivery    交付 prepare/check
  doctor      环境诊断
"""


def main(argv: Sequence[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    as_json = "--json" in args
    args = [a for a in args if a != "--json"]
    if not args or args[0] in {"-h", "--help"}:
        print(HELP)
        return 0
    command = ".".join(args[:2]) if len(args) > 1 else args[0]
    try:
        data, diagnostics = dispatch(args)
        emit(envelope(command, data, diagnostics), as_json=as_json)
        return 0
    except PraxisError as exc:
        payload = error_envelope(command, exc.code, exc.message, exc.details)
        emit(payload, as_json=True if as_json else False)
        return exc.exit_code
    except Exception:
        if as_json:
            emit(error_envelope(command, "UNEXPECTED_ERROR", "发生未预期错误。"), as_json=True)
            return 1
        raise


def dispatch(args: list[str]) -> tuple[object, list[dict]]:
    group = args[0]
    cwd = Path.cwd()
    if group == "workspace":
        if len(args) > 1 and args[1] == "check":
            return WorkspaceService(cwd).check()
        return workspace_cmd(args[1:], cwd), []
    if group == "profile":
        return profile_cmd(args[1:]), []
    if group == "project":
        return project_cmd(args[1:], cwd), []
    if group == "task":
        return task_cmd(args[1:], cwd), []
    if group == "requirement":
        return requirement_cmd(args[1:], cwd), []
    if group == "verify":
        data = verify_cmd(args[1:], cwd)
        return data, []
    if group == "delivery":
        return delivery_cmd(args[1:], cwd), []
    if group == "doctor":
        return doctor_cmd(args[1:])
    raise PraxisError("COMMAND_NOT_FOUND", "未知 Praxis 命令。", 2, {"command": group})


def parse_option(args: list[str], name: str, default: str | None = None) -> str | None:
    if name not in args:
        return default
    idx = args.index(name)
    try:
        return args[idx + 1]
    except IndexError as exc:
        raise PraxisError("ARGUMENT_REQUIRED", "命令参数缺少取值。", 2, {"option": name}) from exc


def parse_projects(args: list[str], root: Path) -> list[dict] | None:
    projects = None
    i = 0
    while i < len(args):
        if args[i] == "--project":
            raw = args[i + 1]
            pid, kind, path = raw.split(":", 2)
            p = Path(path)
            if p.is_absolute() and root in p.resolve().parents:
                path = str(p.resolve().relative_to(root.resolve()))
            if projects is None:
                projects = []
            projects.append({"id": pid, "type": kind, "path": path})
            i += 2
        else:
            i += 1
    return projects


def workspace_cmd(args: list[str], cwd: Path) -> object:
    action = args[0]
    service = WorkspaceService(cwd)
    if action == "init":
        profile = parse_option(args, "--profile", "base") or "base"
        return service.init(profile_id=profile, projects=parse_projects(args, cwd))
    if action == "inspect":
        return service.inspect()
    if action == "check":
        data, _diagnostics = service.check()
        return data
    raise PraxisError("COMMAND_NOT_FOUND", "未知 workspace 命令。", 2)


def profile_cmd(args: list[str]) -> object:
    resolver = ProfileResolver()
    action = args[0]
    if action == "list":
        return {"profiles": resolver.list_profiles()}
    if action in {"resolve", "check"}:
        return resolver.resolve(args[1]).to_dict()
    raise PraxisError("COMMAND_NOT_FOUND", "未知 profile 命令。", 2)


def project_cmd(args: list[str], cwd: Path) -> object:
    registry = ProjectRegistry(cwd)
    if args[0] == "list":
        return {"projects": registry.list()}
    if args[0] == "inspect":
        return registry.inspect(args[1])
    raise PraxisError("COMMAND_NOT_FOUND", "未知 project 命令。", 2)


def task_cmd(args: list[str], cwd: Path) -> object:
    service = TaskService(cwd)
    action = args[0]
    if action == "quick-start":
        return service.quick_start(
            {"id": parse_option(args, "--id"), "title": parse_option(args, "--title", "")}
        )
    if action == "formal-start":
        return service.formal_start(
            {"id": parse_option(args, "--id"), "title": parse_option(args, "--title", "")}
        )
    if action == "resume":
        return service.resume(args[1])
    if action == "quick-check":
        return service.quick_check(args[1])
    raise PraxisError("COMMAND_NOT_FOUND", "未知 task 命令。", 2)


def requirement_cmd(args: list[str], cwd: Path) -> object:
    service = RequirementService(cwd)
    action = args[0]
    if action == "create":
        return service.create(
            parse_option(args, "--id") or "",
            parse_option(args, "--task") or "",
            parse_option(args, "--title", "") or "",
        )
    if action == "inspect":
        return service.inspect(args[1])
    if action == "transition":
        return service.transition(args[1], parse_option(args, "--status") or "draft")
    if action == "close":
        return service.close(args[1])
    raise PraxisError("COMMAND_NOT_FOUND", "未知 requirement 命令。", 2)


def verify_cmd(args: list[str], cwd: Path) -> object:
    if args[0] != "run":
        raise PraxisError("COMMAND_NOT_FOUND", "未知 verify 命令。", 2)
    files = []
    for i, arg in enumerate(args):
        if arg == "--changed-file" and i + 1 < len(args):
            files.append(args[i + 1])
    return VerificationService(cwd).run(files)


def delivery_cmd(args: list[str], cwd: Path) -> object:
    if args[0] == "prepare":
        return DeliveryService(cwd).prepare(parse_option(args, "--require-check"))
    if args[0] == "check":
        return DeliveryService(cwd).prepare(parse_option(args, "--require-check"))
    raise PraxisError("COMMAND_NOT_FOUND", "未知 delivery 命令。", 2)


def doctor_cmd(args: list[str]) -> tuple[object, list[dict]]:
    diagnostics: list[dict] = []
    mise = shutil.which("mise")
    if mise:
        proc = subprocess.run([mise, "--version"], text=True, capture_output=True, check=False)
        diagnostics.append(
            {"code": "MISE_STATUS", "message": "mise 可用。", "version": proc.stdout.strip()}
        )
    else:
        diagnostics.append(
            {
                "code": "MISE_MISSING",
                "message": "未找到 mise；请执行官方安装步骤后运行 mise install。",
            }
        )
    return {
        "version": __version__,
        "runtime": "python",
        "check_vendor": "--check-vendor" in args,
    }, diagnostics
