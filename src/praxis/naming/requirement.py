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
