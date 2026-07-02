from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


ADAPTER_REPORT = ".praxis/out/adapter-plan.json"


def adapter_plan() -> dict[str, Any]:
    """Return optional adapter plan for orchestration, quality and build acceleration."""
    tools = [
        {
            "id": "dagger",
            "layer": "orchestration",
            "required": False,
            "officialUrl": "https://docs.dagger.io/",
            "templatePath": ".praxis/adapters/orchestration/dagger-module.py.tpl",
            "purpose": "Local/CI parity, programmable pipelines and cacheable workflow runs.",
        },
        {
            "id": "nx",
            "layer": "orchestration",
            "required": False,
            "officialUrl": "https://nx.dev/docs/features/ci-features/affected",
            "templatePath": ".praxis/adapters/orchestration/nx.json.tpl",
            "purpose": "Affected project calculation, task cache and parallel execution.",
        },
        {
            "id": "opa",
            "layer": "policy",
            "required": False,
            "officialUrl": "https://www.openpolicyagent.org/docs",
            "templatePath": ".praxis/policies/praxis.rego",
            "purpose": "Policy-as-code engine for structured Praxis gates.",
        },
        {
            "id": "conftest",
            "layer": "policy",
            "required": False,
            "officialUrl": "https://github.com/open-policy-agent/conftest",
            "templatePath": ".praxis/policies/conftest.md",
            "purpose": "Run Rego policy checks against local TOML/JSON/YAML configuration.",
        },
        {
            "id": "semgrep",
            "layer": "quality",
            "required": False,
            "officialUrl": "https://docs.semgrep.dev/",
            "templatePath": ".praxis/adapters/quality/semgrep.yml",
            "purpose": "Fast custom static rules for coding and workflow quality.",
        },
        {
            "id": "codeql",
            "layer": "quality",
            "required": False,
            "officialUrl": "https://docs.github.com/en/code-security/codeql-cli",
            "templatePath": ".praxis/adapters/quality/codeql-action.yml.tpl",
            "purpose": "Optional semantic analysis and SARIF output; GitHub Actions stays a template.",
        },
        {
            "id": "renovate",
            "layer": "dependency",
            "required": False,
            "officialUrl": "https://docs.renovatebot.com/",
            "templatePath": ".praxis/adapters/dependency/renovate.json.tpl",
            "purpose": "Optional dependency update automation after gates are stable.",
        },
        {
            "id": "mvnd",
            "layer": "build",
            "required": False,
            "officialUrl": "https://github.com/apache/maven-mvnd",
            "templatePath": ".praxis/adapters/build/mvnd.md",
            "purpose": "Optional Maven daemon acceleration for repeated Maven builds.",
        },
    ]
    return {
        "schemaVersion": 1,
        "generatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "status": "PASS",
        "policy": "all adapters are optional; task remains the only human entrypoint",
        "tools": tools,
    }


def write_adapter_plan(root: Path) -> Path:
    """Persist the adapter plan for agents and humans."""
    path = root / ADAPTER_REPORT
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(adapter_plan(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Praxis adapter plan: {path}")
    return path

