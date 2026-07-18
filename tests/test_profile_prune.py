from __future__ import annotations

import importlib.util
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def load_sync_profile():
    spec = importlib.util.spec_from_file_location(
        "praxis_sync_profile_prune_test",
        PLUGIN_ROOT / "scripts" / "praxis_sync_profile.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sync_profile_prune_removes_stale_managed_files(tmp_path: Path) -> None:
    stale_extension = tmp_path / ".praxis/extensions/ifc-mom/stale.md"
    stale_script = tmp_path / "scripts/codex/stale.py"
    local_config = tmp_path / "praxis.projects.toml"
    for path in (stale_extension, stale_script, local_config):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("stale\n", encoding="utf-8")

    load_sync_profile().sync_profile(tmp_path, "ifc-mom", force=True, prune=True)

    assert not stale_extension.exists()
    assert not stale_script.exists()
    assert local_config.exists()
