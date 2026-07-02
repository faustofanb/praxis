from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from momlib import praxis as legacy
from momlib.context import worker_rule_skill_paths
from momlib.paths import ROOT_DIR
from momlib.praxis import (  # noqa: F401
    PRAXIS_CONTEXT_DIR,
    PRAXIS_PROFILE,
    REQUIRED_LAYERS,
    ROLE_LABELS,
    praxis_contracts,
    praxis_profile,
    relative,
    rule_files,
    skill_files,
)
from praxislib.config import load_config
from praxislib.project_index import discover_extensions, project_index_summary


PRAXIS_DIR = legacy.PRAXIS_DIR
PRAXIS_INDEX_FILE = legacy.PRAXIS_INDEX_FILE
PRAXIS_ROUTE_FILE = legacy.PRAXIS_ROUTE_FILE


def praxis_index(scan: bool = False) -> Path:
    """Write a generic Praxis project fact index."""
    profile = praxis_profile()
    config = load_config()
    rules = rule_files()
    skills = skill_files()
    commands = praxis_contracts.praxis_commands()
    data: dict[str, Any] = {
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
        "workerContexts": {
            project: worker_rule_skill_paths(project) for project in sorted(config.get("projects", {}))
        },
    }
    PRAXIS_DIR.mkdir(parents=True, exist_ok=True)
    PRAXIS_INDEX_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Praxis index: {PRAXIS_INDEX_FILE}")
    return PRAXIS_INDEX_FILE


def __getattr__(name: str) -> Any:
    """Keep compatibility for functions not yet moved out of momlib."""
    return getattr(legacy, name)
