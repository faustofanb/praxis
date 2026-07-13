from __future__ import annotations

import json
import os
import shutil
import re
import sys
import time
import tomllib
from pathlib import Path
from typing import Any

from .config import load_config
from .context import verify_command, worker_rule_skill_paths
from .docs import find_requirement_dir
from .names import safe_path_leaf
from .paths import PRAXIS_OUTPUT_DIR, ROOT_DIR
from . import praxis_contracts
from .praxis_profile import ADAPTER_FILE, CORE_FILE, praxis_profile_payload
from .praxis_templates import template_report
from praxislib.project_index import discover_extensions, project_index_summary


PRAXIS_PROFILE = ROOT_DIR / ".praxis" / "profile.toml"
PRAXIS_DIR = Path(os.environ.get("PRAXIS_DIR", PRAXIS_OUTPUT_DIR))
PRAXIS_CONTEXT_DIR = PRAXIS_DIR / "context"
PRAXIS_VERDICT_DIR = PRAXIS_DIR / "verdicts"
PRAXIS_READINESS_DIR = PRAXIS_DIR / "readiness"
PRAXIS_HANDOFF_DIR = PRAXIS_DIR / "handoffs"
PRAXIS_LOCK_DIR = PRAXIS_DIR / "locks"
PRAXIS_INDEX_FILE = PRAXIS_DIR / "project-index.json"
PRAXIS_PROPOSALS_FILE = PRAXIS_DIR / "evolution-proposals.json"
PRAXIS_RUNTIME_FILE = PRAXIS_DIR / "runtime-evaluation.json"
PRAXIS_ROUTE_FILE = ROOT_DIR / ".praxis" / "rules" / "praxis-workflow.md"
TODO_FILE = ROOT_DIR / "todo.md"


REQUIRED_LAYERS = ["epistemology", "dialectics", "historical_materialism", "organization"]
ROLE_LABELS = ["Execution", "Quality", "Delivery", "Knowledge", "Evolution"]
VERDICT_ROLE_LABELS = {"quality": "Quality", "delivery": "Delivery"}


def load_toml(path: Path) -> dict[str, Any]:
    """Read TOML with the standard library."""
    with path.open("rb") as file:
        return tomllib.load(file)


def _fallback_profile() -> dict[str, Any]:
    """Return a compatibility profile when `.praxis/profile.toml` is missing."""
    return {
        "schema_version": 1,
        "name": "praxis-fallback",
        "status": "partial",
        "baseline": "lightweight-structured-layer",
        "control_plane": {
            "primary_command": "task",
            "legacy_commands_are_aliases": True,
            "command_groups": ["req", "project", "context", "gate", "delivery", "system"],
            "runtime_recommendation": "hybrid-python-core-bun-ts-adapters",
        },
        "layers": {
            layer: {"engineering_name": f"fallback-{layer.replace('_', '-')}"}
            for layer in REQUIRED_LAYERS
        },
        "milestone": [
            {"id": "M1"},
            {"id": "M2"},
            {"id": "M3"},
            {"id": "M4"},
        ],
    }


def relative(path: Path) -> str:
    """Return repository-relative path for stable output."""
    try:
        return str(path.relative_to(ROOT_DIR))
    except ValueError:
        return str(path)


def praxis_profile(strict: bool = False) -> dict[str, Any]:
    """Load the heavy Praxis profile.

    When strict is False and the profile file is absent, return a local compatibility
    profile so guard/context commands do not fail in lightweight trees.
    """
    if not PRAXIS_PROFILE.is_file():
        if strict:
            raise FileNotFoundError(f"missing {relative(PRAXIS_PROFILE)}")
        return _fallback_profile()
    return load_toml(PRAXIS_PROFILE)


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


def pending_todo_lines() -> list[str]:
    """Return pending workflow-hardening lines from todo.md."""
    if not TODO_FILE.is_file():
        return []
    return [
        line.strip()
        for line in TODO_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("- [待固化]")
    ]


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
    """Validate the heavy Praxis profile, route file, and project adapter."""
    errors: list[str] = []
    workflow_payload: dict[str, Any] = {}
    template_payload: dict[str, Any] = {}
    if not PRAXIS_PROFILE.is_file():
        errors.append(f"missing {relative(PRAXIS_PROFILE)}")
    if not PRAXIS_ROUTE_FILE.is_file():
        errors.append(f"missing {relative(PRAXIS_ROUTE_FILE)}")

    profile: dict[str, Any] = {}
    if not errors:
        try:
            profile = praxis_profile(strict=True)
        except Exception as exc:
            errors.append(str(exc))
        if profile.get("schema_version") != 1:
            errors.append("praxis profile schema_version must be 1")
        if profile.get("status") != "complete":
            errors.append("praxis profile status must be complete")
        layers = profile.get("layers", {})
        for layer in REQUIRED_LAYERS:
            if layer not in layers:
                errors.append(f"missing praxis layer: {layer}")
        milestone_ids = {milestone.get("id") for milestone in profile.get("milestone", [])}
        for milestone in {"M1", "M2", "M3", "M4"}:
            if milestone not in milestone_ids:
                errors.append(f"missing praxis milestone: {milestone}")
        control_plane = profile.get("control_plane", {})
        if control_plane.get("primary_command") != "task":
            errors.append("praxis control_plane.primary_command must be task")
        command_groups = set(control_plane.get("command_groups", []))
        for group in {"req", "project", "context", "gate", "delivery", "system"}:
            if group not in command_groups:
                errors.append(f"missing praxis command group: {group}")
    errors.extend(_workflow_command_contract_errors())
    try:
        workflow_payload = praxis_profile_payload(ROOT_DIR)
    except Exception as exc:
        errors.append(f"Praxis profile validation failed: {exc}")
    else:
        errors.extend(workflow_payload.get("issues", []))
    try:
        template_payload = template_report(ROOT_DIR)
    except Exception as exc:
        errors.append(f"Praxis template validation failed: {exc}")
    else:
        errors.extend(template_payload.get("issues", []))

    print(f"Praxis check: {'FAIL' if errors else 'PASS'}")
    print("Checked:")
    print(f"  - {relative(PRAXIS_PROFILE)}")
    print(f"  - {relative(PRAXIS_ROUTE_FILE)}")
    print(f"  - {CORE_FILE}")
    print(f"  - {ADAPTER_FILE}")
    if profile:
        print(f"Control plane: {profile.get('control_plane', {}).get('primary_command', '')}")
        print("Layers:")
        for layer in REQUIRED_LAYERS:
            print(f"  - {layer}: {profile.get('layers', {}).get(layer, {}).get('engineering_name', '')}")
    if workflow_payload:
        print(f"Praxis profile: {workflow_payload.get('status', '')}")
        print("Portable stages:")
        for stage in workflow_payload.get("portableStages", []):
            print(f"  - {stage}")
    if template_payload:
        print(f"Praxis templates: {template_payload.get('status', '')}")
        print(f"Rule templates checked: {template_payload.get('counts', {}).get('rules', 0)}")
        print(f"Skill templates checked: {template_payload.get('counts', {}).get('skills', 0)}")
    if errors:
        print("Errors:")
        for error in errors:
            print(f"  - {error}")
        return 1
    return 0


def praxis_index(scan: bool = False) -> Path:
    """Write a local project fact index for AI agents."""
    profile = praxis_profile()
    config = load_config()
    rules = rule_files()
    skills = skill_files()
    commands = praxis_contracts.praxis_commands()
    data = {
        "schemaVersion": 1,
        "praxis": {
            "name": profile.get("name", ""),
            "status": profile.get("status", ""),
            "baseline": profile.get("baseline", ""),
            "route": relative(PRAXIS_ROUTE_FILE),
        },
        "projectIndex": project_index_summary(ROOT_DIR, scan=scan),
        "extensions": discover_extensions(ROOT_DIR),
        "projects": config.get("projects", {}),
        "roles": ROLE_LABELS,
        "methodologyLayers": {
            layer: profile.get("layers", {}).get(layer, {}).get("engineering_name", "") for layer in REQUIRED_LAYERS
        },
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


def engineering_control_context() -> dict[str, str]:
    """Return the shared target-observation-feedback contract for AI packets."""
    return {
        "target": "requirement boundary and acceptance criteria",
        "observation": "context packet, code graph and evidence",
        "feedback": "tests, role verdicts and delivery recheck",
    }


def praxis_handoff_path(project: str, requirement_name: str, role: str) -> Path:
    """Return the default handoff packet path for a role."""
    return PRAXIS_HANDOFF_DIR / f"{safe_packet_name(project, requirement_name).removesuffix('.json')}-{role.strip().lower()}.json"


def praxis_lock_path(project: str, requirement_name: str, role: str) -> Path:
    """Return the default lock packet path for a role."""
    return PRAXIS_LOCK_DIR / f"{safe_packet_name(project, requirement_name).removesuffix('.json')}-{role.strip().lower()}.json"


def praxis_readiness_path(project: str, requirement_name: str) -> Path:
    """Return the default readiness report path for a project + requirement."""
    return PRAXIS_READINESS_DIR / f"{safe_packet_name(project, requirement_name).removesuffix('.json')}.json"


def praxis_verdict_role(role: str) -> str:
    """Normalize a CLI role key to its Praxis role label."""
    role_key = role.strip().lower()
    return VERDICT_ROLE_LABELS.get(role_key, role_key.title())


def praxis_verdict_path(project: str, requirement_name: str, role: str) -> Path:
    """Return the default machine-readable verdict path for a role."""
    role_key = role.strip().lower()
    return PRAXIS_VERDICT_DIR / f"{safe_packet_name(project, requirement_name).removesuffix('.json')}-{role_key}.json"


def praxis_validate_verdict_file(path: str | Path, role: str, project: str, requirement_name: str) -> int:
    """Validate a role verdict file and require a PASS conclusion."""
    verdict_path = Path(path)
    expected_role = praxis_verdict_role(role)
    errors: list[str] = []
    data: dict[str, Any] = {}

    if not verdict_path.is_file():
        errors.append(f"missing verdict file: {verdict_path}")
    else:
        try:
            loaded = json.loads(verdict_path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                errors.append("verdict file must contain a JSON object")
            else:
                data = loaded
        except json.JSONDecodeError as exc:
            errors.append(f"invalid JSON: {exc}")

    if data:
        if data.get("schemaVersion") != 1:
            errors.append("schemaVersion must be 1")
        if data.get("role") != expected_role:
            errors.append(f"role must be {expected_role}")
        if data.get("project") != project:
            errors.append(f"project must be {project}")
        if data.get("requirementName") != requirement_name:
            errors.append(f"requirementName must be {requirement_name}")
        if data.get("verdict") != "PASS":
            errors.append("verdict must be PASS")
        findings = data.get("findings")
        if not isinstance(findings, list):
            errors.append("findings must be a list")
        elif any(isinstance(item, dict) and item.get("severity") == "BLOCKER" for item in findings):
            errors.append("findings must not contain BLOCKER")
        for field in ["rules_checked", "manual_checks"]:
            value = data.get(field)
            if not isinstance(value, list) or not value:
                errors.append(f"{field} must be a non-empty list")
        if expected_role == "Quality":
            for field in ["evidence_checked", "compliance_checked"]:
                value = data.get(field)
                if not isinstance(value, list) or not value:
                    errors.append(f"{field} must be a non-empty list")

    print(f"Praxis {expected_role} verdict: {'FAIL' if errors else 'PASS'}")
    print(f"File: {verdict_path}")
    if errors:
        print("Errors:")
        for error in errors:
            print(f"  - {error}")
        return 1
    return 0


def praxis_import_verdict_file(path: str | Path, role: str, project: str, requirement_name: str) -> int:
    """Import an agent verdict into the default runtime verdict path and validate it."""
    source_path = Path(path)
    expected_role = praxis_verdict_role(role)
    if not source_path.is_file():
        print(f"error: missing verdict file: {source_path}", file=sys.stderr)
        return 1
    try:
        loaded = json.loads(source_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"error: invalid JSON: {exc}", file=sys.stderr)
        return 1
    if not isinstance(loaded, dict):
        print("error: verdict file must contain a JSON object", file=sys.stderr)
        return 1

    normalized = dict(loaded)
    normalized["schemaVersion"] = 1
    normalized["role"] = expected_role
    normalized["project"] = project
    normalized["requirementName"] = requirement_name
    normalized.setdefault("findings", [])

    PRAXIS_VERDICT_DIR.mkdir(parents=True, exist_ok=True)
    target_path = praxis_verdict_path(project, requirement_name, role)
    target_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Praxis verdict imported: {target_path}")
    return praxis_validate_verdict_file(target_path, role, project, requirement_name)


def praxis_require_verdict(role: str, project: str, requirement_name: str) -> int:
    """Require the default PASS verdict before protected Praxis actions."""
    return praxis_validate_verdict_file(praxis_verdict_path(project, requirement_name, role), role, project, requirement_name)


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
        "controlPlane": {
            "primaryCommand": praxis_profile().get("control_plane", {}).get("primary_command", "task"),
            "legacyCommandsAreAliases": praxis_profile().get("control_plane", {}).get("legacy_commands_are_aliases", True),
            "commandGroups": praxis_profile().get("control_plane", {}).get("command_groups", []),
        },
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


def praxis_write_role_handoff(project: str, requirement_name: str, role: str, summary: str, context_packet: Path) -> Path:
    """Write a machine-readable role handoff packet."""
    handoff = {
        "schemaVersion": 1,
        "role": praxis_verdict_role(role),
        "project": project,
        "requirementName": requirement_name,
        "summary": summary,
        "contextPacket": relative(context_packet),
        "verdictPath": relative(praxis_verdict_path(project, requirement_name, role)),
    }
    PRAXIS_HANDOFF_DIR.mkdir(parents=True, exist_ok=True)
    path = praxis_handoff_path(project, requirement_name, role)
    path.write_text(json.dumps(handoff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Praxis handoff: {path}")
    return path


def praxis_write_lock(
    project: str,
    requirement_name: str,
    role: str,
    write_scope: list[str],
    context_packet: Path,
) -> Path:
    """Write a single-writer lock packet for a role domain and scope."""
    lock = {
        "schemaVersion": 1,
        "role": praxis_verdict_role(role),
        "project": project,
        "requirementName": requirement_name,
        "policy": "single-writer",
        "writeScope": write_scope,
        "contextPacket": relative(context_packet),
    }
    PRAXIS_LOCK_DIR.mkdir(parents=True, exist_ok=True)
    path = praxis_lock_path(project, requirement_name, role)
    path.write_text(json.dumps(lock, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Praxis lock: {path}")
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
    profile = praxis_profile()
    req_dir = find_requirement_dir(config, requirement_name)
    project_data = config.get("projects", {}).get(project, {})
    quality_verdict = praxis_verdict_path(project, requirement_name, "quality")
    delivery_verdict = praxis_verdict_path(project, requirement_name, "delivery")
    packet = {
        "schemaVersion": 1,
        "project": project,
        "requirementName": requirement_name,
        "controlPlane": {
            "primaryCommand": profile.get("control_plane", {}).get("primary_command", "task"),
            "legacyCommandsAreAliases": profile.get("control_plane", {}).get("legacy_commands_are_aliases", True),
            "commandGroups": profile.get("control_plane", {}).get("command_groups", []),
        },
        "engineeringControl": engineering_control_context(),
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
        "methodology": {
            layer: profile.get("layers", {}).get(layer, {}).get("engineering_name", "") for layer in REQUIRED_LAYERS
        },
        "roles": ROLE_LABELS,
        "roleVerdicts": {
            "quality": {
                "role": "Quality",
                "path": relative(quality_verdict),
                "requiredBefore": ["commit-split", "deliver", "cleanup"],
                "validateCommand": (
                    praxis_contracts.praxis_usage(
                        f"gate validate-verdict quality {project} {requirement_name} {relative(quality_verdict)}"
                    )
                ),
                "importCommand": (
                    praxis_contracts.praxis_usage(
                        f"gate import-verdict quality {project} {requirement_name} <agent-output-json>"
                    )
                ),
            },
            "delivery": {
                "role": "Delivery",
                "path": relative(delivery_verdict),
                "requiredBefore": ["deliver", "cleanup"],
                "validateCommand": (
                    praxis_contracts.praxis_usage(
                        f"gate validate-verdict delivery {project} {requirement_name} {relative(delivery_verdict)}"
                    )
                ),
                "importCommand": (
                    praxis_contracts.praxis_usage(
                        f"gate import-verdict delivery {project} {requirement_name} <agent-output-json>"
                    )
                ),
            },
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
            "quality-verdict-json-required-before-commit-delivery-cleanup",
            "delivery-verdict-json-required-before-deliver-cleanup",
        ],
        "nextCommands": [
            praxis_contracts.praxis_usage(f"context --brief {project} {requirement_name}"),
            praxis_contracts.praxis_usage(f"context {project} {requirement_name}"),
            praxis_contracts.praxis_usage(f"project preflight {project} {requirement_name}"),
            praxis_contracts.praxis_usage(f"gate ready {project} {requirement_name}"),
            praxis_contracts.praxis_usage(f"gate ready-all {requirement_name}"),
            praxis_contracts.praxis_usage(f"delivery precheck-all {requirement_name}"),
            praxis_contracts.praxis_usage(
                f"gate validate-verdict quality {project} {requirement_name} {relative(quality_verdict)}"
            ),
            praxis_contracts.praxis_usage(f"gate import-verdict quality {project} {requirement_name} <agent-output-json>"),
            praxis_contracts.praxis_usage(
                f"gate validate-verdict delivery {project} {requirement_name} {relative(delivery_verdict)}"
            ),
            praxis_contracts.praxis_usage(f"gate import-verdict delivery {project} {requirement_name} <agent-output-json>"),
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


def praxis_write_delivery_precheck_packet(requirement_name: str, projects: list[str]) -> Path:
    """Write the parallel closeout dispatch packet for the main conversation."""
    dispatch = [
        {
            "role": "quality",
            "project": project,
            "command": f"quality: {project}",
            "expectedVerdictImport": (
                f"task gate -- import-verdict quality {project} {requirement_name} <agent-output-json>"
            ),
        }
        for project in projects
    ]
    dispatch.append(
        {
            "role": "delivery-precheck",
            "project": "all",
            "command": "delivery-precheck",
            "checks": [f"task delivery -- status {project} {requirement_name}" for project in projects],
        }
    )
    packet = {
        "schemaVersion": 1,
        "requirementName": requirement_name,
        "engineeringControl": engineering_control_context(),
        "projects": projects,
        "parallelDispatch": dispatch,
        "nextCommands": [
            f"task gate -- ready-all {requirement_name}",
            f"task delivery -- commit-split-all {requirement_name} <production-message>",
            f"task delivery -- deliver-all {requirement_name}",
            f"task delivery -- cleanup-all {requirement_name}",
        ],
    }
    target_dir = PRAXIS_CONTEXT_DIR.parent / "delivery-precheck"
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{safe_path_leaf(requirement_name)}.json"
    path.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Praxis delivery precheck: {path}")
    return path


def praxis_formalism_check() -> int:
    """Check for obvious workflow formalism and unresolved hardening records."""
    errors: list[str] = []
    warnings: list[str] = []
    pending_items = pending_todo_lines()
    if pending_items:
        warnings.append(f"todo.md has {len(pending_items)} pending hardening item(s)")
    if PRAXIS_ROUTE_FILE.is_file():
        route_text = PRAXIS_ROUTE_FILE.read_text(encoding="utf-8")
        if not re.search(r"^#{2,4}\s+分阶段(实施|执行|完成状态)", route_text, re.MULTILINE):
            errors.append("Praxis route file has no staged implementation section")

    print(f"Praxis formalism check: {'FAIL' if errors else 'PASS'}")
    if errors:
        print("Findings:")
        for error in errors:
            print(f"  - {error}")
        return 1
    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"  - {warning}")
        return 0
    print("Findings: none")
    return 0


def praxis_evolve_propose() -> Path:
    """Write controlled-evolution proposals from current feedback and route state."""
    pending = pending_todo_lines()
    proposals = []
    if pending:
        for index, line in enumerate(pending, start=1):
            proposals.append(
                {
                    "id": f"todo-{index}",
                    "source": "todo.md",
                    "problem": line.removeprefix("- [待固化] ").strip(),
                    "requiredPath": ["rule", "skill", "script-or-template", "regression-test", "todo-cleanup"],
                    "applyPolicy": "proposal-only",
                }
            )
    else:
        proposals.append(
            {
                "id": "monitor-formalism",
                "source": "praxis formalism-check",
                "problem": "No pending hardening item; continue checking that workflow steps produce evidence instead of empty ritual.",
                "requiredPath": ["observe", "threshold", "proposal"],
                "applyPolicy": "proposal-only",
            }
        )

    data = {
        "schemaVersion": 1,
        "policy": "controlled-evolution",
        "canApplyAutomatically": False,
        "proposals": proposals,
    }
    PRAXIS_DIR.mkdir(parents=True, exist_ok=True)
    PRAXIS_PROPOSALS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Evolution proposals: {PRAXIS_PROPOSALS_FILE}")
    return PRAXIS_PROPOSALS_FILE


def praxis_runtime_evaluation(benchmark: bool = False) -> Path:
    """Evaluate uv+Python versus Bun+TypeScript for the Praxis control plane."""
    data = {
        "schemaVersion": 1,
        "recommendation": "hybrid-python-core-bun-ts-adapters",
        "benchmarkRequested": benchmark,
        "evaluated": ["uv-python", "bun-typescript"],
        "detected": {
            "python": shutil.which("python3") or "",
            "uv": shutil.which("uv") or "",
            "bun": shutil.which("bun") or "",
        },
        "criteria": [
            {
                "name": "local-availability",
                "uv-python": "Already required by existing workflow and tests.",
                "bun-typescript": "Useful when Bun is installed; current workflow still treats Bun as optional.",
            },
            {
                "name": "filesystem-git-docs-automation",
                "uv-python": "Best fit for current TOML/JSON/filesystem/Git orchestration with stdlib coverage.",
                "bun-typescript": "Viable, but would add a second required runtime for existing Python-heavy scripts.",
            },
            {
                "name": "frontend-node-analysis",
                "uv-python": "Can invoke tools but is weaker for TypeScript AST/package graph work.",
                "bun-typescript": "Best fit for Web/PDA package graph, TypeScript AST and frontend config analysis.",
            },
            {
                "name": "migration-risk",
                "uv-python": "Lowest risk because current verification and task dispatcher already run here.",
                "bun-typescript": "Full rewrite would be high churn before Praxis semantics are stable.",
            },
        ],
        "decisions": [
            {
                "decision": "keep-core-in-python",
                "scope": "Praxis control plane, Git/worktree, docs, JSON/TOML, guard, delivery and evidence indexing.",
                "reason": "Current workflow is already verified around uv+Python; replacing the core now would add churn without proving a larger control-plane gain.",
            },
            {
                "decision": "use-bun-ts-adapters",
                "scope": "Frontend/PDA package graph, TypeScript AST, route/component/API analysis.",
                "reason": "Bun+TypeScript gives better native leverage where the target projects are TypeScript/Vue/uni-app.",
            },
            {
                "decision": "revisit-after-praxis-control-plane-stabilizes",
                "scope": "Possible future CLI rewrite.",
                "reason": "A full TypeScript rewrite should be justified by measured speed, maintainability and context-reduction gains after Praxis semantics are in use.",
            },
        ],
    }
    PRAXIS_DIR.mkdir(parents=True, exist_ok=True)
    PRAXIS_RUNTIME_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Praxis runtime evaluation: {PRAXIS_RUNTIME_FILE}")
    return PRAXIS_RUNTIME_FILE
