from __future__ import annotations

import hashlib
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Skill:
    id: str
    type: str
    version: str
    license: str
    source: str
    source_version: str
    risk: str
    context_budget: int
    required_tools: tuple[str, ...]
    triggers: tuple[str, ...]
    content_hash: str
    path: Path


class SkillRegistry:
    def __init__(self, root: Path | str):
        self.root = Path(root)

    @classmethod
    def bundled(cls) -> SkillRegistry:
        source_assets = Path(__file__).resolve().parents[3] / "assets" / "skills"
        packaged_assets = Path(__file__).resolve().parents[1] / "assets" / "skills"
        return cls(source_assets if source_assets.exists() else packaged_assets)

    def inspect(self, skill_id: str) -> Skill:
        matches = list(self.root.glob(f"*/{skill_id}/skill.toml"))
        if len(matches) != 1:
            raise KeyError(skill_id)
        metadata_path = matches[0]
        content_path = metadata_path.with_name("SKILL.md")
        raw = metadata_path.read_bytes() + b"\0" + content_path.read_bytes()
        payload: dict[str, Any] = tomllib.loads(metadata_path.read_text(encoding="utf-8"))
        return Skill(
            id=payload["id"],
            type=payload["type"],
            version=payload["version"],
            license=payload["license"],
            source=payload["source"],
            source_version=payload["source_version"],
            risk=payload["risk"],
            context_budget=payload["context_budget"],
            required_tools=tuple(payload["required_tools"]),
            triggers=tuple(payload["triggers"]),
            content_hash=hashlib.sha256(raw).hexdigest(),
            path=content_path,
        )

    def route(self, intent: str, *, budget: int = 2000) -> list[Skill]:
        normalized = intent.casefold()
        routed: list[Skill] = []
        used = 0
        for metadata in sorted(self.root.glob("*/*/skill.toml")):
            skill = self.inspect(metadata.parent.name)
            matches = any(trigger.casefold() in normalized for trigger in skill.triggers)
            if matches and used + skill.context_budget <= budget:
                routed.append(skill)
                used += skill.context_budget
        return routed

    def resource(self, uri: str) -> str:
        prefix = "praxis://skills/"
        if not uri.startswith(prefix):
            raise KeyError(uri)
        skill_type, skill_id = uri.removeprefix(prefix).split("/", 1)
        skill = self.inspect(skill_id)
        if skill.type != skill_type:
            raise KeyError(uri)
        return skill.path.read_text(encoding="utf-8")
