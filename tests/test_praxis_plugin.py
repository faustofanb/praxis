from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def write_valid_workspace(root: Path) -> None:
    (root / ".praxis" / "contracts" / "agents").mkdir(parents=True)
    (root / ".praxis").mkdir(exist_ok=True)
    (root / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    (root / "praxis.toml").write_text(
        'schema_version = 1\nproject_index = "praxis.projects.toml"\n',
        encoding="utf-8",
    )
    (root / "praxis.projects.toml").write_text(
        """
version = 1
worktreeRoot = ".worktrees"

[projects.web]
label = "Web"
path = "apps/web"
kind = "pnpm-web"
defaultBranch = "local"
upstreamBranch = "main"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (root / ".praxis" / "core.toml").write_text("schema_version = 1\n", encoding="utf-8")
    (root / ".praxis" / "project-adapter.toml").write_text(
        "schema_version = 1\n", encoding="utf-8"
    )
    (root / ".praxis" / "contracts" / "agents" / "turn.schema.json").write_text(
        '{"schemaVersion": 1}\n',
        encoding="utf-8",
    )


def test_check_workspace_reads_project_branch_config_from_workspace(tmp_path: Path) -> None:
    write_valid_workspace(tmp_path)
    check_workspace = load_module(
        "praxis_check_workspace",
        PLUGIN_ROOT / "scripts" / "praxis_check_workspace.py",
    )

    report = check_workspace.analyze_workspace(tmp_path)

    assert report.ok is True
    assert report.projects == [
        {
            "name": "web",
            "path": "apps/web",
            "kind": "pnpm-web",
            "defaultBranch": "local",
            "upstreamBranch": "main",
        }
    ]


def test_check_workspace_reports_missing_required_files(tmp_path: Path) -> None:
    check_workspace = load_module(
        "praxis_check_workspace",
        PLUGIN_ROOT / "scripts" / "praxis_check_workspace.py",
    )

    report = check_workspace.analyze_workspace(tmp_path)

    assert report.ok is False
    assert "AGENTS.md" in report.missing_files
    assert "praxis.projects.toml" in report.missing_files


def test_init_workspace_renders_thin_project_templates(tmp_path: Path) -> None:
    init_workspace = load_module(
        "praxis_init_workspace",
        PLUGIN_ROOT / "scripts" / "praxis_init_workspace.py",
    )

    written = init_workspace.initialize_workspace(tmp_path, name="Demo Workspace")

    assert "AGENTS.md" in written
    assert "praxis.toml" in written
    assert "praxis.projects.toml" in written
    projects_text = (tmp_path / "praxis.projects.toml").read_text(encoding="utf-8")
    assert 'defaultBranch = "main"' in projects_text
    assert 'defaultBranch = "local"' not in projects_text


def test_skill_references_exist_and_are_linked() -> None:
    skill_text = (PLUGIN_ROOT / "skills" / "praxis-workflow" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    expected_references = {
        "startup-gate.md",
        "worktree.md",
        "command-contract.md",
        "project-config-boundary.md",
        "verification-closeout.md",
    }

    for reference in expected_references:
        assert reference in skill_text
        assert (PLUGIN_ROOT / "skills" / "praxis-workflow" / "references" / reference).is_file()
