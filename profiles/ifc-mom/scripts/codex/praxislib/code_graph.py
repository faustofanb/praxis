from __future__ import annotations

import hashlib
import json
import re
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CODE_GRAPH_FILE = ".praxis/out/code-graph.json"
QUERY_REPORT = ".praxis/out/code-graph-query.json"
CODE_GRAPH_SCHEMA_VERSION = 2
SUPPORTED_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".vue", ".java", ".go", ".rs", ".md", ".toml", ".yaml", ".yml", ".json"}
SOURCE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".vue", ".java", ".go", ".rs"}
CONFIG_SUFFIXES = {".md", ".toml", ".yaml", ".yml", ".json"}
SCRIPT_SUFFIX_CANDIDATES = [".ts", ".tsx", ".js", ".jsx", ".vue", ".json"]
SCRIPT_INDEX_SUFFIX_CANDIDATES = [".ts", ".tsx", ".js", ".jsx", ".vue"]
EXCLUDED_DIR_NAMES = {
    ".git",
    ".github",
    ".opencode",
    ".vscode",
    ".worktree",
    ".worktrees",
    "node_modules",
    "target",
    "dist",
    "build",
    "__pycache__",
}
EXCLUDED_PATH_PREFIXES = {".praxis/out"}
EXCLUDED_COMPONENT_SEQUENCES = {(".tolaria", "cache"), (".tolaria", "plugins")}
CORE_SCAN_PATHS = ["scripts", ".praxis", "AGENTS.md", "README.md", "Taskfile.yml", "praxis.toml", "praxis.projects.toml"]


@dataclass(frozen=True)
class ScriptAlias:
    project_root: Path
    alias_prefix: str
    target_prefix: Path


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _is_excluded(root: Path, path: Path) -> bool:
    relative = _relative(root, path)
    if any(relative == excluded or relative.startswith(excluded + "/") for excluded in EXCLUDED_PATH_PREFIXES):
        return True
    parts = Path(relative).parts
    if any(part in EXCLUDED_DIR_NAMES for part in parts):
        return True
    return any(
        tuple(parts[index : index + len(sequence)]) == sequence
        for sequence in EXCLUDED_COMPONENT_SEQUENCES
        for index in range(0, len(parts) - len(sequence) + 1)
    )


def _scan_roots(root: Path) -> list[Path]:
    project_index = root / "praxis.projects.toml"
    if not project_index.is_file():
        return [root]
    payload = tomllib.loads(project_index.read_text(encoding="utf-8"))
    projects = payload.get("projects", {})
    roots: list[Path] = []
    if isinstance(projects, dict):
        for project in projects.values():
            if not isinstance(project, dict):
                continue
            raw_path = project.get("path")
            if not isinstance(raw_path, str):
                continue
            path = root / raw_path
            if path.exists():
                roots.append(path)
    for raw_path in CORE_SCAN_PATHS:
        path = root / raw_path
        if path.exists():
            roots.append(path)
    return roots or [root]


def _files(root: Path) -> list[Path]:
    files: list[Path] = []
    for scan_root in _scan_roots(root):
        if scan_root.is_file():
            candidates = [scan_root]
        else:
            candidates = list(scan_root.rglob("*"))
        files.extend(
            path
            for path in candidates
            if path.is_file() and path.suffix in SUPPORTED_SUFFIXES and not _is_excluded(root, path)
        )
    return sorted(set(files))


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_fingerprint(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "size": stat.st_size,
        "mtimeNs": stat.st_mtime_ns,
        "sha256": _file_hash(path),
    }


def _source_snapshot(root: Path, files: list[Path]) -> dict[str, Any]:
    paths = [_relative(root, path) for path in files]
    stats = [path.stat() for path in files]
    return {
        "fileCount": len(files),
        "totalSize": sum(stat.st_size for stat in stats),
        "maxMtimeNs": max((stat.st_mtime_ns for stat in stats), default=0),
        "pathsHash": hashlib.sha256("\n".join(paths).encode("utf-8")).hexdigest(),
    }


def _known_candidate(root: Path, candidate: Path, known_paths: set[str]) -> str | None:
    try:
        target = candidate.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None
    return target if target in known_paths else None


def _known_suffix(suffix: str, known_paths: set[str]) -> str | None:
    matches = sorted(path for path in known_paths if path.endswith(suffix))
    return matches[0] if matches else None


def _module_candidates(root: Path, path: Path, module: str, suffixes: list[str]) -> list[Path]:
    clean_module = module.lstrip(".")
    parts = [part for part in clean_module.split(".") if part]
    if module.startswith("."):
        level = len(module) - len(module.lstrip("."))
        base = path.parent
        for _ in range(max(0, level - 1)):
            base = base.parent
        return [base.joinpath(*parts).with_suffix(suffix) for suffix in suffixes] + [
            base.joinpath(*parts, "__init__.py")
        ]
    if not parts:
        return []
    direct = [root.joinpath(*parts).with_suffix(suffix) for suffix in suffixes]
    direct.append(root.joinpath(*parts, "__init__.py"))
    if len(parts) == 1:
        direct.extend(path.parent.joinpath(parts[0]).with_suffix(suffix) for suffix in suffixes)
    return direct


def _strip_json_comments(text: str) -> str:
    output: list[str] = []
    in_string = False
    escaped = False
    index = 0
    while index < len(text):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""
        if in_string:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            output.append(char)
            index += 1
            continue
        if char == "/" and next_char == "/":
            index += 2
            while index < len(text) and text[index] not in "\r\n":
                index += 1
            continue
        if char == "/" and next_char == "*":
            index += 2
            while index + 1 < len(text) and not (text[index] == "*" and text[index + 1] == "/"):
                if text[index] in "\r\n":
                    output.append(text[index])
                index += 1
            index += 2
            continue
        output.append(char)
        index += 1
    return "".join(output)


def _json_payload(path: Path) -> dict[str, Any]:
    text = _strip_json_comments(_read_text(path))
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _join_config_path(base: Path, raw_path: str) -> Path:
    normalized = raw_path.replace("\\", "/")
    parts = [part for part in normalized.split("/") if part and part != "."]
    return base.joinpath(*parts) if parts else base


def _is_script_config(path: Path) -> bool:
    return path.name == "jsconfig.json" or (path.name.startswith("tsconfig") and path.name.endswith(".json"))


def _script_aliases(files: list[Path]) -> list[ScriptAlias]:
    aliases: list[ScriptAlias] = []
    for config_path in sorted(path for path in files if _is_script_config(path)):
        project_root = config_path.parent
        compiler_options = _json_payload(config_path).get("compilerOptions", {})
        if not isinstance(compiler_options, dict):
            continue
        base_url_raw = compiler_options.get("baseUrl", ".")
        base_url = _join_config_path(project_root, base_url_raw) if isinstance(base_url_raw, str) else project_root
        paths = compiler_options.get("paths", {})
        if not isinstance(paths, dict):
            continue
        for alias_pattern, target_patterns in paths.items():
            if not isinstance(alias_pattern, str) or not isinstance(target_patterns, list):
                continue
            alias_prefix = alias_pattern.replace("\\", "/").split("*", 1)[0]
            for target_pattern in target_patterns:
                if not isinstance(target_pattern, str):
                    continue
                target_prefix = target_pattern.split("*", 1)[0]
                if alias_prefix:
                    aliases.append(
                        ScriptAlias(
                            project_root=project_root,
                            alias_prefix=alias_prefix,
                            target_prefix=_join_config_path(base_url, target_prefix),
                        )
                    )
    return sorted(aliases, key=lambda item: (-len(item.project_root.parts), -len(item.alias_prefix)))


def _script_path_candidates(base: Path) -> list[Path]:
    candidates = [base] if base.suffix else []
    if not base.suffix:
        candidates.extend(base.with_suffix(suffix) for suffix in SCRIPT_SUFFIX_CANDIDATES)
        candidates.extend(base / f"index{suffix}" for suffix in SCRIPT_INDEX_SUFFIX_CANDIDATES)
    seen: set[Path] = set()
    unique: list[Path] = []
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            unique.append(candidate)
    return unique


def _script_specifier_candidates(path: Path, specifier: str, aliases: list[ScriptAlias]) -> list[Path]:
    clean_specifier = specifier.split("?", 1)[0]
    hash_index = clean_specifier.find("#")
    if hash_index > 0:
        clean_specifier = clean_specifier[:hash_index]
    if clean_specifier.startswith("."):
        return _script_path_candidates(path.parent / clean_specifier)
    candidates: list[Path] = []
    for alias in aliases:
        if not _is_relative_to(path, alias.project_root):
            continue
        if not clean_specifier.startswith(alias.alias_prefix):
            continue
        remainder = clean_specifier[len(alias.alias_prefix) :]
        candidates.extend(_script_path_candidates(alias.target_prefix / remainder))
    return candidates


def _python_import_edges(root: Path, path: Path, known_paths: set[str]) -> list[dict[str, str]]:
    if path.suffix != ".py":
        return []
    text = _read_text(path)
    source = _relative(root, path)
    edges: list[dict[str, str]] = []
    for match in re.finditer(r"^\s*(?:from\s+([.\w]+)\s+import|import\s+([A-Za-z_][\w.]*))", text, re.MULTILINE):
        module = match.group(1) or match.group(2) or ""
        candidates = _module_candidates(root, path, module, [".py"])
        module_suffix = module.lstrip(".").replace(".", "/")
        for candidate in candidates:
            target = _known_candidate(root, candidate, known_paths)
            if target:
                edges.append({"source": source, "target": target, "kind": "python-import"})
                break
        else:
            suffix_candidates = [f"{module_suffix}.py", f"{module_suffix}/__init__.py"] if "." in module_suffix else []
            for suffix in suffix_candidates:
                match_path = _known_suffix(suffix, known_paths)
                if match_path:
                    edges.append({"source": source, "target": match_path, "kind": "python-import"})
                    break
    return edges


def _script_import_edges(root: Path, path: Path, known_paths: set[str], aliases: list[ScriptAlias]) -> list[dict[str, str]]:
    if path.suffix not in {".ts", ".tsx", ".js", ".jsx", ".vue"}:
        return []
    text = _read_text(path)
    source = _relative(root, path)
    edges: list[dict[str, str]] = []
    patterns = [
        r"(?<!@)\b(?:import|export)\s+(?:[^'\"]+\s+from\s+)?['\"]([^'\"]+)['\"]",
        r"import\(\s*['\"]([^'\"]+)['\"]\s*\)",
        r"require\(\s*['\"]([^'\"]+)['\"]\s*\)",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            specifier = match.group(1)
            for candidate in _script_specifier_candidates(path, specifier, aliases):
                target = _known_candidate(root, candidate, known_paths)
                if target:
                    edges.append({"source": source, "target": target, "kind": "typescript-import"})
                    break
    return edges


def _java_package_and_class(path: Path) -> tuple[str, str, str]:
    text = _read_text(path)
    package_match = re.search(r"^\s*package\s+([\w.]+)\s*;", text, re.MULTILINE)
    package = package_match.group(1) if package_match else ""
    class_match = re.search(r"\b(?:class|interface|enum|record)\s+([A-Za-z_]\w*)", text)
    class_name = class_match.group(1) if class_match else path.stem
    return package, class_name, text


def _strip_java_non_code(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    text = re.sub(r"//.*", " ", text)
    text = re.sub(r'"(?:\\.|[^"\\])*"', '""', text)
    text = re.sub(r"'(?:\\.|[^'\\])*'", "''", text)
    return text


def _java_symbol_indexes(root: Path, files: list[Path]) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    symbols: dict[str, str] = {}
    package_symbols: dict[str, dict[str, str]] = {}
    for path in files:
        if path.suffix != ".java":
            continue
        package, class_name, _ = _java_package_and_class(path)
        if package:
            relative_path = _relative(root, path)
            symbols[f"{package}.{class_name}"] = relative_path
            package_symbols.setdefault(package, {})[class_name] = relative_path
    return symbols, package_symbols


def _java_import_edges(root: Path, path: Path, java_symbols: dict[str, str]) -> list[dict[str, str]]:
    if path.suffix != ".java":
        return []
    text = _read_text(path)
    source = _relative(root, path)
    edges: list[dict[str, str]] = []
    for match in re.finditer(r"^\s*import\s+(?:static\s+)?([\w.]+)\s*;", text, re.MULTILINE):
        symbol = match.group(1)
        target = java_symbols.get(symbol)
        if target:
            edges.append({"source": source, "target": target, "kind": "java-import"})
    return edges


def _java_reference_edges(root: Path, path: Path, package_symbols: dict[str, dict[str, str]]) -> list[dict[str, str]]:
    if path.suffix != ".java":
        return []
    package, _, text = _java_package_and_class(path)
    source = _relative(root, path)
    same_package_symbols = package_symbols.get(package, {})
    if not same_package_symbols:
        return []
    code = _strip_java_non_code(text)
    tokens = set(re.findall(r"\b[A-Z][A-Za-z0-9_]*\b", code))
    edges: list[dict[str, str]] = []
    for class_name in sorted(tokens & set(same_package_symbols)):
        target = same_package_symbols[class_name]
        if target != source:
            edges.append({"source": source, "target": target, "kind": "java-reference"})
    return edges


def _dedupe_edges(edges: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str, str]] = set()
    unique: list[dict[str, str]] = []
    for edge in edges:
        key = (edge["source"], edge["target"], edge["kind"])
        if key not in seen:
            seen.add(key)
            unique.append(edge)
    return unique


def _edge_summary(edges: list[dict[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for edge in edges:
        kind = edge.get("kind", "unknown")
        counts[kind] = counts.get(kind, 0) + 1
    return counts


def _node_search_terms(path: Path) -> list[str]:
    if path.suffix not in SOURCE_SUFFIXES:
        return []
    text = _read_text(path)
    terms: set[str] = set()
    symbol_patterns = [
        r"\b(?:class|interface|enum|record|type)\s+([A-Za-z_][A-Za-z0-9_]*)",
        r"\b(?:def|function|const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)",
    ]
    for pattern in symbol_patterns:
        terms.update(match.group(1).lower() for match in re.finditer(pattern, text))
    if path.suffix in {".ts", ".tsx", ".js", ".jsx", ".vue"}:
        for match in re.finditer(r"\bexport\s+\{([^}]+)\}", text):
            terms.update(item.strip().lower() for item in match.group(1).split(","))
    return sorted(term.strip().lower() for term in terms if term.strip())


def _query_score(node: dict[str, Any], query_lower: str) -> int:
    node_path = str(node.get("path", ""))
    suffix = str(node.get("suffix", ""))
    basename = str(node.get("basenameLower") or Path(node_path).name.lower())
    stem = str(node.get("stemLower") or Path(node_path).stem.lower())
    score = 0
    if stem == query_lower:
        score += 12
    if query_lower in basename:
        score += 8
    if query_lower in node_path.lower():
        score += 4
    if suffix in SOURCE_SUFFIXES:
        score += 3
    elif suffix in CONFIG_SUFFIXES:
        score -= 2
    terms = [str(term).lower() for term in node.get("searchTerms", [])]
    if query_lower in terms:
        score += 4
    elif any(query_lower in term for term in terms):
        score += 2
    return score


def build_code_graph(root: Path) -> Path:
    """Build a lightweight repository code graph."""
    files = _files(root)
    known_paths = {_relative(root, path) for path in files}
    nodes = []
    for path in files:
        relative_path = _relative(root, path)
        fingerprint = _file_fingerprint(path)
        nodes.append(
            {
                "id": relative_path,
                "path": relative_path,
                "suffix": path.suffix,
                "basenameLower": path.name.lower(),
                "stemLower": path.stem.lower(),
                "size": fingerprint["size"],
                "mtimeNs": fingerprint["mtimeNs"],
                "sha256": fingerprint["sha256"],
                "fingerprint": fingerprint,
                "searchTerms": _node_search_terms(path),
            }
        )
    edges: list[dict[str, str]] = []
    java_symbols, java_package_symbols = _java_symbol_indexes(root, files)
    script_aliases = _script_aliases(files)
    for path in files:
        edges.extend(_python_import_edges(root, path, known_paths))
        edges.extend(_script_import_edges(root, path, known_paths, script_aliases))
        edges.extend(_java_import_edges(root, path, java_symbols))
        edges.extend(_java_reference_edges(root, path, java_package_symbols))
    edges = _dedupe_edges(edges)
    graph = {
        "schemaVersion": CODE_GRAPH_SCHEMA_VERSION,
        "generatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "manifest": {
            "schemaVersion": CODE_GRAPH_SCHEMA_VERSION,
            "indexerVersion": "praxis-code-graph-v2",
            "workspaceRoot": ".",
            "scanConfigHash": hashlib.sha256(
                json.dumps(
                    {
                        "supportedSuffixes": sorted(SUPPORTED_SUFFIXES),
                        "sourceSuffixes": sorted(SOURCE_SUFFIXES),
                        "configSuffixes": sorted(CONFIG_SUFFIXES),
                        "excludedDirNames": sorted(EXCLUDED_DIR_NAMES),
                        "excludedPathPrefixes": sorted(EXCLUDED_PATH_PREFIXES),
                        "coreScanPaths": CORE_SCAN_PATHS,
                    },
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest(),
        },
        "sourceSnapshot": _source_snapshot(root, files),
        "summary": {
            "files": len(nodes),
            "edges": len(edges),
            "edgeCoverage": "present" if edges else "none",
            "edgeKinds": _edge_summary(edges),
        },
        "nodes": nodes,
        "edges": edges,
    }
    output = root / CODE_GRAPH_FILE
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Praxis code graph: {output}")
    return output


def _graph_path(root: Path) -> Path:
    return root / CODE_GRAPH_FILE


def code_graph_issues(root: Path) -> list[str]:
    """Return freshness and coverage issues for the existing graph."""
    path = _graph_path(root)
    if not path.is_file():
        return ["code graph is missing; run task system -- code-graph build"]
    try:
        graph = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ["code graph is invalid JSON; run task system -- code-graph build"]
    if graph.get("schemaVersion") != CODE_GRAPH_SCHEMA_VERSION:
        return ["code graph schema version is unsupported; run task system -- code-graph build"]
    current_files = _files(root)
    current_paths = {_relative(root, item) for item in current_files}
    graph_nodes = {str(node.get("path")): node for node in graph.get("nodes", []) if isinstance(node, dict)}
    graph_paths = set(graph_nodes)
    issues: list[str] = []
    for missing in sorted(current_paths - graph_paths)[:20]:
        issues.append(f"missing indexed file: {missing}")
    for obsolete in sorted(graph_paths - current_paths)[:20]:
        issues.append(f"obsolete indexed file: {obsolete}")
    stale_count = 0
    changed_count = 0
    for source in current_files:
        relative_path = _relative(root, source)
        node = graph_nodes.get(relative_path)
        if not node:
            continue
        fingerprint = node.get("fingerprint")
        if not isinstance(fingerprint, dict):
            issues.append(f"missing source fingerprint: {relative_path}")
            continue
        current = _file_fingerprint(source)
        same_content = current.get("size") == fingerprint.get("size") and current.get("sha256") == fingerprint.get("sha256")
        if same_content:
            continue
        if int(current.get("mtimeNs", 0)) > int(fingerprint.get("mtimeNs", 0)):
            issues.append(f"stale source file: {relative_path}")
            stale_count += 1
            if stale_count >= 20:
                break
        else:
            issues.append(f"changed source file: {relative_path}")
            changed_count += 1
            if changed_count >= 20:
                break
    return issues


def _graph_snapshot_matches(root: Path, graph: dict[str, Any]) -> bool:
    if graph.get("schemaVersion") != CODE_GRAPH_SCHEMA_VERSION:
        return False
    expected = graph.get("sourceSnapshot")
    if not isinstance(expected, dict):
        return False
    current = _source_snapshot(root, _files(root))
    keys = ("fileCount", "totalSize", "maxMtimeNs", "pathsHash")
    return all(expected.get(key) == current.get(key) for key in keys)


def _load_graph(root: Path, *, refresh_stale: bool = False) -> dict[str, Any]:
    path = root / CODE_GRAPH_FILE
    if not path.is_file():
        build_code_graph(root)
    else:
        try:
            graph = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            graph = {}
        if refresh_stale and not _graph_snapshot_matches(root, graph):
            build_code_graph(root)
    return json.loads(path.read_text(encoding="utf-8"))


def query_code_graph(root: Path, query: str, *, limit: int = 10, refresh_stale: bool = False) -> dict[str, Any]:
    """Query the code graph by path or lightweight content match."""
    graph = _load_graph(root, refresh_stale=refresh_stale)
    matches: list[dict[str, Any]] = []
    query_lower = query.lower()
    for node in graph.get("nodes", []):
        score = _query_score(node, query_lower)
        if score:
            matches.append({"path": node["path"], "score": score})
    matches.sort(key=lambda item: (-item["score"], item["path"]))
    result = {
        "schemaVersion": 1,
        "query": query,
        "matches": matches[:limit],
    }
    output = root / QUERY_REPORT
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def code_graph_check(root: Path) -> int:
    """Validate that a graph exists and has at least one node."""
    path = _graph_path(root)
    issues = code_graph_issues(root)
    if path.is_file():
        try:
            graph = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            graph = {}
        if isinstance(graph.get("nodes"), list) and not graph.get("nodes"):
            issues.append("code graph has no indexed nodes")
    ok = not issues
    print(f"Praxis code graph check: {'PASS' if ok else 'FAIL'}")
    print(f"  graph: {path}")
    if issues:
        print("Code graph issues:")
        for issue in issues[:40]:
            print(f"  - {issue}")
        print("  rebuild: task system -- code-graph build")
    return 0 if ok else 1
