from __future__ import annotations

from pathlib import Path

from conftest import read_json, run_praxis


def list_files(root: Path):
    return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())


def test_workspace_init_writes_only_allowed_minimal_files(tmp_path):
    proc = run_praxis("workspace", "init", "--profile", "base", "--json", cwd=tmp_path)
    assert proc.returncode == 0
    files = list_files(tmp_path)
    assert files == [".praxis/workspace.toml"]
    assert not any(path.endswith(".py") for path in files)


def test_workspace_init_refuses_conflicting_profile_without_overwrite(tmp_path):
    run_praxis("workspace", "init", "--profile", "base", "--json", cwd=tmp_path)
    same = run_praxis("workspace", "init", "--profile", "base", "--json", cwd=tmp_path)
    conflict = run_praxis("workspace", "init", "--profile", "mom", "--json", cwd=tmp_path)
    assert same.returncode == 0
    assert conflict.returncode != 0
    assert read_json(conflict)["code"] == "WORKSPACE_CONFLICT"


def test_workspace_init_omitted_projects_means_no_change(tmp_path):
    (tmp_path / "app").mkdir()
    run_praxis(
        "workspace",
        "init",
        "--profile",
        "base",
        "--project",
        "app:java-maven:app",
        "--json",
        cwd=tmp_path,
    )
    rerun = run_praxis("workspace", "init", "--profile", "base", "--json", cwd=tmp_path)
    assert rerun.returncode == 0
    assert read_json(rerun)["data"]["projects"]["app"]["path"] == "app"


def test_workspace_check_rebuilds_generated_cache_and_preserves_facts(tmp_path):
    run_praxis("workspace", "init", "--profile", "base", "--json", cwd=tmp_path)
    workspace_file = tmp_path / ".praxis" / "workspace.toml"
    before = workspace_file.read_text()
    assert not (tmp_path / ".praxis" / "cache" / "resolved-profile.json").exists()
    proc = run_praxis("workspace", "check", "--json", cwd=tmp_path)
    assert proc.returncode == 0
    payload = read_json(proc)
    assert any(d["code"] == "CACHE_REBUILT" for d in payload["diagnostics"])
    assert workspace_file.read_text() == before


def test_workspace_check_rejects_unreadable_state_json(tmp_path):
    run_praxis("workspace", "init", "--profile", "base", "--json", cwd=tmp_path)
    bad = tmp_path / ".praxis" / "state" / "tasks" / "bad.json"
    bad.parent.mkdir(parents=True)
    bad.write_text("{not-json")
    proc = run_praxis("workspace", "check", "--json", cwd=tmp_path)
    assert proc.returncode != 0
    payload = read_json(proc)
    assert payload["code"] == "STATE_JSON_INVALID"
    assert payload["details"]["path"] == ".praxis/state/tasks/bad.json"


def test_runtime_ignores_workspace_shared_static_rules_and_old_scripts(tmp_path):
    run_praxis("workspace", "init", "--profile", "base", "--json", cwd=tmp_path)
    (tmp_path / ".praxis" / "rules").mkdir()
    (tmp_path / ".praxis" / "rules" / "global.md").write_text("SHOULD_NOT_READ")
    (tmp_path / "scripts" / "praxis").mkdir(parents=True)
    (tmp_path / "scripts" / "praxis" / "task.py").write_text("raise SystemExit('SHOULD_NOT_RUN')")
    proc = run_praxis("profile", "resolve", "base", "--json", cwd=tmp_path)
    assert proc.returncode == 0
    assert "SHOULD_NOT" not in proc.stdout + proc.stderr


def test_workspace_facts_are_relative_after_move(tmp_path):
    project = tmp_path / "app"
    project.mkdir()
    run_praxis(
        "workspace",
        "init",
        "--profile",
        "base",
        "--project",
        "app:java-maven:app",
        "--json",
        cwd=tmp_path,
    )
    moved = tmp_path.parent / (tmp_path.name + "-moved")
    tmp_path.rename(moved)
    proc = run_praxis("project", "inspect", "app", "--json", cwd=moved)
    assert proc.returncode == 0
    assert read_json(proc)["data"]["path"] == "app"
