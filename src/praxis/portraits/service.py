from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from hashlib import blake2b
from pathlib import Path
from typing import Any, Protocol

from praxis.codegraph.service import CodeGraphService, GitSnapshot
from praxis.documents.atomic_writer import atomic_write_text
from praxis.integrations.witr import WitrService, redact_runtime_data
from praxis.result import Result
from praxis.storage.sqlite import StateStore
from praxis.workspace.service import Project, WorkspaceService


class RuntimeInspector(Protocol):
    def diagnose(self, arguments: list[str], *, explicit: bool) -> Result: ...


class PortraitService:
    def __init__(self, root: Path | str, *, witr: RuntimeInspector | None = None):
        self.root = Path(root)
        self.store = StateStore(self.root)
        self.witr = witr or WitrService(self.root)

    def scan(self, project_id: str, runtime_arguments: list[str] | None = None) -> Result:
        workspace = WorkspaceService(self.root)
        project = workspace.project(project_id)
        repo = (self.root / project.path).resolve()
        files = self._tracked_files(repo)
        input_hash = self._input_hash(project, repo, files)
        cached = self.store.get("portrait", project_id)
        if cached and cached["input_hash"] == input_hash and runtime_arguments is None:
            return Result(True, "PORTRAIT_UNCHANGED", data=cached)

        runtime: dict[str, Any] | None = None
        if runtime_arguments is not None:
            runtime_result = self.witr.diagnose(runtime_arguments, explicit=True)
            if not runtime_result.ok:
                return runtime_result
            runtime = redact_runtime_data(runtime_result.data)

        technology_stack, evidence = self._technology(files, repo)
        build_commands, test_commands = self._commands(project, files)
        branches = self._branches(repo)
        deployment_commands = list(project.deployment_commands)
        if "Dockerfile" in files:
            deployment_commands.append("docker build .")
        try:
            graph = CodeGraphService(self.root, project_id).status().data
        except RuntimeError:
            graph = {"fresh": False, "current_head": None}
        data: dict[str, Any] = {
            "project_id": project_id,
            "system_id": project.system_id,
            "kind": project.kind,
            "scan_mode": "incremental",
            "input_hash": input_hash,
            "scanned_at": datetime.now(UTC).isoformat(),
            "technology_stack": technology_stack,
            "build_commands": build_commands,
            "lint_commands": list(project.lint_commands),
            "typecheck_commands": list(project.typecheck_commands),
            "test_commands": test_commands,
            "deployment_commands": list(dict.fromkeys(deployment_commands)),
            "database_connections": list(project.database_connections),
            "release_branches": sorted(
                {
                    *project.release_branches,
                    *(name for name in branches if name.startswith("release/")),
                }
            ),
            "template_branches": sorted(
                {
                    *project.template_branches,
                    *(name for name in branches if name.startswith("template/")),
                }
            ),
            "ci_files": sorted(
                name
                for name in files
                if name.startswith(".github/workflows/")
                or name in {".gitlab-ci.yml", "Jenkinsfile"}
            ),
            "codegraph": {"fresh": graph["fresh"], "current_head": graph["current_head"]},
            "runtime_scanned": runtime is not None,
            "runtime": runtime,
            "evidence": evidence,
        }
        previous = cached
        if previous:
            self.store.set("portrait_previous", project_id, previous)
        self.store.set("portrait", project_id, data)
        self._write(project, data)
        return Result(True, data=data)

    def show(self, project_id: str) -> Result:
        data = self.store.get("portrait", project_id)
        return Result(bool(data), "OK" if data else "PORTRAIT_NOT_FOUND", data=data or {})

    def path(self, project_id: str) -> Path:
        workspace = WorkspaceService(self.root)
        project = workspace.project(project_id)
        return (
            self.root
            / workspace.load()["knowledge_root"]
            / "系统画像"
            / project.system_id
            / f"{project.id}.md"
        )

    def diff(self, project_id: str) -> Result:
        current = self.store.get("portrait", project_id)
        previous = self.store.get("portrait_previous", project_id)
        if not current:
            return Result(False, "PORTRAIT_NOT_FOUND")
        keys = sorted(set(current) | set(previous or {}))
        changes = {
            key: {"before": (previous or {}).get(key), "after": current.get(key)}
            for key in keys
            if (previous or {}).get(key) != current.get(key)
            and key not in {"scanned_at", "input_hash"}
        }
        return Result(True, data={"project_id": project_id, "changes": changes})

    def verify(self, project_id: str) -> Result:
        portrait = self.store.get("portrait", project_id)
        if not portrait:
            return Result(False, "PORTRAIT_NOT_FOUND")
        invalid_connections = [
            reference
            for reference in portrait.get("database_connections", [])
            if not reference.startswith("dbx://")
        ]
        invalid_confidence = [
            item
            for item in portrait.get("evidence", [])
            if item.get("置信度") not in {"工具检测", "已验证", "人工确认"}
        ]
        ok = not invalid_connections and not invalid_confidence
        return Result(
            ok,
            "OK" if ok else "PORTRAIT_INVALID",
            data={
                "project_id": project_id,
                "invalid_connections": invalid_connections,
                "invalid_evidence": invalid_confidence,
            },
        )

    @staticmethod
    def _input_hash(project: Project, repo: Path, files: set[str]) -> str:
        try:
            snapshot = GitSnapshot.capture(repo)
            source = {"head": snapshot.head, "dirty": snapshot.dirty_fingerprint}
        except RuntimeError:
            source = {
                "files": {
                    name: blake2b((repo / name).read_bytes(), digest_size=20).hexdigest()
                    for name in sorted(files)
                    if (repo / name).is_file()
                }
            }
        facts = {
            "source": source,
            "project": {
                key: list(value) if isinstance(value, tuple) else value
                for key, value in project.__dict__.items()
            },
        }
        return blake2b(
            json.dumps(facts, ensure_ascii=False, sort_keys=True).encode(), digest_size=20
        ).hexdigest()

    @staticmethod
    def _tracked_files(repo: Path) -> set[str]:
        process = subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=repo,
            check=False,
            capture_output=True,
        )
        if process.returncode == 0:
            return {
                name.decode(errors="surrogateescape")
                for name in process.stdout.split(b"\0")
                if name
            }
        markers = {
            "pyproject.toml",
            "pom.xml",
            "build.gradle",
            "build.gradle.kts",
            "package.json",
            "Dockerfile",
            "docker-compose.yml",
            "compose.yaml",
            "manifest.json",
            ".gitlab-ci.yml",
            "Jenkinsfile",
        }
        return {name for name in markers if (repo / name).is_file()}

    @staticmethod
    def _technology(files: set[str], repo: Path) -> tuple[list[str], list[dict[str, str]]]:
        detected: list[tuple[str, str]] = []
        for marker, technologies in (
            ("pyproject.toml", ("Python",)),
            ("pom.xml", ("Java", "Maven")),
            ("build.gradle", ("Java", "Gradle")),
            ("build.gradle.kts", ("Java", "Gradle")),
            ("package.json", ("Node.js",)),
            ("Dockerfile", ("Docker",)),
            ("docker-compose.yml", ("Docker Compose",)),
            ("compose.yaml", ("Docker Compose",)),
            ("manifest.json", ("UniApp",)),
        ):
            if marker in files:
                detected.extend((technology, marker) for technology in technologies)
        package = repo / "package.json"
        if package.is_file():
            content = package.read_text(encoding="utf-8", errors="ignore")
            if '"vue"' in content:
                detected.append(("Vue", "package.json"))
        unique = dict(detected)
        return list(unique), [
            {
                "结论": technology,
                "来源": source,
                "扫描器": "StaticProjectScanner",
                "置信度": "工具检测",
            }
            for technology, source in unique.items()
        ]

    @staticmethod
    def _commands(project: Project, files: set[str]) -> tuple[list[str], list[str]]:
        build: list[str] = []
        tests = list(project.test_commands)
        if "pom.xml" in files:
            build.append("mvn package")
            tests = tests or ["mvn test"]
        if "pyproject.toml" in files:
            build.append("uv build")
            tests = tests or ["uv run pytest"]
        if "package.json" in files:
            build.append("npm run build")
            tests = tests or ["npm test"]
        return build, tests

    @staticmethod
    def _branches(repo: Path) -> list[str]:
        process = subprocess.run(
            ["git", "branch", "--format=%(refname:short)"],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
        )
        return sorted(line for line in process.stdout.splitlines() if line)

    def _write(self, project: Project, data: dict[str, Any]) -> None:
        path = self.path(project.id)
        lines = [
            "---",
            "类型: 系统画像",
            f"系统编号: {project.system_id}",
            f"仓库编号: {project.id}",
            f"扫描时间: {data['scanned_at']}",
            f"内容哈希: {data['input_hash']}",
            "---",
            "",
            f"# {project.name or project.id}仓库画像",
            "",
            "## 技术栈",
            "",
            *(f"- {item}" for item in data["technology_stack"]),
            "",
            "## 构建与测试",
            "",
            *(f"- 构建：`{item}`" for item in data["build_commands"]),
            *(f"- 测试：`{item}`" for item in data["test_commands"]),
            "",
            "## 数据库连接引用",
            "",
            *(f"- `{item}`" for item in data["database_connections"]),
            "",
            "## 分支与交付",
            "",
            *(f"- 发布分支：`{item}`" for item in data["release_branches"]),
            *(f"- 模板分支：`{item}`" for item in data["template_branches"]),
            *(
                f"- 部署命令来源：`{item}`（扫描时未执行）"
                for item in data["deployment_commands"]
            ),
            "",
            "## 运行态",
            "",
            f"- 已显式扫描：{'是' if data['runtime_scanned'] else '否'}",
            "",
            "## 证据",
            "",
            *(
                f"- {item['结论']}：{item['置信度']}，来源 `{item['来源']}`"
                for item in data["evidence"]
            ),
            "",
        ]
        atomic_write_text(path, "\n".join(lines))
