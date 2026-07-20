from __future__ import annotations

import subprocess
from pathlib import Path

from praxis.integrations.ponytail import diff_warning
from praxis.integrations.process import ProcessRunner
from praxis.integrations.witr import WitrService
from praxis.portraits.service import PortraitService
from praxis.workspace.service import Project, WorkspaceService


def test_static_portrait_records_commands_and_branches_without_running_them(tmp_path: Path) -> None:
    repo = tmp_path / "backend"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "branch", "release/1.0"], cwd=repo, check=False, capture_output=True)
    (repo / "pom.xml").write_text("<project/>")
    (repo / "Dockerfile").write_text("FROM scratch")
    WorkspaceService(tmp_path).init(
        "demo",
        "ifc-manufacturing",
        "knowledge",
        [
            Project(
                "backend",
                "java-maven",
                "backend",
                "main",
                database_connections=("mom-dev",),
                deployment_commands=("mise run deploy",),
                template_branches=("template/base",),
            )
        ],
    )

    result = PortraitService(tmp_path).scan("backend")

    assert result.ok
    assert result.data["build_commands"] == ["mvn package"]
    assert result.data["test_commands"] == ["mvn test"]
    assert result.data["deployment_commands"] == ["mise run deploy", "docker build ."]
    assert result.data["database_connections"] == ["mom-dev"]
    assert result.data["template_branches"] == ["template/base"]
    assert result.data["scan_mode"] == "static"
    portrait = tmp_path / "knowledge" / "portraits" / "backend.md"
    assert portrait.exists()
    assert "type: SystemPortrait" in portrait.read_text()


def test_machine_protocol_bypasses_rtk_and_human_output_uses_it(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "{}", "")

    runner = ProcessRunner(tmp_path, run=run, rtk_available=lambda: True)
    runner.run(["git", "status"], machine_output=True)
    runner.run(["git", "status"], machine_output=False)
    assert calls == [["git", "status"], ["rtk", "git", "status"]]


def test_witr_requires_explicit_runtime_diagnostics(tmp_path: Path) -> None:
    service = WitrService(tmp_path)
    blocked = service.diagnose([], explicit=False)
    assert not blocked.ok
    assert blocked.code == "WITR_EXPLICIT_REQUIRED"


def test_witr_explicit_diagnostics_use_machine_protocol(tmp_path: Path) -> None:
    calls = []

    def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, '{"processes": []}', "")

    result = WitrService(tmp_path, run=run).diagnose(["--port", "8080"], explicit=True)
    assert result.ok and result.data == {"processes": []}
    assert calls == [["witr", "--port", "8080", "--json"]]


def test_ponytail_diff_warning_is_non_blocking() -> None:
    result = diff_warning(added_lines=900, deleted_lines=10, threshold=500)
    assert result.ok
    assert result.code == "PONYTAIL_DIFF_GROWTH"
