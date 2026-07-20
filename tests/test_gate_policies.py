from __future__ import annotations

from pathlib import Path

from praxis.domain.process import CommandIntent, ProcessRequest
from praxis.gates.policies import allowed_paths_gate, command_policy_gate, secret_gate


def test_allowed_paths_gate_blocks_parent_escape_and_forbidden_files() -> None:
    result = allowed_paths_gate(
        ["src/report.py", "../outside.py", "src/secrets.env"],
        ["src"],
        ["src/*.env"],
    )

    assert result.code == "GATE_PATH_OUT_OF_SCOPE"
    assert result.data["blocked_paths"] == ["../outside.py", "src/secrets.env"]


def test_command_policy_gate_requires_approval_for_external_writes(tmp_path: Path) -> None:
    request = ProcessRequest(
        ("dbx", "query"),
        tmp_path,
        CommandIntent.DATABASE_WRITE,
    )

    assert command_policy_gate(request, [tmp_path]).code == "GATE_APPROVAL_REQUIRED"


def test_secret_gate_blocks_private_keys() -> None:
    result = secret_gate({"config.txt": "-----BEGIN PRIVATE KEY-----\nsecret"})

    assert result.code == "GATE_SECRET_DETECTED"
