from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from praxis.integrations.ponytail import diff_warning
from praxis.integrations.process import ProcessRunner
from praxis.integrations.witr import WitrService
from praxis.portraits.service import PortraitService
from praxis.result import Result
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
                database_connections=("dbx://mom-dev",),
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
    assert result.data["database_connections"] == ["dbx://mom-dev"]
    assert result.data["template_branches"] == ["template/base"]
    assert result.data["scan_mode"] == "incremental"
    portrait = tmp_path / "knowledge" / "系统画像" / "demo" / "backend.md"
    assert portrait.exists()
    content = portrait.read_text()
    assert "类型: 系统画像" in content
    assert "## 仓库范围与结构" in content
    assert "## 工程入口与接口面" in content
    assert "## 数据与配置资产" in content
    assert "## 质量与交付命令" in content
    assert result.data["repository"]["file_count"] >= 2
    assert "pom.xml" in result.data["entrypoints"]
    assert "Dockerfile" in result.data["data_and_config_assets"]
    assert PortraitService(tmp_path).scan("backend").code == "PORTRAIT_UNCHANGED"


def test_process_runs_once_keeps_redacted_raw_log_and_compresses_human_output(
    tmp_path: Path,
) -> None:
    calls: list[list[str]] = []

    def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, 'password="secret"\nverbose output', "")

    runner = ProcessRunner(
        tmp_path,
        run=run,
        rtk_available=lambda: True,
        compress=lambda output, cwd: "compressed output",
    )
    result = runner.run(["git", "status"], machine_output=False)

    assert calls == [["git", "status"]]
    assert result.data["stdout"] == "compressed output"
    raw_log = Path(result.data["raw_log"])
    assert raw_log.is_file()
    assert "secret" not in raw_log.read_text()
    assert "[已脱敏]" in raw_log.read_text()


def test_machine_protocol_bypasses_rtk_filter(tmp_path: Path) -> None:
    def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, "{}", "")

    runner = ProcessRunner(
        tmp_path,
        run=run,
        rtk_available=lambda: True,
        compress=lambda output, cwd: (_ for _ in ()).throw(AssertionError("不应压缩机器输出")),
    )

    result = runner.run(["git", "status"], machine_output=True)

    assert result.data["stdout"] == "{}"


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


def test_explicit_runtime_portrait_uses_witr_and_redacts_secrets(tmp_path: Path) -> None:
    repo = tmp_path / "backend"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='demo'\n")
    WorkspaceService(tmp_path).init(
        "demo",
        "演示工作空间",
        projects=[Project("backend", "python", "backend", "main")],
    )

    class FakeWitr:
        def diagnose(self, arguments: list[str], *, explicit: bool):
            assert arguments == ["--port", "8080"]
            assert explicit
            return Result(
                True,
                data={"processes": [{"name": "python", "environment": {"TOKEN": "secret"}}]},
            )

    result = PortraitService(tmp_path, witr=FakeWitr()).scan(
        "backend", runtime_arguments=["--port", "8080"]
    )

    assert result.ok
    assert result.data["runtime_scanned"] is True
    assert result.data["runtime"]["processes"][0]["environment"]["TOKEN"] == "[已脱敏]"


def test_portrait_verify_rejects_non_dbx_connection_reference(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="dbx://"):
        WorkspaceService(tmp_path).init(
            "demo",
            "演示工作空间",
            projects=[
                Project(
                    "backend",
                    "python",
                    "backend",
                    "main",
                    database_connections=("password@localhost",),
                )
            ],
        )


def test_ponytail_diff_warning_is_non_blocking() -> None:
    result = diff_warning(added_lines=900, deleted_lines=10, threshold=500)
    assert result.ok
    assert result.code == "PONYTAIL_DIFF_GROWTH"
