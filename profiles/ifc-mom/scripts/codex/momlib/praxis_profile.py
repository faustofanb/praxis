from __future__ import annotations

import json
import time
import tomllib
from pathlib import Path
from typing import Any

from .paths import ROOT_DIR


CORE_FILE = ".praxis/core.toml"
ADAPTER_FILE = ".praxis/project-adapter.toml"
COMMANDS_FILE = ".praxis/commands.toml"
PROJECTS_FILE = "praxis.projects.toml"
REPORT_FILE = ".praxis/out/profile.json"


def read_toml(root: Path, relative: str) -> dict[str, Any]:
    """Read a TOML file below the supplied repository root."""
    with (root / relative).open("rb") as file:
        return tomllib.load(file)


def command_ids(root: Path) -> set[str]:
    """Return known command IDs from the command contract table."""
    payload = read_toml(root, COMMANDS_FILE)
    return {item["id"] for item in payload.get("command", []) if isinstance(item, dict) and isinstance(item.get("id"), str)}


def project_kinds(root: Path) -> set[str]:
    """Return project kind values from the Praxis project adapter registry."""
    project_file = PROJECTS_FILE if (root / PROJECTS_FILE).is_file() else ".praxis/projects.toml"
    if not (root / project_file).is_file():
        return set()
    payload = read_toml(root, project_file)
    projects = payload.get("projects", {})
    return {
        item.get("kind", "")
        for item in projects.values()
        if isinstance(item, dict) and isinstance(item.get("kind"), str) and item.get("kind")
    }


def _list_table(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = payload.get(key, [])
    return [item for item in value if isinstance(item, dict)]


def _table_keys(payload: dict[str, Any], key: str) -> list[str]:
    value = payload.get(key, {})
    return sorted(value.keys()) if isinstance(value, dict) else []


def _extension_project_kinds(root: Path) -> set[str]:
    extension_root = root / ".praxis" / "extensions"
    if not extension_root.is_dir():
        return set()
    kinds: set[str] = set()
    for manifest in sorted(extension_root.glob("*/extension.toml")):
        try:
            extension = read_toml(root, manifest.relative_to(root).as_posix())
        except Exception:
            continue
        adapter = extension.get("adapter")
        if not isinstance(adapter, str) or not (root / adapter).is_file():
            continue
        try:
            adapter_payload = read_toml(root, adapter)
        except Exception:
            continue
        kinds.update(_table_keys(adapter_payload, "project_kinds"))
    return kinds


def _string_set(payload: dict[str, Any], key: str) -> set[str]:
    value = payload.get(key, [])
    return {item for item in value if isinstance(item, str)}


def validate_praxis_profile(root: Path, core: dict[str, Any], adapter: dict[str, Any]) -> list[str]:
    """Validate the portable Praxis core and project adapter boundary."""
    issues: list[str] = []
    known_commands = command_ids(root)

    if core.get("schema_version") != 1:
        issues.append(f"{CORE_FILE} schema_version must be 1")
    if adapter.get("schema_version") != 1:
        issues.append(f"{ADAPTER_FILE} schema_version must be 1")

    platform = core.get("platform", {})
    if not isinstance(platform, dict) or platform.get("primary_command") != "task":
        issues.append(f"{CORE_FILE} platform.primary_command must be task")

    adapter_meta = adapter.get("adapter", {})
    if not isinstance(adapter_meta, dict) or adapter_meta.get("shared_core") != CORE_FILE:
        issues.append(f"{ADAPTER_FILE} adapter.shared_core must be {CORE_FILE}")

    portability = core.get("portability", {})
    if not isinstance(portability, dict) or portability.get("windows_supported") is not True:
        issues.append(f"{CORE_FILE} portability.windows_supported must be true")

    for stage in _list_table(core, "stage"):
        stage_id = stage.get("id", "<unknown>")
        for command_id in stage.get("commands", []):
            if command_id not in known_commands:
                issues.append(f"{CORE_FILE} stage {stage_id} references unknown command {command_id}")

    for lane, lane_data in core.get("risk_lane", {}).items():
        if not isinstance(lane_data, dict):
            continue
        for command_id in lane_data.get("commands", []):
            if command_id not in known_commands:
                issues.append(f"{CORE_FILE} risk_lane {lane} references unknown command {command_id}")

    for tool in _list_table(core, "tool_candidate"):
        tool_id = tool.get("id", "<unknown>")
        official_url = tool.get("official_url")
        if not isinstance(official_url, str) or not official_url.startswith("https://"):
            issues.append(f"{CORE_FILE} tool_candidate {tool_id} must provide https official_url")

    path_policy = adapter.get("path_policy", {})
    optional_external = _string_set(path_policy, "optional_external") if isinstance(path_policy, dict) else set()
    paths = adapter.get("paths", {})
    if not isinstance(paths, dict):
        issues.append(f"{ADAPTER_FILE} paths must be a table")
        paths = {}
    for label, relative in paths.items():
        if not isinstance(relative, str):
            issues.append(f"{ADAPTER_FILE} paths.{label} must be a string")
        elif label not in optional_external and not (root / relative).exists():
            issues.append(f"{ADAPTER_FILE} paths.{label} does not exist: {relative}")
    for label in sorted(optional_external - set(paths.keys())):
        issues.append(f"{ADAPTER_FILE} path_policy.optional_external references unknown path {label}")

    configured_kinds = set(_table_keys(adapter, "project_kinds")) | _extension_project_kinds(root)
    missing_kinds = sorted(project_kinds(root) - configured_kinds)
    for kind in missing_kinds:
        issues.append(f"{ADAPTER_FILE} missing project_kinds.{kind}")

    for key in ("rule_paths", "skill_paths"):
        for relative in adapter.get(key, []):
            if not isinstance(relative, str):
                issues.append(f"{ADAPTER_FILE} {key} entry must be a string")
            elif not (root / relative).exists():
                issues.append(f"{ADAPTER_FILE} {key} missing path: {relative}")

    extensions_dir = root / ".praxis" / "extensions"
    if extensions_dir.is_dir():
        for manifest in sorted(extensions_dir.glob("*/extension.toml")):
            try:
                extension = read_toml(root, manifest.relative_to(root).as_posix())
            except Exception as exc:
                issues.append(f"{manifest.relative_to(root).as_posix()} cannot be read: {exc}")
                continue
            extension_id = extension.get("id")
            if not isinstance(extension_id, str) or not extension_id:
                issues.append(f"{manifest.relative_to(root).as_posix()} id must be a non-empty string")
            for key in ("adapter", "manifest", "rules", "skills", "templates"):
                value = extension.get(key)
                if isinstance(value, str) and not (root / value).exists():
                    issues.append(f"{manifest.relative_to(root).as_posix()} {key} path does not exist: {value}")

    return issues


def praxis_profile_payload(root: Path) -> dict[str, Any]:
    """Build a normalized Praxis profile payload for humans and future tool adapters."""
    core = read_toml(root, CORE_FILE)
    adapter = read_toml(root, ADAPTER_FILE)
    issues = validate_praxis_profile(root, core, adapter)
    stages = _list_table(core, "stage")
    tools = _list_table(core, "tool_candidate")

    return {
        "schemaVersion": 1,
        "generatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "status": "PASS" if not issues else "FAIL",
        "core": {
            "path": CORE_FILE,
            "platform": core.get("platform", {}),
        },
        "adapter": {
            "path": ADAPTER_FILE,
            "workspace": adapter.get("adapter", {}).get("workspace", ""),
            "optionalExternalPaths": sorted(
                _string_set(adapter.get("path_policy", {}), "optional_external")
                if isinstance(adapter.get("path_policy", {}), dict)
                else []
            ),
        },
        "portableStages": sorted(stage.get("id", "") for stage in stages if stage.get("portable") is True),
        "projectKinds": _table_keys(adapter, "project_kinds"),
        "toolCandidates": sorted(tool.get("id", "") for tool in tools if isinstance(tool.get("id"), str)),
        "portability": {
            "windowsSupported": core.get("portability", {}).get("windows_supported") is True
            if isinstance(core.get("portability", {}), dict)
            else False,
            "pathStyle": core.get("portability", {}).get("path_style", "")
            if isinstance(core.get("portability", {}), dict)
            else "",
        },
        "issues": issues,
    }


def write_praxis_profile_report(root: Path = ROOT_DIR) -> Path:
    """Write the normalized Praxis profile report and print a compact summary."""
    payload = praxis_profile_payload(root)
    report_path = root / REPORT_FILE
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Praxis profile: {payload['status']}")
    print(f"  report: {report_path}")
    print(f"  portable stages: {', '.join(payload['portableStages'])}")
    print(f"  project kinds: {', '.join(payload['projectKinds'])}")
    print(f"  tool candidates: {', '.join(payload['toolCandidates'])}")
    if payload["issues"]:
        print("Issues:")
        for issue in payload["issues"]:
            print(f"  - {issue}")
    return report_path
