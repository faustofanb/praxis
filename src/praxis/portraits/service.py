from __future__ import annotations

import json
import re
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
        build_commands, test_commands, lint_commands, typecheck_commands = (
            self._commands(project, repo, files)
        )
        branches = self._branches(repo)
        entrypoints = self._entrypoints(files)
        interface_surfaces = self._interface_surfaces(files)
        data_and_config_assets = self._data_and_config_assets(files)
        module_structure = self._module_structure(project, repo, files)
        rule_summary = self._rule_summary(repo)
        subrepo_skills = self._discover_subrepo_skills(project.id, repo)
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
            "repository": {
                "path": project.path,
                "file_count": len(files),
                "top_level_paths": sorted(
                    {name.split("/", 1)[0] for name in files}
                ),
            },
            "entrypoints": entrypoints,
            "interface_surfaces": interface_surfaces,
            "data_and_config_assets": data_and_config_assets,
            "module_structure": module_structure,
            "rule_summary": rule_summary,
            "subrepo_skills": subrepo_skills,
            "build_commands": build_commands,
            "lint_commands": list(dict.fromkeys([*project.lint_commands, *lint_commands])),
            "typecheck_commands": list(dict.fromkeys([*project.typecheck_commands, *typecheck_commands])),
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
    def _commands(
        project: Project, repo: Path, files: set[str]
    ) -> tuple[list[str], list[str]]:
        build: list[str] = []
        tests = list(project.test_commands)
        lint = list(project.lint_commands)
        typecheck = list(project.typecheck_commands)
        if "pom.xml" in files:
            build.append("mvn package")
            tests = tests or ["mvn test"]
        if "pyproject.toml" in files:
            build.append("uv build")
            tests = tests or ["uv run pytest"]
        if "package.json" in files:
            package_path = repo / "package.json"
            if package_path.is_file():
                try:
                    package = json.loads(
                        package_path.read_text(encoding="utf-8", errors="ignore")
                    )
                    manager = str(package.get("packageManager", "")).split("@")[0]
                    prefix = "pnpm" if manager == "pnpm" else "npm"
                    scripts = package.get("scripts", {})
                    build.extend(PortraitService._semantic_scripts(prefix, scripts, "build"))
                    if not tests:
                        tests = PortraitService._semantic_scripts(prefix, scripts, "test")
                    if not lint:
                        lint = PortraitService._semantic_scripts(prefix, scripts, "lint")
                    if not typecheck:
                        typecheck = PortraitService._semantic_scripts(prefix, scripts, "type")
                except json.JSONDecodeError:
                    build.append("npm run build")
                    tests = tests or ["npm test"]
            else:
                build.append("npm run build")
                tests = tests or ["npm test"]
        # CLAUDE.md/AGENTS.md 常用命令段补充
        rule_commands = PortraitService._rule_commands(repo)
        for command in rule_commands:
            if command not in build:
                build.append(command)
            if command not in tests:
                tests.append(command)
        return (
            list(dict.fromkeys(build)),
            list(dict.fromkeys(tests)),
            list(dict.fromkeys(lint)),
            list(dict.fromkeys(typecheck)),
        )

    @staticmethod
    def _semantic_scripts(prefix: str, scripts: dict[str, Any], kind: str) -> list[str]:
        exact = {"build": "build", "test": "test", "lint": "lint", "type": "check:type"}
        targets = [exact[kind]]
        if kind in {"build", "test", "lint"}:
            targets.append(f"{kind}:")
        matches = [
            name
            for name in sorted(scripts)
            if name == exact[kind] or name.startswith(f"{exact[kind]}:")
        ]
        return [f"{prefix} {name}" for name in matches][:3]

    @staticmethod
    def _rule_commands(repo: Path) -> list[str]:
        found: list[str] = []
        for rule_file in ("CLAUDE.md", "AGENTS.md"):
            path = repo / rule_file
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for block in re.findall(r"```(?:bash|sh)?\n(.*?)```", text, re.DOTALL):
                for line in block.splitlines():
                    stripped = line.strip()
                    if re.match(r"^(mvn|pnpm|npm|uv)\s", stripped):
                        found.append(stripped)
        return found[:5]

    @staticmethod
    def _module_structure(project: Project, repo: Path, files: set[str]) -> list[str]:
        modules: list[str] = []
        if "pom.xml" in files:
            pom = repo / "pom.xml"
            if pom.is_file():
                text = pom.read_text(encoding="utf-8", errors="ignore")
                modules = [
                    name.strip()
                    for name in re.findall(r"<module>(.*?)</module>", text)
                    if not name.strip().startswith("<!--")
                ]
        return modules

    @staticmethod
    def _rule_summary(repo: Path) -> str:
        for rule_file in ("CLAUDE.md", "AGENTS.md"):
            path = repo / rule_file
            if not path.is_file():
                continue
            lines = [
                line.strip()
                for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()
                if line.strip() and not line.startswith("```")
            ]
            return "\n".join(lines[:5])[:300]
        return ""

    def _discover_subrepo_skills(self, project_id: str, repo: Path) -> list[str]:
        """Discover SKILL.md files inside a sub-repository and register them into the
        workspace knowledge/skills/business catalog so the skill router can route to them."""
        from praxis.skills.importer import SkillImportService

        workspace = WorkspaceService(self.root).load()
        catalog = (
            self.root / workspace["knowledge_root"] / "skills" / "business"
        )
        discovered: list[str] = []
        for skills_root in ("skills", "docs/skills", ".cursor/skills"):
            root = repo / skills_root
            if not root.is_dir():
                continue
            for skill_md in sorted(root.glob("*/SKILL.md")):
                try:
                    content = skill_md.read_bytes()
                except OSError:
                    continue
                import hashlib

                skill_toml = skill_md.parent / "skill.toml"
                toml_id = ""
                if skill_toml.is_file():
                    try:
                        import tomllib

                        toml_id = tomllib.loads(
                            skill_toml.read_text(encoding="utf-8", errors="ignore")
                        ).get("id", "")
                    except (ValueError, OSError):
                        toml_id = ""
                skill_id = toml_id or f"business.{project_id}.{skill_md.parent.name}"
                target_dir = catalog / skill_id
                if target_dir.is_dir() and (target_dir / "SKILL.md").is_file():
                    existing = (target_dir / "SKILL.md").read_bytes()
                    if existing == content:
                        discovered.append(skill_id)
                        continue
                target_dir.mkdir(parents=True, exist_ok=True)
                (target_dir / "SKILL.md").write_bytes(content)
                if skill_toml.is_file():
                    (target_dir / "skill.toml").write_bytes(
                        skill_toml.read_bytes()
                    )
                else:
                    # 子仓库只带标准 SKILL.md（无 skill.toml）时，补最小注册清单，
                    # 否则 SkillRegistry 无法解析该技能。
                    (target_dir / "skill.toml").write_text(
                        f'id = "{skill_id}"\n'
                        'type = "business"\n'
                        'version = "1.0.0"\n'
                        'license = "Proprietary"\n'
                        f'source = "subrepo:{project_id}"\n'
                        'source_version = "1"\n'
                        'risk = "none"\n'
                        "context_budget = 500\n"
                        "required_tools = []\n"
                        "triggers = []\n"
                        "systems = []\n"
                        "projects = []\n"
                        "repository_roles = []\n",
                        encoding="utf-8",
                    )
                discovered.append(skill_id)
        return sorted(discovered)

    @staticmethod
    def _entrypoints(files: set[str]) -> list[str]:
        markers = {
            "pyproject.toml",
            "pom.xml",
            "build.gradle",
            "build.gradle.kts",
            "package.json",
            "manifest.json",
        }
        return sorted(
            name
            for name in files
            if name in markers
            or name.endswith(("/__main__.py", "/main.py", "/Application.java"))
        )

    @staticmethod
    def _interface_surfaces(files: set[str]) -> list[str]:
        terms = ("/cli/", "/mcp/", "/api/", "/controller/", "/routes/")
        return sorted(
            name
            for name in files
            if any(term in f"/{name.casefold()}" for term in terms)
        )[:50]

    @staticmethod
    def _data_and_config_assets(files: set[str]) -> list[str]:
        names = {
            "Dockerfile",
            "docker-compose.yml",
            "compose.yaml",
            "praxis.toml",
            "pyproject.toml",
            "package.json",
            "pom.xml",
        }
        return sorted(
            name
            for name in files
            if name in names
            or "/migrations/" in f"/{name.casefold()}"
            or name.endswith((".yaml", ".yml", ".toml"))
        )[:100]

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
            "## 仓库范围与结构",
            "",
            f"- 仓库类型：`{project.kind}`",
            f"- 配置路径：`{data['repository']['path']}`",
            f"- 已识别文件数：{data['repository']['file_count']}",
            *(
                f"- 顶层路径：`{item}`"
                for item in data["repository"]["top_level_paths"]
            ),
            "",
            "## 技术栈",
            "",
            *(f"- {item}" for item in data["technology_stack"]),
            "",
            "## 模块结构与关键目录",
            "",
            *(f"- 模块：`{item}`" for item in data["module_structure"]),
            "",
            "## 仓库规则摘要",
            "",
            *([data["rule_summary"]] if data["rule_summary"] else ["（无规则文件）"]),
            "",
            "## 子仓库技能",
            "",
            *(f"- `{item}`" for item in data["subrepo_skills"]),
            "",
            "## 工程入口与接口面",
            "",
            *(f"- 工程入口：`{item}`" for item in data["entrypoints"]),
            *(f"- 接口面：`{item}`" for item in data["interface_surfaces"]),
            "",
            "## 数据与配置资产",
            "",
            *(f"- `{item}`" for item in data["data_and_config_assets"]),
            "",
            "## 质量与交付命令",
            "",
            *(f"- 构建：`{item}`" for item in data["build_commands"]),
            *(f"- Lint：`{item}`" for item in data["lint_commands"]),
            *(f"- 类型检查：`{item}`" for item in data["typecheck_commands"]),
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
