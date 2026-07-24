from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
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
_PNPM_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?$")


def _utf8_environment(overrides: dict[str, str] | None = None) -> dict[str, str]:
    environment = {**os.environ, **(overrides or {})}
    safe: dict[str, str] = {}
    for key, value in environment.items():
        try:
            key.encode("utf-8")
            value.encode("utf-8")
        except UnicodeEncodeError:
            continue
        safe[key] = value
    return safe


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
        resolved = resolve_worktree_binding(
            StateStore(self.root),
            "",
            repository_id=project_id,
            worktree_path=repository_path,
        )
        return CodeGraphService(
            self.root,
            project_id,
            repo=repository_path,
        ).enqueue(binding_id=resolved[0] if resolved else "")

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
        repository_path = Path(str(binding["repository_path"]))
        excluded = self._exclude_generated_paths(repository_path)
        binding["generated_paths_exclude_status"] = excluded.code
        if not excluded.ok:
            store.audit("worktree.generated_paths_exclude_failed", excluded.code, binding)
        package_manager = self._setup_package_manager_spec(
            project.worktree_setup_commands, repository_path
        )
        setup_fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "commands": project.worktree_setup_commands,
                    "package_manager": package_manager,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        setup_ready_for_graph = True
        if not project.worktree_setup_commands:
            binding["worktree_setup_status"] = "WORKTREE_SETUP_NOT_CONFIGURED"
            binding["worktree_setup_commands_configured"] = 0
            for key in (
                "worktree_setup_commands_completed",
                "worktree_setup_fingerprint",
                "worktree_setup_started_at",
                "worktree_setup_completed_at",
                "worktree_setup_last_action",
                "worktree_setup_package_managers",
            ):
                binding.pop(key, None)
        else:
            preflight = self._preflight_worktree_setup(project, repository_path)
            setup_ready_for_graph = preflight.ok
            binding.update(
                worktree_setup_status=(
                    "WORKTREE_SETUP_DEFERRED" if preflight.ok else preflight.code
                ),
                worktree_setup_preflight_status=preflight.code,
                worktree_setup_commands_configured=len(
                    project.worktree_setup_commands
                ),
                worktree_setup_fingerprint=setup_fingerprint,
                worktree_setup_package_managers=preflight.data.get(
                    "package_managers", []
                ),
            )
            store.audit("worktree.setup_deferred", preflight.code, binding)
        binding.pop("codegraph_completed_at", None)
        binding.update(
            status="active",
            codegraph_status=(
                "CODEGRAPH_QUEUED"
                if setup_ready_for_graph
                else "CODEGRAPH_DEFERRED_SETUP_PREFLIGHT_FAILED"
            ),
        )
        store.set("worktree", binding_key, binding)
        if not setup_ready_for_graph:
            return Result(
                True,
                success_code,
                data=binding,
                diagnostics=(
                    {
                        "code": "WORKTREE_SETUP_PREFLIGHT_FAILED",
                        "message": (
                            "Worktree is active; fix setup preflight before prepare or CodeGraph."
                        ),
                    },
                ),
            )
        graph = self.initialize_graph(str(binding["repository_id"]), repository_path)
        binding = store.get("worktree", binding_key) or binding
        if not binding.get("codegraph_completed_at"):
            binding["codegraph_status"] = graph.code
            binding["codegraph_job_id"] = graph.data.get("job_id")
        store.set("worktree", binding_key, binding)
        return Result(
            True,
            success_code,
            data=binding,
            diagnostics=graph.diagnostics,
        )

    def _preflight_worktree_setup(self, project: Project, repository_path: Path) -> Result:
        package_managers: list[dict[str, str]] = []
        for index, configured in enumerate(project.worktree_setup_commands, start=1):
            command = shlex.split(configured)
            if command[0] == "pnpm":
                resolved = self._resolve_pnpm(repository_path)
                if not resolved.ok:
                    return Result(
                        False,
                        resolved.code,
                        data={**resolved.data, "command_index": index},
                    )
                lockfile = repository_path / "pnpm-lock.yaml"
                if not lockfile.is_file():
                    return Result(
                        False,
                        "WORKTREE_SETUP_LOCKFILE_MISSING",
                        data={"command_index": index, "path": str(lockfile)},
                    )
                try:
                    lockfile_header = lockfile.read_text(encoding="utf-8")[:65_536]
                except (OSError, UnicodeDecodeError) as error:
                    return Result(
                        False,
                        "WORKTREE_SETUP_LOCKFILE_INVALID",
                        data={
                            "command_index": index,
                            "path": str(lockfile),
                            "error_type": type(error).__name__,
                        },
                    )
                if "lockfileVersion:" not in lockfile_header or any(
                    marker in lockfile_header for marker in ("<<<<<<<", "=======", ">>>>>>>")
                ):
                    return Result(
                        False,
                        "WORKTREE_SETUP_LOCKFILE_INVALID",
                        data={"command_index": index, "path": str(lockfile)},
                    )
                package_managers.append(
                    {
                        "name": "pnpm",
                        "version": str(resolved.data["version"]),
                        "source": str(resolved.data["source"]),
                    }
                )
            elif shutil.which(command[0]) is None:
                return Result(
                    False,
                    "WORKTREE_SETUP_COMMAND_NOT_FOUND",
                    data={"command_index": index, "executable": command[0]},
                )
        return Result(
            True,
            "WORKTREE_SETUP_PREFLIGHT_OK",
            data={"package_managers": package_managers},
        )

    def _exclude_generated_paths(self, repository_path: Path) -> Result:
        common = self._git(
            ["rev-parse", "--git-common-dir"],
            cwd=repository_path,
            failure_code="WORKTREE_GIT_COMMON_DIR_FAILED",
        )
        if not common.ok:
            return common
        common_path = Path(str(common.data["stdout"]))
        if not common_path.is_absolute():
            common_path = repository_path / common_path
        exclude_path = common_path.resolve() / "info" / "exclude"
        try:
            exclude_path.parent.mkdir(parents=True, exist_ok=True)
            current = exclude_path.read_text(encoding="utf-8") if exclude_path.is_file() else ""
            entries = {line.strip() for line in current.splitlines()}
            missing = [item for item in (".codegraph/", ".praxis/") if item not in entries]
            if missing:
                with exclude_path.open("a", encoding="utf-8") as stream:
                    if current and not current.endswith("\n"):
                        stream.write("\n")
                    stream.write("\n".join(missing) + "\n")
        except OSError as error:
            return Result(
                False,
                "WORKTREE_GENERATED_PATH_EXCLUDE_FAILED",
                data={"error_type": type(error).__name__},
            )
        return Result(
            True,
            "WORKTREE_GENERATED_PATHS_EXCLUDED",
            data={"path": str(exclude_path)},
        )

    def prepare_for_requirement(self, requirement_id: str, repository_id: str) -> Result:
        store = StateStore(self.root)
        binding_id = worktree_binding_id(requirement_id, repository_id)
        resolved = resolve_worktree_binding(store, binding_id)
        if not resolved:
            return Result(False, "WORKTREE_BINDING_NOT_FOUND", data={"binding_id": binding_id})
        binding_key, binding = resolved
        if binding.get("status") != "active":
            return Result(False, "WORKTREE_NOT_ACTIVE", data=binding)
        setup_status = str(binding.get("worktree_setup_status", ""))
        if setup_status == "WORKTREE_SETUP_COMPLETED":
            return Result(True, "WORKTREE_SETUP_ALREADY_PREPARED", data=binding)
        if setup_status not in {
            "WORKTREE_SETUP_DEFERRED",
            "WORKTREE_SETUP_NOT_CONFIGURED",
        }:
            from praxis.governance.service import ExecutionBudgetService

            retry = ExecutionBudgetService(self.root).consume(
                requirement_id,
                "in_progress",
                "retry",
                f"worktree-setup:{repository_id}",
            )
            if not retry.ok:
                return retry
        project = WorkspaceService(self.root).project(repository_id)
        repository_path = Path(str(binding["repository_path"]))
        preflight = self._preflight_worktree_setup(project, repository_path)
        if not preflight.ok:
            binding["worktree_setup_status"] = preflight.code
            store.set("worktree", binding_key, binding)
            return Result(False, "WORKTREE_SETUP_PREFLIGHT_FAILED", data=preflight.data)
        binding.update(
            worktree_setup_status="WORKTREE_SETUP_RUNNING",
            worktree_setup_started_at=datetime.now(UTC).isoformat(),
        )
        store.set("worktree", binding_key, binding)
        setup = self._run_worktree_setup_commands(project, repository_path)
        binding.update(
            worktree_setup_status=setup.code,
            worktree_setup_commands_completed=setup.data.get("completed", 0),
            worktree_setup_package_managers=setup.data.get("package_managers", []),
            worktree_setup_completed_at=datetime.now(UTC).isoformat(),
        )
        store.set("worktree", binding_key, binding)
        if setup.ok and binding.get("codegraph_status") == (
            "CODEGRAPH_DEFERRED_SETUP_PREFLIGHT_FAILED"
        ):
            graph = CodeGraphService(
                self.root,
                repository_id,
                repo=repository_path,
            ).enqueue(binding_id=binding_key)
            binding = store.get("worktree", binding_key) or binding
            if not binding.get("codegraph_completed_at"):
                binding["codegraph_status"] = graph.code
                binding["codegraph_job_id"] = graph.data.get("job_id")
        store.set("worktree", binding_key, binding)
        audit_id = store.audit(
            "worktree.setup_completed" if setup.ok else "worktree.setup_failed",
            setup.code,
            binding,
        )
        return Result(setup.ok, setup.code, data={**binding, "audit_id": audit_id})

    def _run_worktree_setup_commands(
        self, project: Project, repository_path: Path
    ) -> Result:
        if not project.worktree_setup_commands:
            return Result(True, "WORKTREE_SETUP_NOT_CONFIGURED", data={"completed": 0})
        completed = 0
        package_managers: list[dict[str, str]] = []
        for index, configured in enumerate(project.worktree_setup_commands, start=1):
            command = shlex.split(configured)
            executable = command[0]
            if executable == "pnpm":
                resolved = self._resolve_pnpm(repository_path)
                if not resolved.ok:
                    return Result(
                        False,
                        resolved.code,
                        data={
                            **resolved.data,
                            "command_index": index,
                            "executable": executable,
                            "completed": completed,
                            "package_managers": package_managers,
                        },
                    )
                command[0] = str(resolved.data["executable"])
                package_managers.append(
                    {
                        "name": "pnpm",
                        "version": str(resolved.data["version"]),
                        "source": str(resolved.data["source"]),
                    }
                )
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
                        "package_managers": package_managers,
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
                        "package_managers": package_managers,
                    },
                )
            completed += 1
        return Result(
            True,
            "WORKTREE_SETUP_COMPLETED",
            data={
                "completed": completed,
                "package_managers": package_managers,
            },
        )

    @staticmethod
    def _setup_package_manager_spec(
        commands: tuple[str, ...], repository_path: Path
    ) -> str | None:
        if not any(shlex.split(command)[0] == "pnpm" for command in commands):
            return None
        manifest = repository_path / "package.json"
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        value = payload.get("packageManager")
        return value if isinstance(value, str) else None

    def _resolve_pnpm(self, repository_path: Path) -> Result:
        manifest = repository_path / "package.json"
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return Result(False, "WORKTREE_PACKAGE_MANAGER_MANIFEST_MISSING")
        except (OSError, json.JSONDecodeError):
            return Result(False, "WORKTREE_PACKAGE_MANAGER_MANIFEST_INVALID")
        spec = payload.get("packageManager")
        if not isinstance(spec, str) or not spec:
            return Result(False, "WORKTREE_PACKAGE_MANAGER_VERSION_REQUIRED")
        if not spec.startswith("pnpm@"):
            return Result(
                False,
                "WORKTREE_PACKAGE_MANAGER_MISMATCH",
                data={"declared": spec, "configured": "pnpm"},
            )
        version = spec.removeprefix("pnpm@").split("+", 1)[0]
        if not _PNPM_VERSION.fullmatch(version):
            return Result(
                False,
                "WORKTREE_PACKAGE_MANAGER_VERSION_INVALID",
                data={"declared": spec, "configured": "pnpm"},
            )

        candidates: list[tuple[str, str]] = [("path", "pnpm")]
        for pnpm_home in self._pnpm_home_candidates():
            executable = pnpm_home / ".tools" / "pnpm" / version / "bin" / "pnpm"
            if executable.is_file():
                candidates.append(("pnpm_home", str(executable)))
        local_pattern = f".pnpm-store/v*/links/@/pnpm/{version}/*/bin/pnpm"
        candidates.extend(
            ("workspace_store", str(path))
            for path in sorted(self.root.glob(local_pattern))
            if path.is_file()
        )

        detected: list[str] = []
        probe_environment = {
            "COREPACK_ENABLE_NETWORK": "0",
            "pnpm_config_manage_package_manager_versions": "false",
            "pnpm_config_pm_on_fail": "ignore",
        }
        for source, executable in candidates:
            try:
                process = self.run(
                    [executable, "--version"],
                    self.root,
                    probe_environment,
                )
            except FileNotFoundError:
                continue
            actual = (process.stdout or "").strip()
            if process.returncode == 0 and actual == version:
                return Result(
                    True,
                    "WORKTREE_PACKAGE_MANAGER_RESOLVED",
                    data={
                        "executable": executable,
                        "name": "pnpm",
                        "version": version,
                        "source": source,
                    },
                )
            if actual and actual not in detected:
                detected.append(actual)
        return Result(
            False,
            "WORKTREE_PACKAGE_MANAGER_VERSION_UNAVAILABLE",
            data={
                "name": "pnpm",
                "required_version": version,
                "detected_versions": detected,
            },
        )

    @staticmethod
    def _pnpm_home_candidates() -> tuple[Path, ...]:
        candidates: list[Path] = []
        if configured := os.environ.get("PNPM_HOME"):
            path = Path(configured).expanduser()
            if path.is_absolute():
                candidates.append(path)
        home = Path.home()
        candidates.extend((home / "Library" / "pnpm", home / ".local/share/pnpm"))
        return tuple(dict.fromkeys(candidates))

    @staticmethod
    def _run(
        command: Sequence[str], cwd: Path, environment: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            cwd=cwd,
            env=_utf8_environment(environment),
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

    def resolve_template_revision(self, repository_id: str) -> Result:
        project = WorkspaceService(self.root).project(repository_id)
        if not project.template_branches:
            return Result(False, "WORKTREE_TEMPLATE_BRANCH_REQUIRED")
        if len(project.template_branches) != 1:
            return Result(
                False,
                "WORKTREE_TEMPLATE_BRANCH_AMBIGUOUS",
                data={"template_branches": list(project.template_branches)},
            )
        upstream = project.template_branches[0]
        repo = (self.root / project.path).resolve()
        fetched = self._git(
            ["fetch", "origin", upstream],
            cwd=repo,
            failure_code="WORKTREE_TEMPLATE_FETCH_FAILED",
        )
        if not fetched.ok:
            return fetched
        remote_branch = f"origin/{upstream}"
        revision = self._git(
            ["rev-parse", "--verify", f"{remote_branch}^{{commit}}"],
            cwd=repo,
            failure_code="WORKTREE_TEMPLATE_REVISION_FAILED",
        )
        if not revision.ok:
            return revision
        return Result(
            True,
            "WORKTREE_TEMPLATE_REVISION_RESOLVED",
            data={
                "repository_id": repository_id,
                "upstream_branch": remote_branch,
                "revision": revision.data["stdout"],
            },
        )

    def create_for_requirement(
        self,
        requirement_id: str,
        repository_id: str,
        stage: str | None = None,
        *,
        base_revision: str | None = None,
    ) -> Result:
        stage = stage or "development"
        if stage not in _STAGES:
            raise ValueError(f"未知任务阶段：{stage}")
        workspace = WorkspaceService(self.root)
        project = workspace.project(repository_id)
        requirement = StateStore(self.root).requirement(requirement_id)
        if not requirement:
            raise KeyError(requirement_id)
        if requirement["status"] not in {
            "ready",
            "in_progress",
            "implemented",
            "verifying",
        }:
            return Result(False, "REQUIREMENT_NOT_READY", data={"status": requirement["status"]})
        if project.system_id not in requirement["systems"]:
            return Result(False, "WORKTREE_SYSTEM_MISMATCH")
        store = StateStore(self.root)
        names = self._names_for_requirement(store, requirement, repository_id)
        repo = (self.root / project.path).resolve()
        display_names = self._validate_display_names(names, repository_id, repo)
        if not display_names.ok:
            return display_names
        resolved_base_revision = ""
        if base_revision:
            revision = self._git(
                ["rev-parse", "--verify", f"{base_revision}^{{commit}}"],
                cwd=repo,
                failure_code="WORKTREE_BASE_REVISION_INVALID",
            )
            if not revision.ok:
                return revision
            resolved_base_revision = str(revision.data["stdout"])
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
            if (
                resolved_base_revision
                and binding.get("base_revision") != resolved_base_revision
            ):
                return Result(
                    False,
                    "WORKTREE_BASE_REVISION_MISMATCH",
                    data={
                        "binding_id": existing[0],
                        "current": binding.get("base_revision", ""),
                        "expected": resolved_base_revision,
                    },
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
        if base_revision:
            synchronized = Result(
                True,
                data={
                    "local_branch": project.default_branch,
                    "upstream_branch": (
                        f"origin/{project.template_branches[0]}"
                        if len(project.template_branches) == 1
                        else ""
                    ),
                    "path": str(repo),
                    "revision": resolved_base_revision,
                },
            )
        else:
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
            [
                "switch",
                "--create",
                branch,
                "--base",
                synchronized.data["revision"] if base_revision else project.default_branch,
                "--no-cd",
            ],
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

    def preview_for_requirement(
        self,
        requirement_id: str,
        repository_ids: Sequence[str],
    ) -> Result:
        store = StateStore(self.root)
        requirement = store.requirement(requirement_id)
        if not requirement:
            return Result(False, "REQUIREMENT_NOT_FOUND")
        repositories = list(dict.fromkeys(repository_ids))
        if not repositories:
            return Result(False, "WORKTREE_REPOSITORY_REQUIRED")
        items: list[dict[str, Any]] = []
        for repository_id in repositories:
            project = WorkspaceService(self.root).project(repository_id)
            if project.system_id not in requirement["systems"]:
                return Result(
                    False,
                    "WORKTREE_SYSTEM_MISMATCH",
                    data={"repository_id": repository_id},
                )
            names = self._names_for_requirement(store, requirement, repository_id)
            item = asdict(names)
            item.update(
                repository_id=repository_id,
                workspace_path=str((self.root / ".worktrees" / names.workspace_name).resolve()),
                repository_path=str(
                    (
                        self.root
                        / ".worktrees"
                        / names.workspace_name
                        / names.worktree_display_name
                    ).resolve()
                ),
            )
            items.append(item)
        created_at = datetime.now(UTC)
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "requirement_id": requirement_id,
                    "repositories": repositories,
                    "items": items,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        preview_id = f"WTP-{created_at:%Y%m%dT%H%M%S}-{fingerprint[:8].upper()}"
        preview = {
            "preview_id": preview_id,
            "requirement_id": requirement_id,
            "repositories": repositories,
            "items": items,
            "fingerprint": fingerprint,
            "created_at": created_at.isoformat(),
            "expires_at": (created_at + timedelta(hours=24)).isoformat(),
        }
        store.set("worktree_preview", preview_id, preview)
        audit_id = store.audit("worktree.previewed", "OK", preview)
        return Result(True, "WORKTREE_PREVIEWED", data={**preview, "audit_id": audit_id})

    def ensure_for_requirement(
        self,
        requirement_id: str,
        repository_ids: Sequence[str],
        *,
        preview_id: str,
    ) -> Result:
        store = StateStore(self.root)
        preview = store.get("worktree_preview", preview_id)
        repositories = list(dict.fromkeys(repository_ids))
        if not preview:
            return Result(False, "WORKTREE_PREVIEW_NOT_FOUND")
        if (
            preview.get("requirement_id") != requirement_id
            or preview.get("repositories") != repositories
        ):
            return Result(False, "WORKTREE_PREVIEW_MISMATCH", data=preview)
        try:
            expired = datetime.fromisoformat(str(preview["expires_at"])) < datetime.now(UTC)
        except (KeyError, TypeError, ValueError):
            expired = True
        if expired:
            return Result(False, "WORKTREE_PREVIEW_EXPIRED", data=preview)
        requirement = store.requirement(requirement_id)
        if not requirement:
            return Result(False, "REQUIREMENT_NOT_FOUND")
        current_names = {
            repository_id: asdict(
                self._names_for_requirement(store, requirement, repository_id)
            )
            for repository_id in repositories
        }
        preview_names = {
            str(item["repository_id"]): {
                key: item[key]
                for key in (
                    "requirement_id",
                    "short_name_snapshot",
                    "display_slug",
                    "workspace_name",
                    "worktree_display_name",
                    "branch_name",
                )
            }
            for item in preview.get("items", [])
        }
        if current_names != preview_names:
            return Result(
                False,
                "WORKTREE_PREVIEW_STALE",
                data={"preview": preview_names, "current": current_names},
            )

        def create(repository_id: str) -> tuple[str, Result]:
            binding_id = worktree_binding_id(requirement_id, repository_id)
            existing = resolve_worktree_binding(store, binding_id)
            attempt_key = f"{requirement_id}:{repository_id}"
            attempt = store.get("worktree_ensure_attempt", attempt_key) or {
                "requirement_id": requirement_id,
                "repository_id": repository_id,
                "attempts": 0,
                "limit": 2,
            }
            if not (existing and existing[1].get("status") == "active"):
                if int(attempt["attempts"]) >= int(attempt["limit"]):
                    return repository_id, Result(
                        False,
                        "WORKTREE_RETRY_BUDGET_EXHAUSTED",
                        data=attempt,
                    )
                attempt["attempts"] = int(attempt["attempts"]) + 1
                attempt["updated_at"] = datetime.now(UTC).isoformat()
                store.set("worktree_ensure_attempt", attempt_key, attempt)
            try:
                result = self.create_for_requirement(
                    requirement_id, repository_id, "development"
                )
            except (KeyError, OSError, TypeError, ValueError) as error:
                result = Result(
                    False,
                    "WORKTREE_ENSURE_REPOSITORY_FAILED",
                    data={"message": str(error)},
                )
            return repository_id, result

        results: dict[str, Result] = {}
        with ThreadPoolExecutor(max_workers=min(4, len(repositories))) as executor:
            for repository_id, result in executor.map(create, repositories):
                results[repository_id] = result
        items = [
            {
                "repository_id": repository_id,
                **results[repository_id].to_dict(),
            }
            for repository_id in repositories
        ]
        ok = all(result.ok for result in results.values())
        code = "WORKTREE_ENSURED" if ok else "WORKTREE_ENSURE_PARTIAL"
        data = {
            "preview_id": preview_id,
            "requirement_id": requirement_id,
            "items": items,
        }
        data["audit_id"] = store.audit("worktree.ensured", code, data)
        return Result(ok, code, data=data)

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
                items.append(self._enrich_list_item(item, str(raw["id"])))
        return Result(True, data={"items": items})

    def status(self, *, binding_id: str = "", worktree_path: str = "") -> Result:
        if not binding_id and not worktree_path:
            return self.list()
        store = StateStore(self.root)
        resolved = resolve_worktree_binding(
            store,
            binding_id,
            worktree_path=worktree_path or None,
        )
        if not resolved:
            return Result(False, "WORKTREE_BINDING_INVALID")
        binding_key, binding = resolved
        project = WorkspaceService(self.root).project(str(binding["repository_id"]))
        result = self._execute(["list"], cwd=(self.root / project.path).resolve())
        if not result.ok:
            return result
        expected_path = Path(
            str(binding.get("repository_path") or binding.get("path", ""))
        ).resolve()
        listed = result.data.get("items", result.data.get("worktrees", []))
        matches = [
            self._enrich_list_item(item, project.id)
            for item in listed
            if str(item.get("branch") or item.get("name") or "")
            == str(binding.get("branch", ""))
            or (
                item.get("path")
                and Path(str(item["path"])).resolve() == expected_path
            )
        ]
        if not matches:
            return Result(
                False,
                "WORKTREE_NOT_FOUND",
                data={"binding_id": binding_key, "repository_id": project.id},
            )
        return Result(True, data={"items": matches, "binding_id": binding_key})

    def _enrich_list_item(self, item: dict[str, Any], repository_id: str) -> dict[str, Any]:
        enriched = {**item, "repository_id": repository_id}
        identifier = str(item.get("branch") or item.get("name") or "")
        resolved = resolve_worktree_binding(
            StateStore(self.root),
            identifier,
            repository_id=repository_id,
            worktree_path=item.get("path"),
        )
        if not resolved:
            return enriched
        raw_state = str(item.get("worktree", {}).get("state", ""))
        active = resolved[1].get("status") == "active"
        enriched.update(
            binding_id=resolved[0],
            workspace_path=resolved[1]["path"],
            binding_status=resolved[1]["status"],
            worktrunk_raw_state=raw_state,
            worktrunk_state="bound_active" if active else raw_state,
        )
        if active:
            enriched["worktree"] = {
                **item.get("worktree", {}),
                "state": "bound_active",
            }
            enriched["symbols"] = str(item.get("symbols", "")).replace("⚑", "")
            enriched["statusline"] = str(item.get("statusline", "")).replace("⚑", "")
        return enriched

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
        names = self._names_for_requirement(store, requirement, repository_id)
        repo = (self.root / project.path).resolve()
        display_names = self._validate_display_names(names, repository_id, repo)
        if not display_names.ok:
            return display_names
        expected_workspace = (self.root / ".worktrees" / names.workspace_name).resolve()
        expected_repository = (
            expected_workspace / names.worktree_display_name
        ).resolve()
        if binding.get("status") == "migrating":
            from praxis.governance.service import ExecutionBudgetService

            recovery = ExecutionBudgetService(self.root).consume(
                requirement_id,
                "in_progress",
                "recovery",
                f"worktree-name:{repository_id}",
            )
            if not recovery.ok:
                return recovery
            return self._recover_interrupted_name_migration(
                store=store,
                binding_key=binding_key,
                binding=binding,
                requirement_id=requirement_id,
                repository_id=repository_id,
                expected_repository=expected_repository,
                expected_branch=names.branch_name,
            )
        if binding.get("status") not in {"active", "blocked", "initializing"}:
            return Result(
                False,
                "WORKTREE_MIGRATION_STATUS_INVALID",
                data={"status": binding.get("status")},
            )
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
        binding.update(
            status="migrating",
            migration_started_at=datetime.now(UTC).isoformat(),
            migration_previous_status=old_status,
            migration_old_workspace_path=str(old_workspace),
            migration_old_repository_path=str(old_repository),
            migration_old_branch=old_branch,
            migration_target_repository_path=str(expected_repository),
            migration_target_branch=names.branch_name,
        )
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
                status="migrating",
            )
            store.set("worktree", binding_key, binding)
            self._relocate_artifacts(artifact_snapshots, old_repository, expected_repository)
            refreshed = ArtifactService(self.root).refresh_index(requirement_id)
            if not refreshed.ok:
                failure = refreshed
                raise RuntimeError(refreshed.code)
            cleanup_pending = False
            if backup_graph.exists():
                try:
                    shutil.rmtree(backup_graph)
                except OSError:
                    cleanup_pending = True
            binding.update(
                status="active",
                migration_previous_status=old_status,
                migration_completed_at=datetime.now(UTC).isoformat(),
                codegraph_status="CODEGRAPH_QUEUED",
                codegraph_backup_cleanup_pending=cleanup_pending,
            )
            binding.pop("codegraph_completed_at", None)
            store.set("worktree", binding_key, binding)
            graph = CodeGraphService(
                self.root,
                repository_id,
                repo=expected_repository,
            ).enqueue(binding_id=binding_key)
            binding = store.get("worktree", binding_key) or binding
            if not binding.get("codegraph_completed_at"):
                binding["codegraph_status"] = graph.code
                binding["codegraph_job_id"] = graph.data.get("job_id")
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
                diagnostics=failure.diagnostics if failure else (),
            )

    def _recover_interrupted_name_migration(
        self,
        *,
        store: StateStore,
        binding_key: str,
        binding: dict[str, Any],
        requirement_id: str,
        repository_id: str,
        expected_repository: Path,
        expected_branch: str,
    ) -> Result:
        required = (
            "migration_old_workspace_path",
            "migration_old_repository_path",
            "migration_old_branch",
            "migration_previous_status",
        )
        missing = [key for key in required if not binding.get(key)]
        if missing:
            return Result(
                False,
                "WORKTREE_NAME_MIGRATION_RECOVERY_DATA_MISSING",
                data={"binding_id": binding_key, "missing": missing},
            )
        old_workspace = Path(str(binding["migration_old_workspace_path"])).resolve()
        old_repository = Path(str(binding["migration_old_repository_path"])).resolve()
        old_branch = str(binding["migration_old_branch"])
        old_binding = dict(binding)
        old_binding.update(
            status=str(binding["migration_previous_status"]),
            path=str(old_workspace),
            repository_path=str(old_repository),
            branch=old_branch,
        )
        for key in tuple(old_binding):
            if key.startswith("migration_"):
                old_binding.pop(key)
        moved = expected_repository.is_dir() and not old_repository.exists()
        branch_renamed = False
        if moved:
            current = self._git(
                ["branch", "--show-current"],
                cwd=expected_repository,
                failure_code="WORKTREE_MIGRATION_BRANCH_READ_FAILED",
            )
            branch_renamed = bool(
                current.ok and str(current.data["stdout"]) == expected_branch
            )
        relocated_artifacts = self._artifact_snapshots(
            requirement_id,
            expected_repository,
        )
        artifact_snapshots: dict[str, dict[str, Any]] = {}
        for artifact_id, artifact in relocated_artifacts.items():
            restored = dict(artifact)
            relative = Path(str(artifact["source_path"])).resolve().relative_to(
                expected_repository
            )
            restored["source_path"] = str(old_repository / relative)
            artifact_snapshots[artifact_id] = restored
        old_graph = CodeGraphService(
            self.root,
            repository_id,
            repo=old_repository,
            codegraph_version="unknown",
        )
        rollback = self._rollback_name_migration(
            store=store,
            binding_key=binding_key,
            old_binding=old_binding,
            old_repository=old_repository,
            expected_repository=expected_repository,
            old_branch=old_branch,
            moved=moved,
            branch_renamed=branch_renamed,
            backup_graph=expected_repository / ".codegraph.praxis-name-migration",
            old_graph_key=old_graph.key,
            old_graph_metadata=store.get("codegraph", old_graph.key),
            old_graph_operation=store.get("codegraph_operation", old_graph.key),
            artifact_snapshots=artifact_snapshots,
        )
        if not rollback.ok:
            audit_id = store.audit(
                "worktree.name_migration_recovery_failed",
                rollback.code,
                {"binding_id": binding_key, "rollback": rollback.data},
            )
            return Result(
                False,
                "WORKTREE_NAME_MIGRATION_RECOVERY_FAILED",
                data={"rollback": rollback.data, "audit_id": audit_id},
            )
        recovered = store.get("worktree", binding_key) or old_binding
        recovered.update(
            status="active",
            migration_previous_status=str(binding["migration_previous_status"]),
            codegraph_status="CODEGRAPH_QUEUED",
            migration_recovered_at=datetime.now(UTC).isoformat(),
        )
        recovered.pop("codegraph_completed_at", None)
        store.set("worktree", binding_key, recovered)
        graph = CodeGraphService(
            self.root,
            repository_id,
            repo=old_repository,
        ).enqueue(binding_id=binding_key)
        recovered = store.get("worktree", binding_key) or recovered
        if not recovered.get("codegraph_completed_at"):
            recovered["codegraph_status"] = graph.code
            recovered["codegraph_job_id"] = graph.data.get("job_id")
        store.set("worktree", binding_key, recovered)
        audit_id = store.audit("worktree.name_migration_recovered", "OK", recovered)
        return Result(
            True,
            "WORKTREE_NAME_MIGRATION_RECOVERED",
            data={**recovered, "audit_id": audit_id},
            diagnostics=graph.diagnostics,
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
            (
                "WORKTREE_NAME_MIGRATION_ROLLED_BACK"
                if not errors
                else "WORKTREE_NAME_MIGRATION_ROLLBACK_INCOMPLETE"
            ),
            data={"errors": errors},
        )

    def remove(self, branch: str) -> Result:
        store = StateStore(self.root)
        resolved = resolve_worktree_binding(store, branch)
        binding = resolved[1] if resolved else None
        cwd = self.root
        graph_cleanup = Result(True, "CODEGRAPH_BACKGROUND_NOT_ACTIVE")
        if binding:
            project = WorkspaceService(self.root).project(binding["repository_id"])
            cwd = (self.root / project.path).resolve()
            graph_cleanup = CodeGraphService(
                self.root,
                project.id,
                repo=binding.get("repository_path", binding["path"]),
                codegraph_version="unknown",
            ).cancel()
            if not graph_cleanup.ok:
                return graph_cleanup
        result = self._execute(
            ["remove", str(binding.get("branch", branch)) if binding else branch],
            cwd=cwd,
        )
        if result.ok and resolved is not None:
            binding = resolved[1]
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
                deleted = self._git(
                    ["branch", "-D", branch_name],
                    cwd=cwd,
                    failure_code="WORKTREE_BRANCH_DELETE_FAILED",
                )
                if not deleted.ok:
                    binding.update(status="remove_cleanup_failed")
                    store.set("worktree", resolved[0], binding)
                    details = {
                        **binding,
                        "branch": branch_name,
                        "branch_deleted": False,
                        "worktrunk": result.data,
                        "git": deleted.data,
                    }
                    details["audit_id"] = store.audit(
                        "worktree.remove_incomplete",
                        deleted.code,
                        details,
                    )
                    return Result(False, deleted.code, data=details)
            store.delete("worktree", resolved[0])
            store.audit(
                "worktree.removed",
                "OK",
                {**binding, "codegraph_cleanup": graph_cleanup.to_dict()},
            )
        return result

    def merge(self, target: str, *, branch: str | None = None) -> Result:
        store = StateStore(self.root)
        resolved = resolve_worktree_binding(store, branch) if branch else None
        binding = resolved[1] if resolved else None
        cwd = Path(binding.get("repository_path", binding["path"])) if binding else self.root
        arguments = ["merge", target]
        if binding:
            # Worktrunk 0.68.0 can panic while its merge command backgrounds cleanup
            # for a Unicode worktree name. Its explicit remove command is Unicode-safe.
            arguments.append("--no-remove")
        result = self._execute(arguments, cwd=cwd)
        if result.ok and resolved is not None:
            binding = resolved[1]
            project = WorkspaceService(self.root).project(binding["repository_id"])
            cleanup = self._execute(
                ["remove", str(binding["branch"])],
                cwd=(self.root / project.path).resolve(),
            )
            if not cleanup.ok:
                binding.update(
                    status="merged_cleanup_failed",
                    merge_target=target,
                    cleanup_result=cleanup.data,
                )
                store.set("worktree", resolved[0], binding)
                audit_id = store.audit(
                    "worktree.merge_cleanup_failed",
                    "WORKTREE_MERGED_CLEANUP_FAILED",
                    binding,
                )
                return Result(
                    False,
                    "WORKTREE_MERGED_CLEANUP_FAILED",
                    data={**binding, "audit_id": audit_id},
                    diagnostics=cleanup.diagnostics,
                )
            current = store.get("worktree", resolved[0])
            if current:
                current["status"] = "merged"
                current["merge_target"] = target
                current["cleanup_result"] = cleanup.data
                store.set("worktree", resolved[0], current)
            store.audit("worktree.merged", "OK", {**binding, "target": target})
            workspace_path = Path(str(binding["path"]))
            with suppress(OSError):
                workspace_path.rmdir()
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
