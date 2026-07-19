from __future__ import annotations

from conftest import read_json, run_praxis


def test_cli_help_defaults_to_chinese():
    proc = run_praxis("--help")
    assert proc.returncode == 0
    assert "工作区" in proc.stdout
    assert "profile" in proc.stdout


def test_json_error_has_stable_english_code_and_chinese_message(tmp_path):
    proc = run_praxis("workspace", "inspect", "--json", cwd=tmp_path)
    assert proc.returncode != 0
    payload = read_json(proc)
    assert payload["ok"] is False
    assert payload["code"] == "WORKSPACE_NOT_FOUND"
    assert "未找到" in payload["message"]
    assert proc.stderr == ""
    assert list(tmp_path.iterdir()) == []


def test_doctor_json_reports_mise_without_workspace_dependency():
    proc = run_praxis("doctor", "--json")
    assert proc.returncode == 0
    payload = read_json(proc)
    assert payload["ok"] is True
    assert payload["command"] == "doctor"
    assert any(d["code"] == "MISE_STATUS" for d in payload["diagnostics"])
