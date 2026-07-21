from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
from collections.abc import Callable, Sequence
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from praxis.artifacts.service import ArtifactService
from praxis.codegraph.service import CodeGraphService
from praxis.naming.requirement import RequirementPathPolicy
from praxis.result import Result
from praxis.storage.sqlite import StateStore
from praxis.workspace.service import Project, WorkspaceService

Runner = Callable[[list[str], Path, dict[str, str] | None], subprocess.CompletedProcess[str]]
GraphInitializer = Callable[[str, Path], Result]

_STAGES = {
    "development": (0, "开发"),
    "analysis": (1, "需求分析"),
    "backend": (2, "后端开发"),
    "frontend": (3, "前端开发"),
    "database": (4, "数据库开发"),
    "integration-test": (5, "联合测试"),
    "review": (6, "代码审查"),
    "release": (7, "发布验证"),
}
_GIT_REF_UNSAFE = re.compile(r"[\x00-\x20\x7f~^:?*\[\]\\]+")


@dataclass(frozen=True, slots=True)
class WorktreeNames:
    requirement_id: str
    short_name_snapshot: str
    display_slug: str
    workspace_name: str
    worktree_display_name: str
    branch_name: str


def worktree_binding_id(requirement_id: str, repository_id: str) -> str:
    return f"WT-{requirement_id}--{repository_id}"


def resolve_worktree_binding(
    store: StateStore,
    identifier: str,
    *,
    repository_id: str = "",
    worktree_path: str | Path | None = None,
) -> tuple[str, dict[str, Any]] | None:
    """Resolve both new stable binding IDs and legacy branch-keyed bindings."""
    direct = store.get("worktree", identifier) if identifier else None
    if direct:
        return identifier, direct
    expected_path = Path(worktree_path).resolve() if worktree_path else None
    candidates: list[tuple[str, dict[str, Any]]] = []
    for binding in store.list_scope("worktree"):
        key = str(binding.get("binding_id") or binding.get("branch", ""))
        if identifier and identifier not in {key, str(binding.get("branch", ""))}:
            continue
        if repository_id and binding.get("repository_id") != repository_id:
            continue
        if expected_path:
            repository_path = Path(
                str(binding.get("repository_path") or binding.get("path", ""))
            ).resolve()
            if repository_path != expected_path:
                continue
        candidates.append((key, binding))
    return candidates[0] if len(candidates) == 1 else None


class WorktreeService:
    def __init__(
        self,
        root: Path | str,
        *,
        run: Runner | None = None,
        initialize_graph: GraphInitializer | None = None,
    ):
        self.root = Path(root)
        self.run = run or self._run
        self.initialize_graph = initialize_graph or self._initialize_graph

    @staticmethod
    def _build_names(
        requirement_id: str,
        short_name: str,
        repository_id: str,
    ) -> WorktreeNames:
        policy = RequirementPathPolicy(Path("."))
        policy.validate_requirement_id(requirement_id)
        normalized = policy.validate_short_name(short_name)
        slug = _GIT_REF_UNSAFE.sub("-", normalized)
        while ".." in slug:
            slug = slug.replace("..", "-")
        slug = slug.replace("@{", "-")
        slug = re.sub(r"-+", "-", slug).strip(".-")
        if slug.casefold().endswith(".lock"):
            slug = f"{slug[:-5]}-lock"
        if not slug:
            raise ValueError("需求简称清理后不能为空")
        workspace_name = f"{requirement_id}__{slug}"
        return WorktreeNames(
            requirement_id=requirement_id,
            short_name_snapshot=normalized,
            display_slug=slug,
            workspace_name=workspace_name,
            worktree_display_name=f"{workspace_name}__{repository_id}",
            branch_name=f"praxis/{workspace_name}",
        )

    def _names_for_requirement(
        self,
        store: StateStore,
        requirement: dict[str, Any],
        repository_id: str,
    ) -> WorktreeNames:
        requirement_id = str(requirement["requirement_id"])
        group_id = f"WTG-{requirement_id}"
        group = store.get("worktree_group", group_id)
        if group:
            workspace_name = str(group["workspace_name"])
            return WorktreeNames(
                requirement_id=requirement_id,
                short_name_snapshot=str(group["short_name_snapshot"]),
                display_slug=str(group["display_slug"]),
                workspace_name=workspace_name,
                worktree_display_name=f"{workspace_name}__{repository_id}",
                branch_name=str(group["branch_name"]),
            )
        legacy_slug = ""
        prefix = f"{requirement_id}__"
        for binding in store.list_scope("worktree"):
            if binding.get("requirement_id") != requirement_id:
                continue
            legacy_workspace = Path(str(binding.get("path", ""))).name
            if legacy_workspace.startswith(prefix):
                legacy_slug = legacy_workspace.removeprefix(prefix)
                break
        names = self._build_names(
            requirement_id,
            legacy_slug or str(requirement["short_name"]),
            repository_id,
        )
        group = {
            "group_id": group_id,
            "requirement_id": requirement_id,
            "short_name_snapshot": names.short_name_snapshot,
            "display_slug": names.display_slug,
            "workspace_name": names.workspace_name,
            "branch_name": names.branch_name,
            "created_at": datetime.now(UTC).isoformat(),
        }
        store.set("worktree_group", group_id, group)
        store.audit("worktree.group_named", "OK", group)
        return names

    def _validate_display_names(
        self,
        names: WorktreeNames,
        repository_id: str,
        repo: Path,
    ) -> Result:
        if names.requirement_id not in names.worktree_display_name or (
            names.display_slug not in names.worktree_display_name
        ):
            return Result(False, "WORKTREE_DISPLAY_NAME_INVALID", data=asdict(names))
        if names.requirement_id not in names.branch_name or (
            names.display_slug not in names.branch_name
        ):
            return Result(False, "WORKTREE_BRANCH_NAME_INVALID", data=asdict(names))
        if not names.worktree_display_name.endswith(f"__{repository_id}"):
            return Result(False, "WORKTREE_DISPLAY_NAME_INVALID", data=asdict(names))
        reference = self._git(
            ["check-ref-format", "--branch", names.branch_name],
            cwd=repo,
            failure_code="WORKTREE_BRANCH_NAME_INVALID",
        )
        if not reference.ok:
            return reference
        return Result(True, data=asdict(names))

    @staticmethod
    def _binding_matches_names(
        binding: dict[str, Any], names: WorktreeNames
    ) -> bool:
        return (
            str(binding.get("workspace_name", "")) == names.workspace_name
            and str(binding.get("worktree_display_name", ""))
            == names.worktree_display_name
            and str(binding.get("branch", "")) == names.branch_name
            and Path(str(binding.get("path", ""))).name == names.workspace_name
            and Path(str(binding.get("repository_path", ""))).name
            == names.worktree_display_name
        )

    def _initialize_graph(self, project_id: str, repository_path: Path) -> Result:
        return CodeGraphService(
            self.root,
            project_id,
            repo=repository_path,
        ).ensure_fresh(initialize=True)

    @staticmethod
    def _prepare_local_files(
        project: Project,
        source_root: Path,
        destination_root: Path,
    ) -> Result:
        if not project.local_files:
            return Result(True, "WORKTREE_LOCAL_FILES_NOT_CONFIGURED")
        source_root = source_root.resolve()
        destination_root = destination_root.resolve()
        prepared: list[tuple[str, Path, Path]] = []
        for relative in project.local_files:
            source_candidate = source_root / relative
            source = source_candidate.resolve()
            destination = destination_root / relative
            if not source.is_relative_to(source_root) or source_candidate.is_symlink():
                return Result(
                    False,
                    "WORKTREE_LOCAL_FILE_SOURCE_UNSAFE",
                    data={"path": relative},
                )
            if not source.is_file():
                return Result(
                    False,
                    "WORKTREE_LOCAL_FILE_SOURCE_MISSING",
                    data={"path": relative},
                )
            if not destination.resolve(strict=False).is_relative_to(destination_root):
                return Result(
                    False,
                    "WORKTREE_LOCAL_FILE_TARGET_UNSAFE",
                    data={"path": relative},
                )
            if destination.exists() and (
                not destination.is_file() or destination.is_symlink()
            ):
                return Result(
                    False,
                    "WORKTREE_LOCAL_FILE_TARGET_UNSAFE",
                    data={"path": relative},
                )
            prepared.append((relative, source, destination))

        copied: list[str] = []
        existing: list[str] = []
        for relative, source, destination in prepared:
            if destination.exists():
                existing.append(relative)
                continue
            try:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
            except OSError as error:
                return Result(
                    False,
                    "WORKTREE_LOCAL_FILE_COPY_FAILED",
                    data={"path": relative, "message": str(error)},
                )
            copied.append(relative)
        return Result(
            True,
            "WORKTREE_LOCAL_FILES_PREPARED",
            data={"copied": copied, "existing": existing},
        )

    def _activate_binding(
        self,
        store: StateStore,
        binding_key: str,
        binding: dict[str, Any],
        *,
        success_code: str = "OK",
    ) -> Result:
        project = WorkspaceService(self.root).project(str(binding["repository_id"]))
        local_files = self._prepare_local_files(
            project,
            (self.root / project.path).resolve(),
            Path(str(binding["repository_path"])),
        )
        binding["local_files_status"] = local_files.code
        if project.local_files:
            binding["local_files"] = list(project.local_files)
        if not local_files.ok:
            binding["status"] = "blocked"
            store.set("worktree", binding_key, binding)
            audit_id = store.audit(
                "worktree.local_files_failed",
                local_files.code,
                {**binding, "local_files_result": local_files.data},
            )
            return Result(
                False,
                "WORKTREE_LOCAL_FILES_PREPARE_FAILED",
                data={
                    **binding,
                    "cause": local_files.code,
                    "local_files_result": local_files.data,
                    "audit_id": audit_id,
                },
            )
        if project.local_files:
            binding["local_files_copied"] = local_files.data.get("copied", [])
            binding["local_files_existing"] = local_files.data.get("existing", [])
            store.audit(
                "worktree.local_files_prepared",
                local_files.code,
                binding,
            )
        setup_fingerprint = hashlib.sha256(
            json.dumps(
                project.worktree_setup_commands,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        setup_already_prepared = (
            bool(project.worktree_setup_commands)
            and binding.get("status") == "active"
            and binding.get("worktree_setup_status") == "WORKTREE_SETUP_COMPLETED"
            and binding.get("worktree_setup_fingerprint") == setup_fingerprint
        )
        if not project.worktree_setup_commands:
            binding["worktree_setup_status"] = "WORKTREE_SETUP_NOT_CONFIGURED"
            binding["worktree_setup_commands_configured"] = 0
            for key in (
                "worktree_setup_commands_completed",
                "worktree_setup_fingerprint",
                "worktree_setup_started_at",
                "worktree_setup_completed_at",
                "worktree_setup_last_action",
            ):
                binding.pop(key, None)
        elif setup_already_prepared:
            binding["worktree_setup_last_action"] = "WORKTREE_SETUP_ALREADY_PREPARED"
        else:
            binding.pop("worktree_setup_last_action", None)
            binding.update(
                status="initializing",
                worktree_setup_status="WORKTREE_SETUP_RUNNING",
                worktree_setup_commands_configured=len(
                    project.worktree_setup_commands
                ),
                worktree_setup_commands_completed=0,
                worktree_setup_fingerprint=setup_fingerprint,
                worktree_setup_started_at=datetime.now(UTC).isoformat(),
            )
            binding.pop("worktree_setup_completed_at", None)
            store.set("worktree", binding_key, binding)
            store.audit("worktree.setup_started", "OK", binding)
            setup = self._run_worktree_setup_commands(
                project,
                Path(str(binding["repository_path"])),
            )
            binding["worktree_setup_status"] = setup.code
            binding["worktree_setup_commands_completed"] = setup.data.get(
                "completed", 0
            )
            if not setup.ok:
                binding["status"] = "blocked"
                store.set("worktree", binding_key, binding)
                audit_id = store.audit(
                    "worktree.setup_failed",
                    setup.code,
                    {**binding, "worktree_setup_result": setup.data},
                )
                return Result(
                    False,
                    "WORKTREE_SETUP_FAILED",
                    data={
                        **binding,
                        "cause": setup.code,
                        "worktree_setup_result": setup.data,
                        "audit_id": audit_id,
                    },
                )
            binding["worktree_setup_completed_at"] = datetime.now(UTC).isoformat()
            store.set("worktree", binding_key, binding)
            store.audit("worktree.setup_completed", setup.code, binding)
        started_at = datetime.now(UTC).isoformat()
        binding.update(
            status="initializing",
            codegraph_attempt=int(binding.get("codegraph_attempt", 0)) + 1,
            codegraph_started_at=started_at,
        )
        binding.pop("codegraph_completed_at", None)
        store.set("worktree", binding_key, binding)
        store.audit("worktree.codegraph_initializing", "OK", binding)
        graph = self.initialize_graph(
            str(binding["repository_id"]),
            Path(str(binding["repository_path"])),
        )
        binding["codegraph_status"] = graph.code
        if graph.code == "CODEGRAPH_SYNC_BUSY":
            binding["status"] = "initializing"
            store.set("worktree", binding_key, binding)
            audit_id = store.audit(
                "worktree.codegraph_initializing",
                graph.code,
                {**binding, "codegraph": graph.data},
            )
            return Result(
                False,
                "WORKTREE_CODEGRAPH_INITIALIZING",
                data={
                    **binding,
                    "cause": graph.code,
                    "codegraph": graph.data,
                    "audit_id": audit_id,
                },
                diagnostics=graph.diagnostics,
            )
        binding["codegraph_completed_at"] = datetime.now(UTC).isoformat()
        if not graph.ok:
            binding["status"] = "blocked"
            store.set("worktree", binding_key, binding)
            store.audit(
                "worktree.codegraph_init_failed",
                graph.code,
                {**binding, "codegraph": graph.data},
            )
            return Result(
                False,
                "WORKTREE_CODEGRAPH_INIT_FAILED",
                data={**binding, "cause": graph.code, "codegraph": graph.data},
                diagnostics=graph.diagnostics,
            )
        binding["status"] = "active"
        store.set("worktree", binding_key, binding)
        store.audit(
            "worktree.codegraph_initialized",
            graph.code,
            {**binding, "codegraph": graph.data},
        )
        return Result(True, success_code, data=binding, diagnostics=graph.diagnostics)

    def _run_worktree_setup_commands(
        self, project: Project, repository_path: Path
    ) -> Result:
        if not project.worktree_setup_commands:
            return Result(True, "WORKTREE_SETUP_NOT_CONFIGURED", data={"completed": 0})
        completed = 0
        for index, configured in enumerate(project.worktree_setup_commands, start=1):
            command = shlex.split(configured)
            executable = command[0]
            try:
                process = self.run(command, repository_path, None)
            except FileNotFoundError:
                return Result(
                    False,
                    "WORKTREE_SETUP_COMMAND_NOT_FOUND",
                    data={
                        "command_index": index,
                        "executable": executable,
                        "completed": completed,
                    },
                )
            if process.returncode:
                return Result(
                    False,
                    "WORKTREE_SETUP_COMMAND_FAILED",
                    data={
                        "command_index": index,
                        "executable": executable,
                        "exit_code": process.returncode,
                        "completed": completed,
                    },
                )
            completed += 1
        return Result(
            True,
            "WORKTREE_SETUP_COMPLETED",
            data={"completed": completed},
        )

    @staticmethod
    def _run(
        command: Sequence[str], cwd: Path, environment: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            cwd=cwd,
            env={**os.environ, **(environment or {})},
            check=False,
            capture_output=True,
            text=True,
        )

    def _execute(
        self,
        arguments: Sequence[str],
        *,
        cwd: Path | None = None,
        environment: dict[str, str] | None = None,
    ) -> Result:
        command = ["wt", *arguments, "--format=json", "--yes"]
        try:
            process = self.run(command, cwd or self.root, environment)
        except FileNotFoundError:
            return Result(False, "WORKTRUNK_NOT_AVAILABLE")
        if process.returncode:
            return Result(False, "WORKTRUNK_FAILED", data={"stderr": process.stderr.strip()})
        try:
            payload: Any = json.loads(process.stdout)
        except json.JSONDecodeError:
            return Result(False, "WORKTRUNK_OUTPUT_INVALID")
        data = payload if isinstance(payload, dict) else {"items": payload}
        return Result(True, data=data)

    def create(self, branch: str, base: str) -> Result:
        return self._execute(["switch", "--create", branch, "--base", base, "--no-cd"])

    def _git(self, arguments: Sequence[str], *, cwd: Path, failure_code: str) -> Result:
        command = ["git", *arguments]
        try:
            process = self.run(command, cwd, None)
        except FileNotFoundError:
            return Result(False, "GIT_NOT_AVAILABLE")
        if process.returncode:
            return Result(
                False,
                failure_code,
                data={
                    "command": command,
                    "cwd": str(cwd),
                    "stderr": process.stderr.strip(),
                },
            )
        return Result(
            True,
            data={
                "command": command,
                "cwd": str(cwd),
                "stdout": process.stdout.strip(),
            },
        )

    def _sync_default_branch(
        self, project: Project, repository_id: str, repo: Path
    ) -> Result:
        if not project.template_branches:
            return Result(False, "WORKTREE_TEMPLATE_BRANCH_REQUIRED")
        if len(project.template_branches) != 1:
            return Result(
                False,
                "WORKTREE_TEMPLATE_BRANCH_AMBIGUOUS",
                data={"template_branches": list(project.template_branches)},
            )
        upstream = project.template_branches[0]
        fetched = self._git(
            ["fetch", "origin", upstream],
            cwd=repo,
            failure_code="WORKTREE_TEMPLATE_FETCH_FAILED",
        )
        if not fetched.ok:
            return fetched

        destination = (self.root / ".worktrees" / ".templates" / repository_id).resolve()
        switched = self._execute(
            ["switch", project.default_branch, "--no-cd", "--no-hooks"],
            cwd=repo,
            environment={"WORKTRUNK_WORKTREE_PATH": str(destination)},
        )
        if not switched.ok:
            return Result(
                False,
                "WORKTREE_TEMPLATE_WORKTREE_FAILED",
                data=switched.data,
            )
        worktree_value = switched.data.get("path")
        if not worktree_value:
            return Result(False, "WORKTREE_TEMPLATE_PATH_MISSING")
        worktree = Path(str(worktree_value))
        if not worktree.is_absolute():
            worktree = repo / worktree
        worktree = worktree.resolve()

        status = self._git(
            ["status", "--porcelain"],
            cwd=worktree,
            failure_code="WORKTREE_TEMPLATE_STATUS_FAILED",
        )
        if not status.ok:
            return status
        if status.data["stdout"]:
            return Result(
                False,
                "WORKTREE_TEMPLATE_DIRTY",
                data={"path": str(worktree), "branch": project.default_branch},
            )

        remote_branch = f"origin/{upstream}"
        merged = self._git(
            ["merge", "--no-edit", remote_branch],
            cwd=worktree,
            failure_code="WORKTREE_TEMPLATE_MERGE_FAILED",
        )
        if not merged.ok:
            return Result(
                False,
                merged.code,
                data={
                    **merged.data,
                    "path": str(worktree),
                    "branch": project.default_branch,
                },
            )
        revision = self._git(
            ["rev-parse", "HEAD"],
            cwd=worktree,
            failure_code="WORKTREE_TEMPLATE_REVISION_FAILED",
        )
        if not revision.ok:
            return revision
        return Result(
            True,
            data={
                "local_branch": project.default_branch,
                "upstream_branch": remote_branch,
                "path": str(worktree),
                "revision": revision.data["stdout"],
            },
        )

    def create_for_requirement(
        self,
        requirement_id: str,
        repository_id: str,
        stage: str | None = None,
    ) -> Result:
        stage = stage or "development"
        if stage not in _STAGES:
            raise ValueError(f"未知任务阶段：{stage}")
        workspace = WorkspaceService(self.root)
        project = workspace.project(repository_id)
        requirement = StateStore(self.root).requirement(requirement_id)
        if not requirement:
            raise KeyError(requirement_id)
        if requirement["status"] not in {"ready", "in_progress", "verifying"}:
            return Result(False, "REQUIREMENT_NOT_READY", data={"status": requirement["status"]})
        if project.system_id not in requirement["systems"]:
            return Result(False, "WORKTREE_SYSTEM_MISMATCH")
        store = StateStore(self.root)
        names = self._names_for_requirement(store, requirement, repository_id)
        repo = (self.root / project.path).resolve()
        display_names = self._validate_display_names(names, repository_id, repo)
        if not display_names.ok:
            return display_names
        branch = names.branch_name
        workspace_path = (
            self.root
            / ".worktrees"
            / names.workspace_name
        ).resolve()
        repository_path = (workspace_path / names.worktree_display_name).resolve()
        binding_id = worktree_binding_id(requirement_id, repository_id)
        existing = resolve_worktree_binding(store, binding_id)
        if existing and existing[1].get("status") in {
            "active",
            "blocked",
            "initializing",
            "migrating",
        }:
            binding = existing[1]
            if binding.get("status") == "migrating":
                return Result(
                    False,
                    "WORKTREE_NAME_MIGRATION_IN_PROGRESS",
                    data={"binding_id": existing[0]},
                )
            if not self._binding_matches_names(binding, names):
                return Result(
                    False,
                    "WORKTREE_NAME_MIGRATION_REQUIRED",
                    data={
                        "binding_id": existing[0],
                        "current": {
                            "workspace_path": binding.get("path"),
                            "repository_path": binding.get("repository_path"),
                            "branch": binding.get("branch"),
                        },
                        "expected": {
                            "workspace_path": str(workspace_path),
                            "repository_path": str(repository_path),
                            "branch": branch,
                        },
                    },
                )
            stages = list(dict.fromkeys([*binding.get("stages", []), stage]))
            binding.update(stage=stage, stages=stages)
            return self._activate_binding(
                store,
                existing[0],
                binding,
                success_code="WORKTREE_ALREADY_ACTIVE",
            )
        if requirement["status"] not in {"ready", "in_progress"}:
            return Result(False, "REQUIREMENT_NOT_READY", data={"status": requirement["status"]})
        synchronized = self._sync_default_branch(project, repository_id, repo)
        if not synchronized.ok:
            store.audit(
                "worktree.template_sync_failed",
                synchronized.code,
                {
                    "requirement_id": requirement_id,
                    "repository_id": repository_id,
                    **synchronized.data,
                },
            )
            return synchronized
        store.audit(
            "worktree.template_synced",
            "OK",
            {
                "requirement_id": requirement_id,
                "repository_id": repository_id,
                **synchronized.data,
            },
        )
        binding = {
            "binding_id": binding_id,
            "group_id": f"WTG-{requirement_id}",
            "workspace_name": names.workspace_name,
            "worktree_display_name": names.worktree_display_name,
            "display_slug": names.display_slug,
            "short_name_snapshot": names.short_name_snapshot,
            "requirement_id": requirement_id,
            "repository_id": repository_id,
            "stage": stage,
            "stages": [stage],
            "branch": branch,
            "base_branch": project.default_branch,
            "upstream_branch": synchronized.data["upstream_branch"],
            "base_revision": synchronized.data["revision"],
            "path": str(workspace_path),
            "repository_path": str(repository_path),
            "status": "creating",
            # ponytail: whole-repo scope until requirement stages persist explicit path scopes.
            "allowed_paths": ["**"],
            "forbidden_paths": [".git", ".praxis", ".env", "**/.env"],
        }
        store.set("worktree", binding_id, binding)
        result = self._execute(
            ["switch", "--create", branch, "--base", project.default_branch, "--no-cd"],
            cwd=repo,
            environment={"WORKTRUNK_WORKTREE_PATH": str(repository_path)},
        )
        if not result.ok:
            store.delete("worktree", binding_id)
            store.audit("worktree.create_failed", result.code, binding)
            return result
        activated = self._activate_binding(store, binding_id, binding)
        if activated.ok:
            store.audit("worktree.created", "OK", activated.data)
        return activated

    def list(self) -> Result:
        if not (self.root / "praxis.toml").is_file():
            return self._execute(["list"])
        items = []
        for raw in WorkspaceService(self.root).load().get("projects", []):
            result = self._execute(["list"], cwd=(self.root / raw["path"]).resolve())
            if not result.ok:
                return result
            listed = result.data.get("items", result.data.get("worktrees", []))
            for item in listed:
                enriched = {**item, "repository_id": raw["id"]}
                identifier = str(item.get("branch") or item.get("name") or "")
                worktree_path = item.get("path")
                resolved = resolve_worktree_binding(
                    StateStore(self.root),
                    identifier,
                    repository_id=raw["id"],
                    worktree_path=worktree_path,
                )
                if resolved:
                    worktrunk_state = str(item.get("worktree", {}).get("state", ""))
                    enriched.update(
                        binding_id=resolved[0],
                        workspace_path=resolved[1]["path"],
                        binding_status=resolved[1]["status"],
                        worktrunk_state=worktrunk_state,
                    )
                    if resolved[1].get("status") == "active":
                        enriched["worktree"] = {
                            **item.get("worktree", {}),
                            "state": "bound_active",
                        }
                        enriched["symbols"] = str(item.get("symbols", "")).replace("⚑", "")
                        enriched["statusline"] = str(item.get("statusline", "")).replace(
                            "⚑", ""
                        )
                items.append(enriched)
        return Result(True, data={"items": items})

    def migrate_name(self, requirement_id: str, repository_id: str) -> Result:
        store = StateStore(self.root)
        requirement = store.requirement(requirement_id)
        if not requirement:
            return Result(False, "REQUIREMENT_NOT_FOUND")
        project = WorkspaceService(self.root).project(repository_id)
        if project.system_id not in requirement["systems"]:
            return Result(False, "WORKTREE_SYSTEM_MISMATCH")
        binding_id = worktree_binding_id(requirement_id, repository_id)
        resolved = resolve_worktree_binding(store, binding_id)
        if not resolved:
            return Result(False, "WORKTREE_BINDING_NOT_FOUND", data={"binding_id": binding_id})
        binding_key, binding = resolved
        if binding.get("status") not in {"active", "blocked", "initializing"}:
            return Result(
                False,
                "WORKTREE_MIGRATION_STATUS_INVALID",
                data={"status": binding.get("status")},
            )
        names = self._names_for_requirement(store, requirement, repository_id)
        repo = (self.root / project.path).resolve()
        display_names = self._validate_display_names(names, repository_id, repo)
        if not display_names.ok:
            return display_names
        expected_workspace = (self.root / ".worktrees" / names.workspace_name).resolve()
        expected_repository = (
            expected_workspace / names.worktree_display_name
        ).resolve()
        if self._binding_matches_names(binding, names):
            return Result(
                True,
                "WORKTREE_NAME_ALREADY_CURRENT",
                data={**binding, **asdict(names)},
            )
        old_workspace = Path(str(binding["path"])).resolve()
        old_repository = Path(str(binding["repository_path"])).resolve()
        old_branch = str(binding["branch"])
        if not old_repository.is_dir():
            return Result(
                False,
                "WORKTREE_MIGRATION_SOURCE_MISSING",
                data={"path": str(old_repository)},
            )
        if expected_repository.exists():
            return Result(
                False,
                "WORKTREE_MIGRATION_TARGET_EXISTS",
                data={"path": str(expected_repository)},
            )
        current_branch = self._git(
            ["branch", "--show-current"],
            cwd=old_repository,
            failure_code="WORKTREE_MIGRATION_BRANCH_READ_FAILED",
        )
        if not current_branch.ok:
            return current_branch
        if current_branch.data["stdout"] != old_branch:
            return Result(
                False,
                "WORKTREE_MIGRATION_BRANCH_MISMATCH",
                data={
                    "binding_branch": old_branch,
                    "actual_branch": current_branch.data["stdout"],
                },
            )
        collision = self._git(
            ["branch", "--list", names.branch_name],
            cwd=repo,
            failure_code="WORKTREE_MIGRATION_BRANCH_CHECK_FAILED",
        )
        if not collision.ok:
            return collision
        if collision.data["stdout"] and names.branch_name != old_branch:
            return Result(
                False,
                "WORKTREE_MIGRATION_BRANCH_EXISTS",
                data={"branch": names.branch_name},
            )

        old_binding = dict(binding)
        old_status = str(binding.get("status", "blocked"))
        old_graph = CodeGraphService(
            self.root,
            repository_id,
            repo=old_repository,
            codegraph_version="unknown",
        )
        old_graph_metadata = store.get("codegraph", old_graph.key)
        old_graph_operation = store.get("codegraph_operation", old_graph.key)
        if old_graph_operation and old_graph_operation.get("status") == "running":
            return Result(
                False,
                "WORKTREE_MIGRATION_CODEGRAPH_BUSY",
                data={"operation": old_graph_operation},
            )
        if (old_repository / ".codegraph" / "lock").exists():
            return Result(
                False,
                "WORKTREE_MIGRATION_CODEGRAPH_BUSY",
                data={"path": str(old_repository / ".codegraph" / "lock")},
            )
        artifact_snapshots = self._artifact_snapshots(requirement_id, old_repository)
        expected_workspace.mkdir(parents=True, exist_ok=True)
        backup_graph = expected_repository / ".codegraph.praxis-name-migration"
        moved = False
        branch_renamed = False
        binding.update(status="migrating", migration_started_at=datetime.now(UTC).isoformat())
        store.set("worktree", binding_key, binding)
        store.audit(
            "worktree.name_migration_started",
            "OK",
            {
                "binding_id": binding_key,
                "old_repository_path": str(old_repository),
                "new_repository_path": str(expected_repository),
                "old_branch": old_branch,
                "new_branch": names.branch_name,
            },
        )
        failure: Result | None = None
        try:
            moved_result = self._git(
                ["worktree", "move", str(old_repository), str(expected_repository)],
                cwd=repo,
                failure_code="WORKTREE_MIGRATION_MOVE_FAILED",
            )
            if not moved_result.ok:
                failure = moved_result
                raise RuntimeError(moved_result.code)
            moved = True
            if names.branch_name != old_branch:
                renamed = self._git(
                    ["branch", "-m", names.branch_name],
                    cwd=expected_repository,
                    failure_code="WORKTREE_MIGRATION_BRANCH_RENAME_FAILED",
                )
                if not renamed.ok:
                    failure = renamed
                    raise RuntimeError(renamed.code)
                branch_renamed = True
            graph_path = expected_repository / ".codegraph"
            if backup_graph.exists():
                failure = Result(
                    False,
                    "WORKTREE_MIGRATION_GRAPH_BACKUP_EXISTS",
                    data={"path": str(backup_graph)},
                )
                raise RuntimeError(failure.code)
            if graph_path.exists():
                graph_path.rename(backup_graph)
            store.delete("codegraph", old_graph.key)
            store.delete("codegraph_operation", old_graph.key)
            binding.update(
                **asdict(names),
                branch=names.branch_name,
                path=str(expected_workspace),
                repository_path=str(expected_repository),
                status="initializing",
            )
            store.set("worktree", binding_key, binding)
            self._relocate_artifacts(artifact_snapshots, old_repository, expected_repository)
            refreshed = ArtifactService(self.root).refresh_index(requirement_id)
            if not refreshed.ok:
                failure = refreshed
                raise RuntimeError(refreshed.code)
            graph = self.initialize_graph(repository_id, expected_repository)
            if not graph.ok:
                failure = Result(
                    False,
                    "WORKTREE_MIGRATION_CODEGRAPH_FAILED",
                    data={"cause": graph.code, "codegraph": graph.data},
                    diagnostics=graph.diagnostics,
                )
                raise RuntimeError(failure.code)
            cleanup_pending = False
            if backup_graph.exists():
                try:
                    shutil.rmtree(backup_graph)
                except OSError:
                    cleanup_pending = True
            binding.update(
                status=old_status,
                migration_completed_at=datetime.now(UTC).isoformat(),
                codegraph_status=graph.code,
                codegraph_backup_cleanup_pending=cleanup_pending,
            )
            store.set("worktree", binding_key, binding)
            with suppress(OSError):
                old_workspace.rmdir()
            audit_id = store.audit("worktree.name_migrated", "OK", binding)
            return Result(
                True,
                "WORKTREE_NAME_MIGRATED",
                data={**binding, "audit_id": audit_id},
                diagnostics=graph.diagnostics,
            )
        except (OSError, RuntimeError) as error:
            rollback = self._rollback_name_migration(
                store=store,
                binding_key=binding_key,
                old_binding=old_binding,
                old_repository=old_repository,
                expected_repository=expected_repository,
                old_branch=old_branch,
                moved=moved,
                branch_renamed=branch_renamed,
                backup_graph=backup_graph,
                old_graph_key=old_graph.key,
                old_graph_metadata=old_graph_metadata,
                old_graph_operation=old_graph_operation,
                artifact_snapshots=artifact_snapshots,
            )
            details = {
                "binding_id": binding_key,
                "cause": failure.code if failure else type(error).__name__,
                "rollback": rollback.data,
            }
            audit_id = store.audit(
                "worktree.name_migration_failed",
                "WORKTREE_NAME_MIGRATION_FAILED",
                details,
            )
            return Result(
                False,
                "WORKTREE_NAME_MIGRATION_FAILED",
                data={**details, "audit_id": audit_id},
                diagnostics=failure.diagnostics if failure else [],
            )

    def _artifact_snapshots(
        self, requirement_id: str, old_repository: Path
    ) -> dict[str, dict[str, Any]]:
        snapshots = {}
        for artifact in StateStore(self.root).list_scope("artifact"):
            source = Path(str(artifact.get("source_path", ""))).resolve()
            if artifact.get("requirement_id") == requirement_id and source.is_relative_to(
                old_repository
            ):
                snapshots[str(artifact["artifact_id"])] = dict(artifact)
        return snapshots

    def _relocate_artifacts(
        self,
        snapshots: dict[str, dict[str, Any]],
        source_root: Path,
        destination_root: Path,
    ) -> None:
        store = StateStore(self.root)
        for artifact_id, artifact in snapshots.items():
            relative = Path(str(artifact["source_path"])).resolve().relative_to(source_root)
            relocated = dict(artifact)
            relocated["source_path"] = str(destination_root / relative)
            store.set("artifact", artifact_id, relocated)

    def _rollback_name_migration(
        self,
        *,
        store: StateStore,
        binding_key: str,
        old_binding: dict[str, Any],
        old_repository: Path,
        expected_repository: Path,
        old_branch: str,
        moved: bool,
        branch_renamed: bool,
        backup_graph: Path,
        old_graph_key: str,
        old_graph_metadata: dict[str, Any] | None,
        old_graph_operation: dict[str, Any] | None,
        artifact_snapshots: dict[str, dict[str, Any]],
    ) -> Result:
        errors: list[str] = []
        if moved:
            graph_path = expected_repository / ".codegraph"
            if graph_path.exists():
                try:
                    shutil.rmtree(graph_path)
                except OSError as error:
                    errors.append(f"codegraph-new:{error}")
            if backup_graph.exists():
                try:
                    backup_graph.rename(graph_path)
                except OSError as error:
                    errors.append(f"codegraph-backup:{error}")
            if branch_renamed:
                restored_branch = self._git(
                    ["branch", "-m", old_branch],
                    cwd=expected_repository,
                    failure_code="WORKTREE_MIGRATION_BRANCH_ROLLBACK_FAILED",
                )
                if not restored_branch.ok:
                    errors.append(restored_branch.code)
            restored_path = self._git(
                ["worktree", "move", str(expected_repository), str(old_repository)],
                cwd=(self.root / WorkspaceService(self.root).project(
                    str(old_binding["repository_id"])
                ).path).resolve(),
                failure_code="WORKTREE_MIGRATION_PATH_ROLLBACK_FAILED",
            )
            if not restored_path.ok:
                errors.append(restored_path.code)
        restored_to_old_path = old_repository.is_dir() and not expected_repository.exists()
        new_graph = CodeGraphService(
            self.root,
            str(old_binding["repository_id"]),
            repo=expected_repository,
            codegraph_version="unknown",
        )
        store.delete("codegraph", new_graph.key)
        store.delete("codegraph_operation", new_graph.key)
        if restored_to_old_path:
            if old_graph_metadata is not None:
                store.set("codegraph", old_graph_key, old_graph_metadata)
            if old_graph_operation is not None:
                store.set("codegraph_operation", old_graph_key, old_graph_operation)
            for artifact_id, artifact in artifact_snapshots.items():
                store.set("artifact", artifact_id, artifact)
            refreshed = ArtifactService(self.root).refresh_index(
                str(old_binding["requirement_id"])
            )
            if not refreshed.ok:
                errors.append(refreshed.code)
            restored_binding = dict(old_binding)
            if errors:
                restored_binding.update(
                    status="blocked",
                    migration_rollback_incomplete=True,
                )
            store.set("worktree", binding_key, restored_binding)
        else:
            incomplete = dict(old_binding)
            actual_branch = old_branch
            if expected_repository.is_dir():
                branch = self._git(
                    ["branch", "--show-current"],
                    cwd=expected_repository,
                    failure_code="WORKTREE_MIGRATION_BRANCH_READ_FAILED",
                )
                if branch.ok:
                    actual_branch = str(branch.data["stdout"])
            incomplete.update(
                status="blocked",
                migration_rollback_incomplete=True,
                repository_path=str(expected_repository),
                path=str(expected_repository.parent),
                branch=actual_branch,
            )
            store.set("worktree", binding_key, incomplete)
            errors.append("WORKTREE_MIGRATION_PATH_NOT_RESTORED")
        return Result(
            not errors,
            "WORKTREE_NAME_MIGRATION_ROLLED_BACK" if not errors else "WORKTREE_NAME_MIGRATION_ROLLBACK_INCOMPLETE",
            data={"errors": errors},
        )

    def remove(self, branch: str) -> Result:
        store = StateStore(self.root)
        resolved = resolve_worktree_binding(store, branch)
        binding = resolved[1] if resolved else None
        cwd = self.root
        if binding:
            project = WorkspaceService(self.root).project(binding["repository_id"])
            cwd = (self.root / project.path).resolve()
        result = self._execute(
            ["remove", str(binding.get("branch", branch)) if binding else branch],
            cwd=cwd,
        )
        if result.ok and binding:
            store.delete("worktree", resolved[0])
            workspace_path = Path(str(binding["path"]))
            with suppress(OSError):
                workspace_path.rmdir()
            branch_name = str(binding.get("branch", branch))
            remaining = self._git(
                ["branch", "--list", branch_name],
                cwd=cwd,
                failure_code="WORKTREE_BRANCH_VERIFY_FAILED",
            )
            if not remaining.ok:
                audit_id = store.audit(
                    "worktree.remove_incomplete",
                    remaining.code,
                    {**binding, "worktrunk": result.data, "git": remaining.data},
                )
                return Result(
                    False,
                    remaining.code,
                    data={**remaining.data, "audit_id": audit_id},
                )
            if remaining.data["stdout"]:
                details = {
                    **binding,
                    "branch": branch_name,
                    "branch_deleted": False,
                    "worktrunk": result.data,
                }
                details["audit_id"] = store.audit(
                    "worktree.remove_incomplete",
                    "WORKTREE_BRANCH_DELETE_MISMATCH",
                    details,
                )
                return Result(False, "WORKTREE_BRANCH_DELETE_MISMATCH", data=details)
            store.audit("worktree.removed", "OK", binding)
        return result

    def merge(self, target: str, *, branch: str | None = None) -> Result:
        store = StateStore(self.root)
        resolved = resolve_worktree_binding(store, branch) if branch else None
        binding = resolved[1] if resolved else None
        cwd = Path(binding.get("repository_path", binding["path"])) if binding else self.root
        result = self._execute(["merge", target], cwd=cwd)
        if result.ok and binding:
            current = store.get("worktree", resolved[0])
            if current:
                current["status"] = "merged"
                store.set("worktree", resolved[0], current)
            store.audit("worktree.merged", "OK", {**binding, "target": target})
        return result

    def install_hooks(self, project_id: str) -> Result:
        project = WorkspaceService(self.root).project(project_id)
        repo = (self.root / project.path).resolve()
        config = repo / ".config" / "wt.toml"
        existing = config.read_text(encoding="utf-8") if config.exists() else ""
        keys = "pre-start|post-start|pre-commit|pre-merge|post-merge|post-remove"
        if re.search(rf"(?m)^\s*(?:(?:{keys})\s*=|\[\[?(?:{keys})\]{{1,2}})", existing):
            return Result(False, "WORKTRUNK_HOOK_CONFLICT", data={"path": str(config)})
        root = shlex.quote(str(self.root.resolve()))

        def command(event: str) -> str:
            return f"praxis --root {root} lifecycle {event} --stdin-json"

        hooks = {
            "pre-start": command("worktree-pre-start"),
            "post-start": command("worktree-post-start"),
            "pre-commit": command("pre-commit"),
            "pre-merge": command("pre-merge"),
            "post-merge": command("post-merge"),
            "post-remove": command("post-remove"),
        }
        block = "\n# Praxis V3 managed CodeGraph lifecycle\n" + "\n".join(
            f"{key} = {json.dumps(value)}" for key, value in hooks.items()
        )
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(existing.rstrip() + block + "\n", encoding="utf-8")
        return Result(True, data={"path": str(config), "hooks": list(hooks)})
