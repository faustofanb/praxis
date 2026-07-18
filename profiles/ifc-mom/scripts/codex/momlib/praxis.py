from __future__ import annotations

import json
import os
import re
import time
import tomllib
from pathlib import Path
from typing import Any

from .config import load_config
from .context import verify_command, worker_rule_skill_paths
from .docs import find_requirement_dir
from .paths import PRAXIS_OUTPUT_DIR, ROOT_DIR
from . import praxis_contracts
from .praxis_profile import ADAPTER_FILE, CORE_FILE, praxis_profile_payload
from praxislib.project_index import discover_extensions, project_index_summary


PRAXIS_DIR = Path(os.environ.get("PRAXIS_DIR", PRAXIS_OUTPUT_DIR))
PRAXIS_CONTEXT_DIR = PRAXIS_DIR / "context"
PRAXIS_READINESS_DIR = PRAXIS_DIR / "readiness"
PRAXIS_INDEX_FILE = PRAXIS_DIR / "project-index.json"


def relative(path: Path) -> str:
    """Return repository-relative path for stable output."""
    try:
        return str(path.relative_to(ROOT_DIR))
    except ValueError:
        return str(path)


def markdown_files(root: Path) -> list[Path]:
    """Return Markdown files below a root, tolerating absent directories."""
    if not root.is_dir():
        return []
    return sorted(path for path in root.rglob("*.md") if path.is_file())


def rule_files() -> list[Path]:
    """Return Praxis core and extension rule Markdown files."""
    roots = [ROOT_DIR / ".praxis" / "rules"]
    extension_root = ROOT_DIR / ".praxis" / "extensions"
    if extension_root.is_dir():
        roots.extend(sorted(path for path in extension_root.glob("*/rules") if path.is_dir()))
    return sorted(path for root in roots if root.is_dir() for path in root.rglob("*.md"))


def skill_files() -> list[Path]:
    """Return Praxis extension skill entry files."""
    roots = [ROOT_DIR / ".praxis" / "skills"]
    extension_root = ROOT_DIR / ".praxis" / "extensions"
    if extension_root.is_dir():
        roots.extend(sorted(path for path in extension_root.glob("*/skills") if path.is_dir()))
    return sorted(path for root in roots if root.is_dir() for path in root.rglob("SKILL.md"))


def _is_command_legacy(raw: str) -> bool:
    """Return whether a command still uses the deprecated praxis-prefixed entrypoint."""
    tokens = raw.split()
    try:
        index = tokens.index("scripts/codex/task.py")
    except ValueError:
        return " praxis " in f" {raw} " or raw.startswith("praxis ")
    if index + 1 < len(tokens) and tokens[index + 1] == "praxis":
        return True
    return raw.startswith("praxis ") or " task praxis " in f" {raw} "


def _missing_task_separator(raw: str) -> bool:
    """Return whether a go-task dispatcher example is missing the `--` argument separator."""
    tokens = raw.split()
    if tokens[:2] == ["rtk", "task"]:
        offset = 1
    else:
        offset = 0
    if len(tokens) <= offset + 2:
        return False
    if tokens[offset] != "task":
        return False
    group = tokens[offset + 1]
    return group in praxis_contracts.DISPATCH_GROUPS and tokens[offset + 2] != "--"


def _scan_command_examples() -> tuple[list[str], list[str]]:
    """Collect task entry examples from known docs and policy files."""
    command_examples: list[str] = []
    legacy_examples: list[str] = []
    commands_toml = ROOT_DIR / ".praxis" / "commands.toml"
    execpolicy = ROOT_DIR / ".codex" / "execpolicy.rules"

    def add(raw: str) -> None:
        raw = raw.strip().strip("`").strip(",")
        if not raw:
            return
        if "scripts/codex/task.py" not in raw and " task " not in f" {raw} ":
            return
        command = raw
        command_examples.append(command)
        if _is_command_legacy(command) or _missing_task_separator(command):
            legacy_examples.append(command)

    if commands_toml.is_file():
        try:
            payload = tomllib.loads(commands_toml.read_text(encoding="utf-8"))
            for item in payload.get("command", []):
                argv = item.get("argv")
                if isinstance(argv, str):
                    add(argv)
        except Exception:
            pass

    if execpolicy.is_file():
        line_pattern = re.compile(r"^\s*['\"]([^'\"]+)['\"]")
        for line in execpolicy.read_text(encoding="utf-8").splitlines():
            match = line_pattern.match(line)
            if not match:
                continue
            add(match.group(1))

    for path in (ROOT_DIR / "AGENTS.md", ROOT_DIR / "README.md"):
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if "scripts/codex/task.py" not in line:
                continue
            for fragment in line.split():
                if "scripts/codex/task.py" not in fragment:
                    continue
                add(fragment)

    return sorted(set(command_examples)), sorted(set(legacy_examples))


def command_audit(mode: str = "auto") -> Path:
    """Audit command-entry style consistency and write a machine-readable report."""
    if mode not in {"auto", "python", "bun"}:
        raise ValueError(f"unknown command-audit mode: {mode}")
    commands, legacy = _scan_command_examples()
    status = "PASS" if not legacy else "WARN"

    PRAXIS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = PRAXIS_DIR / "command-audit.json"
    report = {
        "schemaVersion": 1,
        "generatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "summary": {
            "engine": "python" if mode != "bun" else "bun",
            "status": status,
            "totalScanned": len(commands),
            "legacyCommandExamples": len(legacy),
            "policy": "docs-and-entrypoints-should-use-task-without-praxis-prefix",
        },
        "commandPattern": "task <group> ... / uv run scripts/codex/task.py <group> ...",
        "legacyCommandExamples": legacy,
        "commands": commands,
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Praxis command-audit: {status} ({mode})")
    print(f"  report: {report_path}")
    if legacy:
        print("Legacy examples:")
        for item in legacy[:20]:
            print(f"  - {item}")
    return report_path


def _workflow_command_contract_errors() -> list[str]:
    """Validate that machine-readable command indexes match executable command contracts."""
    errors: list[str] = []
    commands_toml = ROOT_DIR / ".praxis" / "commands.toml"
    manifest_toml = ROOT_DIR / ".praxis" / "manifest.toml"
    methodology_toml = ROOT_DIR / ".praxis" / "methodology.toml"
    command_ids: set[str] = set()

    if commands_toml.is_file():
        payload = tomllib.loads(commands_toml.read_text(encoding="utf-8"))
        for item in payload.get("command", []):
            command_id = item.get("id")
            if isinstance(command_id, str):
                command_ids.add(command_id)
            argv = item.get("argv")
            if isinstance(argv, str) and _missing_task_separator(argv):
                errors.append(f"commands.toml {command_id or '<unknown>'} missing go-task -- separator: {argv}")

    for extension_commands in sorted((ROOT_DIR / ".praxis" / "extensions").glob("*/commands.toml")):
        payload = tomllib.loads(extension_commands.read_text(encoding="utf-8"))
        for item in payload.get("command", []):
            command_id = item.get("id")
            if isinstance(command_id, str):
                command_ids.add(command_id)

    def check_index_refs(path: Path, table_name: str) -> None:
        if not path.is_file():
            return
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
        tables = payload.get(table_name, {})
        if isinstance(tables, dict):
            items = tables.values()
        elif isinstance(tables, list):
            items = tables
        else:
            items = []
        for item in items:
            if not isinstance(item, dict):
                continue
            owner = item.get("id") or item.get("project") or item.get("triggers") or "<unknown>"
            for command_key in ("commands", "closeout_commands", "diagnostic_commands"):
                for command_id in item.get(command_key, []):
                    if command_id not in command_ids:
                        errors.append(f"{path.name} references unknown command {command_id!r} in {owner}")
            for key in ("rules", "skills"):
                for ref in item.get(key, []):
                    if not isinstance(ref, str):
                        continue
                    ref_path = ROOT_DIR / ref
                    if not ref_path.exists():
                        errors.append(f"{path.name} references missing {key[:-1]} path {ref!r} in {owner}")

    check_index_refs(manifest_toml, "task")
    for extension_manifest in sorted((ROOT_DIR / ".praxis" / "extensions").glob("*/manifest.toml")):
        check_index_refs(extension_manifest, "task")
    check_index_refs(methodology_toml, "principle")
    return errors


def praxis_check() -> int:
    """Validate the portable Praxis core, adapter, and command contracts."""
    errors = _workflow_command_contract_errors()
    workflow_payload: dict[str, Any] = {}
    try:
        workflow_payload = praxis_profile_payload(ROOT_DIR)
    except Exception as exc:
        errors.append(f"Praxis profile validation failed: {exc}")
    else:
        errors.extend(workflow_payload.get("issues", []))
    print(f"Praxis check: {'FAIL' if errors else 'PASS'}")
    print("Checked:")
    print(f"  - {CORE_FILE}")
    print(f"  - {ADAPTER_FILE}")
    if workflow_payload:
        print(f"Praxis profile: {workflow_payload.get('status', '')}")
        print("Portable stages:")
        for stage in workflow_payload.get("portableStages", []):
            print(f"  - {stage}")
    if errors:
        print("Errors:")
        for error in errors:
            print(f"  - {error}")
        return 1
    return 0


def praxis_index(scan: bool = False) -> Path:
    """Write a local project fact index for AI agents."""
    profile = praxis_profile_payload(ROOT_DIR)
    config = load_config()
    rules = rule_files()
    skills = skill_files()
    commands = praxis_contracts.praxis_commands()
    data = {
        "schemaVersion": 1,
        "praxis": {
            "status": profile.get("status", ""),
            "core": CORE_FILE,
            "adapter": ADAPTER_FILE,
        },
        "projectIndex": project_index_summary(ROOT_DIR, scan=scan),
        "extensions": discover_extensions(ROOT_DIR),
        "projects": config.get("projects", {}),
        "commands": commands,
        "counts": {
            "projects": len(config.get("projects", {})),
            "rules": len(rules),
            "skills": len(skills),
            "commands": len(commands),
            "extensions": len(discover_extensions(ROOT_DIR)),
        },
        "rules": [relative(path) for path in rules],
        "skills": [relative(path) for path in skills],
    }
    PRAXIS_DIR.mkdir(parents=True, exist_ok=True)
    PRAXIS_INDEX_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Praxis index: {PRAXIS_INDEX_FILE}")
    return PRAXIS_INDEX_FILE


def safe_packet_name(project: str, requirement_name: str) -> str:
    """Return a stable filename for a requirement context packet."""
    return f"{project}-{requirement_name.replace('/', '-').replace(':', '-')}.json"


def praxis_readiness_path(project: str, requirement_name: str) -> Path:
    """Return the default readiness report path for a project + requirement."""
    return PRAXIS_READINESS_DIR / f"{safe_packet_name(project, requirement_name).removesuffix('.json')}.json"


def praxis_write_readiness_report(
    project: str, requirement_name: str, context_packet: Path, results: dict[str, int]
) -> Path:
    """Write a normalized readiness aggregation report."""
    status = "PASS" if all(code == 0 for code in results.values()) else "FAIL"
    report = {
        "schemaVersion": 1,
        "project": project,
        "requirementName": requirement_name,
        "status": status,
        "controlPlane": {"primaryCommand": "task"},
        "contextPacket": relative(context_packet),
        "results": {
            gate: {"exitCode": code, "status": "PASS" if code == 0 else "FAIL"}
            for gate, code in results.items()
        },
    }
    PRAXIS_READINESS_DIR.mkdir(parents=True, exist_ok=True)
    path = praxis_readiness_path(project, requirement_name)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Praxis readiness: {status}")
    print(f"  report: {path}")
    return path


def _code_graph_context_summary() -> dict[str, Any]:
    """Return Code Graph context when the root project index is available."""
    try:
        return project_index_summary(ROOT_DIR).get("codeGraph", {})
    except FileNotFoundError:
        return {}


def portable_config_path(path_text: Any) -> str:
    """Keep report paths workspace-relative when a config already resolved them."""
    if not isinstance(path_text, str) or not path_text:
        return ""
    path = Path(path_text)
    return relative(path) if path.is_absolute() else path_text


def string_list(value: Any) -> list[str]:
    return [str(item) for item in value if isinstance(item, str)] if isinstance(value, list) else []


def praxis_context_packet(config: dict[str, Any], project: str, requirement_name: str) -> Path:
    """Write the compressed AI context packet used by Praxis-controlled commands."""
    req_dir = find_requirement_dir(config, requirement_name)
    project_data = config.get("projects", {}).get(project, {})
    packet = {
        "schemaVersion": 1,
        "project": project,
        "requirementName": requirement_name,
        "controlPlane": {"primaryCommand": "task"},
        "facts": {
            "requirementDir": relative(req_dir),
            "projectLabel": str(project_data.get("label", "")),
            "projectDescription": str(project_data.get("description", "")),
            "projectAliases": string_list(project_data.get("aliases")),
            "projectPath": portable_config_path(project_data.get("path", "")),
            "projectKind": project_data.get("kind", ""),
            "defaultBranch": project_data.get("defaultBranch", ""),
            "upstreamBranch": project_data.get("upstreamBranch", ""),
        },
        "workerContext": {
            "rulesAndSkills": worker_rule_skill_paths(project),
            "verification": verify_command(project, requirement_name),
            "codeGraph": _code_graph_context_summary(),
        },
        "evidenceGates": [
            "original-requirement-preserved",
            "analysis-evidence-required",
            "database-readonly-investigation-when-data-related",
            "minimal-verification-before-completion",
            "explicit-confirmation-before-delivery-actions",
        ],
        "nextCommands": [
            praxis_contracts.praxis_usage(f"context --brief {project} {requirement_name}"),
            praxis_contracts.praxis_usage(f"context {project} {requirement_name}"),
            praxis_contracts.praxis_usage(f"project preflight {project} {requirement_name}"),
            praxis_contracts.praxis_usage(f"gate ready {project} {requirement_name}"),
            praxis_contracts.praxis_usage(f"project verify {project} {requirement_name}"),
            praxis_contracts.praxis_usage(f"delivery finish {project} {requirement_name}"),
            praxis_contracts.praxis_usage(f"delivery status-all {requirement_name}"),
            praxis_contracts.praxis_usage(f"delivery commit-split-all {requirement_name} <production-message>"),
            praxis_contracts.praxis_usage(f"delivery deliver-all {requirement_name}"),
            praxis_contracts.praxis_usage(f"delivery cleanup-all {requirement_name}"),
        ],
    }
    PRAXIS_CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
    path = PRAXIS_CONTEXT_DIR / safe_packet_name(project, requirement_name)
    path.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Praxis context packet: {path}")
    return path
