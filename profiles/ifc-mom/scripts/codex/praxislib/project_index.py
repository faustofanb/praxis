from __future__ import annotations

import fnmatch
import json
import re
import time
import tomllib
from pathlib import Path
from typing import Any


PROJECTS_FILE = "praxis.projects.toml"
LEGACY_PROJECTS_FILE = ".praxis/projects.toml"
ROOT_CONFIG_FILE = "praxis.toml"
DEFAULT_SCAN_MAX_DEPTH = 3
DEFAULT_EXCLUDED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".praxis",
    ".codex",
    ".claude",
    ".cursor",
    ".github",
    ".opencode",
    ".vscode",
    ".worktree",
    ".worktrees",
    "__pycache__",
    "node_modules",
    "target",
    "dist",
    "build",
}


def _scan_options(root: Path) -> tuple[int, list[str], list[str]]:
    config = root / ROOT_CONFIG_FILE
    if not config.is_file():
        return DEFAULT_SCAN_MAX_DEPTH, [], []
    payload = tomllib.loads(config.read_text(encoding="utf-8"))
    section = payload.get("project_scan", {})
    if not isinstance(section, dict):
        return DEFAULT_SCAN_MAX_DEPTH, [], []
    raw_depth = section.get("maxDepth", section.get("max_depth", DEFAULT_SCAN_MAX_DEPTH))
    try:
        max_depth = max(1, int(raw_depth))
    except (TypeError, ValueError):
        max_depth = DEFAULT_SCAN_MAX_DEPTH
    include_globs = section.get("includeGlobs", section.get("include_globs", []))
    exclude_globs = section.get("excludeGlobs", section.get("exclude_globs", []))
    return (
        max_depth,
        [str(item) for item in include_globs if isinstance(item, str)] if isinstance(include_globs, list) else [],
        [str(item) for item in exclude_globs if isinstance(item, str)] if isinstance(exclude_globs, list) else [],
    )


def _safe_project_name(path: Path) -> str:
    name = re.sub(r"[^A-Za-z0-9_.-]+", "-", path.name.strip()).strip("-._")
    return name.lower() or "project"


def _safe_project_name_for_path(root: Path, path: Path, used_names: set[str]) -> str:
    name = _safe_project_name(path)
    if name not in used_names:
        return name
    relative_name = re.sub(r"[^A-Za-z0-9_.-]+", "-", path.relative_to(root).as_posix()).strip("-._")
    return relative_name.lower() or name


def _project_kind(directory: Path) -> str | None:
    if (directory / "pom.xml").is_file():
        return "java-maven"
    if (directory / "package.json").is_file():
        return "node-package"
    if (directory / "pyproject.toml").is_file():
        return "python-package"
    if (directory / "go.mod").is_file():
        return "go-module"
    if (directory / "Cargo.toml").is_file():
        return "rust-cargo"
    if (directory / "README.md").is_file():
        return "docs"
    return None


def _matches_any_glob(relative: str, globs: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(relative, pattern) for pattern in globs)


def scan_project_candidates(root: Path) -> list[dict[str, str]]:
    """Scan one repository root for common project boundaries."""
    max_depth, include_globs, exclude_globs = _scan_options(root)
    projects: list[dict[str, str]] = []
    used_names: set[str] = set()
    queue = [path for path in sorted(root.iterdir(), key=lambda item: item.name.lower()) if path.is_dir()]
    while queue:
        child = queue.pop(0)
        if child.name in DEFAULT_EXCLUDED_DIRS:
            continue
        relative = child.relative_to(root).as_posix()
        depth = len(Path(relative).parts)
        if depth > max_depth or _matches_any_glob(relative, exclude_globs):
            continue
        kind = _project_kind(child)
        if kind and (not include_globs or _matches_any_glob(relative, include_globs)):
            name = _safe_project_name_for_path(root, child, used_names)
            used_names.add(name)
            projects.append(
                {
                    "name": name,
                    "label": child.name,
                    "path": relative,
                    "kind": kind,
                }
            )
            continue
        if depth < max_depth:
            queue.extend(path for path in sorted(child.iterdir(), key=lambda item: item.name.lower()) if path.is_dir())
    root_kind = _project_kind(root)
    if root_kind and not projects:
        projects.append({"name": "root", "label": root.name, "path": ".", "kind": root_kind})
    return sorted(projects, key=lambda item: item["path"].lower())


def _default_verify(kind: str, path: str) -> str:
    commands = {
        "java-maven": f"mvn -f {path}/pom.xml test",
        "node-package": f"npm --prefix {path} test",
        "python-package": f"python -m pytest {path}",
        "go-module": f"go test ./...",
        "rust-cargo": f"cargo test --manifest-path {path}/Cargo.toml",
        "docs": "manual-doc-review",
    }
    return commands.get(kind, "manual-review")


def render_project_index_config(projects: list[dict[str, str]]) -> str:
    """Render a portable root-level project index TOML."""
    lines = [
        "# Root Praxis project index. Keep paths workspace-relative and portable.",
        "version = 1",
        'worktreeRoot = ".worktrees"',
        "",
    ]
    for project in projects:
        name = project["name"]
        path = project["path"]
        kind = project["kind"]
        label = project.get("label", name)
        lines.extend(
            [
                f"[projects.{name}]",
                f'label = "{label}"',
                f'path = "{path}"',
                f'kind = "{kind}"',
                f'verify = "{_default_verify(kind, path)}"',
                'defaultBranch = "main"',
                'upstreamBranch = "main"',
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def write_project_index_config(root: Path, *, force: bool = False) -> Path:
    """Scan a workspace and write `praxis.projects.toml` at the root."""
    output = root / PROJECTS_FILE
    if output.exists() and not force:
        raise FileExistsError(f"{PROJECTS_FILE} already exists; pass --force to overwrite")
    projects = scan_project_candidates(root)
    output.write_text(render_project_index_config(projects), encoding="utf-8")
    return output


def read_project_index(root: Path) -> tuple[dict[str, Any], str]:
    """Read the preferred root project index, falling back to the old path."""
    root_config = root / PROJECTS_FILE
    legacy_config = root / LEGACY_PROJECTS_FILE
    source = PROJECTS_FILE if root_config.is_file() else LEGACY_PROJECTS_FILE
    path = root_config if root_config.is_file() else legacy_config
    if not path.is_file():
        raise FileNotFoundError(f"missing project index: {PROJECTS_FILE}")
    with path.open("rb") as file:
        payload = tomllib.load(file)
    payload.setdefault("_praxis", {})["configSource"] = source
    return payload, source


def discover_extensions(root: Path) -> list[dict[str, str]]:
    """Return installed Praxis extension descriptors."""
    extension_root = root / ".praxis" / "extensions"
    if not extension_root.is_dir():
        return []
    extensions: list[dict[str, str]] = []
    for manifest in sorted(extension_root.glob("*/extension.toml")):
        with manifest.open("rb") as file:
            data = tomllib.load(file)
        extension_id = str(data.get("id") or manifest.parent.name)
        extensions.append(
            {
                "id": extension_id,
                "name": str(data.get("name") or extension_id),
                "path": manifest.parent.relative_to(root).as_posix(),
            }
        )
    return extensions


def project_index_summary(root: Path, *, scan: bool = False) -> dict[str, Any]:
    """Build the generic project-index section consumed by Praxis reports."""
    config, source = read_project_index(root)
    scanned = scan_project_candidates(root) if scan else []
    code_graph = root / ".praxis" / "out" / "code-graph.json"
    graph_summary: dict[str, Any] = {
        "path": ".praxis/out/code-graph.json",
        "status": "missing",
    }
    if code_graph.is_file():
        try:
            graph = json.loads(code_graph.read_text(encoding="utf-8"))
            graph_summary = {
                "path": ".praxis/out/code-graph.json",
                "status": "present",
                "files": graph.get("summary", {}).get("files", 0),
                "edges": graph.get("summary", {}).get("edges", 0),
                "edgeCoverage": graph.get("summary", {}).get("edgeCoverage", "none"),
            }
        except json.JSONDecodeError:
            graph_summary["status"] = "invalid"
    return {
        "root": ".",
        "configSource": source,
        "rootConfig": PROJECTS_FILE,
        "legacyConfig": LEGACY_PROJECTS_FILE,
        "scanEnabled": scan,
        "scannedProjects": scanned,
        "codeGraph": graph_summary,
        "generatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "projectCount": len(config.get("projects", {})),
    }


def write_project_index_report(root: Path, output: Path, *, scan: bool = False) -> Path:
    """Write a standalone generic project-index report."""
    config, _source = read_project_index(root)
    report = {
        "schemaVersion": 1,
        "projectIndex": project_index_summary(root, scan=scan),
        "projects": config.get("projects", {}),
        "extensions": discover_extensions(root),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output
