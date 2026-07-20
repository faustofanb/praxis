from __future__ import annotations

import re
from hashlib import sha256
from pathlib import Path

from praxis.documents.atomic_writer import atomic_write_text
from praxis.result import Result
from praxis.skills.registry import normalize_skill_content
from praxis.workspace.service import WorkspaceService, _array, _quote


class SkillImportService:
    def __init__(self, root: Path | str):
        self.root = Path(root)

    def import_legacy(self, source_root: Path | str, system_id: str) -> Result:
        source = Path(source_root).resolve()
        discovered = sorted(source.rglob("SKILL.md"))
        groups: dict[str, list[Path]] = {}
        contents: dict[str, str] = {}
        for path in discovered:
            content = path.read_text(encoding="utf-8")
            normalized = normalize_skill_content(content)
            digest = sha256(normalized.encode()).hexdigest()
            groups.setdefault(digest, []).append(path)
            contents.setdefault(digest, content)

        workspace = WorkspaceService(self.root).load()
        target_root = self.root / workspace["knowledge_root"] / "技能候选" / "导入"
        candidates = []
        for digest, paths in sorted(groups.items()):
            slug = _slug(paths[0].parent.name)
            capability_id = f"business.{system_id.replace('-', '_')}.{slug}"
            relative_sources = [str(path.relative_to(source)) for path in paths]
            metadata = "\n".join(
                (
                    f"capability_id = {_quote(capability_id)}",
                    'status = "pending-review"',
                    f"system_id = {_quote(system_id)}",
                    f"normalized_content_hash = {_quote(digest)}",
                    f"sources = {_array(relative_sources)}",
                    f"aliases = {_array([path.parent.name for path in paths])}",
                    'source_priority = "historical-skill-document"',
                    "",
                )
            )
            atomic_write_text(target_root / f"{capability_id}.toml", metadata)
            atomic_write_text(
                target_root / f"{capability_id}.md",
                f"# 导入技能候选：{capability_id}\n\n"
                "## 审核状态\n\n待人工审核，不会自动替换或删除旧技能。\n\n"
                "## 来源\n\n"
                + "\n".join(f"- `{item}`" for item in relative_sources)
                + "\n\n## 规范化内容\n\n"
                + contents[digest].strip()
                + "\n",
            )
            candidates.append(capability_id)
        duplicate_groups = sum(1 for paths in groups.values() if len(paths) > 1)
        return Result(
            True,
            data={
                "discovered": len(discovered),
                "candidates": len(candidates),
                "duplicate_groups": duplicate_groups,
                "capability_ids": candidates,
            },
        )


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")
    return normalized or "imported"
