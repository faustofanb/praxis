from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

_REQUIREMENT_ID_PATTERN = re.compile(r"^REQ-\d{8}-\d{3}$")
_INVALID_PATH_CHARACTERS = frozenset('/\\:*?"<>|\0')
_WINDOWS_RESERVED_NAMES = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{number}" for number in range(1, 10)),
        *(f"LPT{number}" for number in range(1, 10)),
    }
)

REQUIREMENT_DOCUMENTS = {
    "overview": "00-需求总览.md",
    "original_request": "01-原始需求.md",
    "analysis": "02-调查分析.md",
    "plan": "03-实施计划.md",
    "progress": "04-执行进度.md",
    "decisions": "05-决策记录.md",
    "acceptance": "06-验收结论.md",
    "changes": "07-变更记录.md",
    "relations": "08-关联关系.yaml",
    "artifacts": "09-产出物清单.yaml",
    "events": "10-事件记录.jsonl",
}
LEGACY_REQUIREMENT_DOCUMENTS = {
    key: value.split("-", 1)[1] for key, value in REQUIREMENT_DOCUMENTS.items()
}


@dataclass(slots=True, frozen=True)
class RequirementPathPolicy:
    knowledge_root: Path

    def validate_requirement_id(self, value: str) -> None:
        if not _REQUIREMENT_ID_PATTERN.fullmatch(value):
            raise ValueError(f"非法需求编号：{value}")

    def validate_short_name(self, value: str) -> str:
        name = unicodedata.normalize("NFC", value.strip())
        if not 4 <= len(name) <= 24:
            raise ValueError("中文需求简称长度必须在4到24个字符之间")
        if any(character in _INVALID_PATH_CHARACTERS for character in name):
            raise ValueError("中文需求简称包含非法路径字符")
        if name.endswith((".", " ")):
            raise ValueError("中文需求简称不能以点或空格结尾")
        if name.upper() in _WINDOWS_RESERVED_NAMES:
            raise ValueError("中文需求简称与系统保留名称冲突")
        if sum("\u4e00" <= character <= "\u9fff" for character in name) < 2:
            raise ValueError("需求简称至少应包含两个汉字")
        return name

    def directory_name(self, requirement_id: str, short_name: str) -> str:
        self.validate_requirement_id(requirement_id)
        return f"{requirement_id}__{self.validate_short_name(short_name)}"

    def legacy_directory_name(self, requirement_id: str, short_name: str) -> str:
        self.validate_requirement_id(requirement_id)
        return f"{self.validate_short_name(short_name)}__{requirement_id}"

    def requirement_path(self, requirement_id: str, short_name: str) -> Path:
        self.validate_requirement_id(requirement_id)
        return (
            self.knowledge_root
            / "需求"
            / requirement_id[4:8]
            / requirement_id[8:10]
            / self.directory_name(requirement_id, short_name)
        )

    def legacy_requirement_path(self, requirement_id: str, short_name: str) -> Path:
        self.validate_requirement_id(requirement_id)
        return (
            self.knowledge_root
            / "需求"
            / requirement_id[4:8]
            / requirement_id[8:10]
            / self.legacy_directory_name(requirement_id, short_name)
        )

    def locate_requirement_path(self, requirement_id: str, short_name: str) -> Path:
        current = self.requirement_path(requirement_id, short_name)
        legacy = self.legacy_requirement_path(requirement_id, short_name)
        return current if current.exists() or not legacy.exists() else legacy

    def migrate_layout(self, requirement_id: str, short_name: str) -> tuple[Path, bool]:
        current = self.requirement_path(requirement_id, short_name)
        legacy = self.legacy_requirement_path(requirement_id, short_name)
        migrated = False
        if legacy.exists() and current.exists():
            raise FileExistsError(f"需求新旧目录同时存在：{legacy}，{current}")
        source_root = legacy if legacy.exists() else current
        migrations = []
        if source_root.exists():
            for key, target_name in REQUIREMENT_DOCUMENTS.items():
                source = source_root / LEGACY_REQUIREMENT_DOCUMENTS[key]
                target = source_root / target_name
                if not source.exists():
                    continue
                if target.exists() and source.read_bytes() != target.read_bytes():
                    raise FileExistsError(f"需求文档迁移冲突：{source}，{target}")
                migrations.append((source.name, target.name))
        if legacy.exists():
            legacy.rename(current)
            migrated = True
        if not current.exists():
            return current, migrated
        for source_name, target_name in migrations:
            source = current / source_name
            target = current / target_name
            if target.exists():
                source.unlink()
            else:
                source.rename(target)
            migrated = True
        return current, migrated


def requirement_document(key: str) -> str:
    return REQUIREMENT_DOCUMENTS[key]
