from __future__ import annotations

import hashlib
import os
from pathlib import Path

from praxis.skills.routing import NodeSkillRouter

_SKILL_MD = (
    "---\nname: demo-linked-skill\ndescription: 通过符号链接安装的技能。\n---\n\n# 测试\n"
)


def test_installed_skills_follows_directory_symlinks(tmp_path: Path, monkeypatch) -> None:
    real = tmp_path / "real-skills"
    skill_dir = real / "demo-linked-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(_SKILL_MD, encoding="utf-8")

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for root in ("codex", "agents", "claude", "skilldock"):
        (tmp_path / f".{root}" / "skills").mkdir(parents=True, exist_ok=True)
    # 符号链接技能放入被扫描的 .codex/skills 根内
    (tmp_path / ".codex" / "skills" / "demo-linked-skill").symlink_to(
        skill_dir, target_is_directory=True
    )

    installed = NodeSkillRouter._installed_skills()

    assert "demo-linked-skill" in installed
    assert installed["demo-linked-skill"]["content_hash"] == hashlib.sha256(
        _SKILL_MD.encode("utf-8")
    ).hexdigest()


def test_installed_skills_handles_symlink_cycles(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / ".codex" / "skills"
    root.mkdir(parents=True)
    a = root / "a"
    b = root / "b"
    a.mkdir()
    b.mkdir()
    # 循环符号链接：a -> b, b -> a
    (root / "loop1").symlink_to(a, target_is_directory=True)
    (root / "loop2").symlink_to(b, target_is_directory=True)
    (a / "SKILL.md").write_text(_SKILL_MD, encoding="utf-8")

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for other in ("agents", "claude", "skilldock"):
        (tmp_path / f".{other}" / "skills").mkdir(parents=True, exist_ok=True)

    installed = NodeSkillRouter._installed_skills()

    assert "demo-linked-skill" in installed
