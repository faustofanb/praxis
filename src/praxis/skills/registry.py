from __future__ import annotations

import hashlib
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from praxis.result import Result


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
    normalized_content_hash: str
    path: Path
    systems: tuple[str, ...] = ()
    business_domains: tuple[str, ...] = ()
    repository_roles: tuple[str, ...] = ()
    stages: tuple[str, ...] = ()
    artifact_types: tuple[str, ...] = ()
    denied_risks: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SkillRoutingContext:
    system_id: str = ""
    business_domains: tuple[str, ...] = ()
    repository_role: str = ""
    stage: str = ""
    agent_role: str = ""
    risks: tuple[str, ...] = ()
    artifact_types: tuple[str, ...] = ()
    token_budget: int = 2_000


class SkillRegistry:
    def __init__(self, root: Path | str):
        self.root = Path(root)

    @classmethod
    def bundled(cls) -> SkillRegistry:
        source_skills = Path(__file__).resolve().parents[3] / "skills"
        packaged_skills = Path(__file__).resolve().parents[1] / "bundled_skills"
        return cls(source_skills if source_skills.exists() else packaged_skills)

    def inspect(self, skill_id: str) -> Skill:
        matches = list(self.root.glob(f"{skill_id}/skill.toml"))
        matches.extend(self.root.glob(f"*/{skill_id}/skill.toml"))
        if len(matches) != 1:
            raise KeyError(skill_id)
        metadata_path = matches[0]
        content_path = metadata_path.with_name("SKILL.md")
        raw = metadata_path.read_bytes() + b"\0" + content_path.read_bytes()
        content = content_path.read_text(encoding="utf-8")
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
            normalized_content_hash=hashlib.sha256(normalize_skill_content(content).encode()).hexdigest(),
            path=content_path,
            systems=tuple(payload.get("systems", [])),
            business_domains=tuple(payload.get("business_domains", [])),
            repository_roles=tuple(payload.get("repository_roles", [])),
            stages=tuple(payload.get("stages", [])),
            artifact_types=tuple(payload.get("artifact_types", [])),
            denied_risks=tuple(payload.get("denied_risks", [])),
        )

    def all(self) -> list[Skill]:
        return [self.inspect(path.parent.name) for path in self._metadata_paths()]

    def route(self, intent: str, *, budget: int = 2000) -> list[Skill]:
        normalized = intent.casefold()
        routed: list[Skill] = []
        used = 0
        for metadata in self._metadata_paths():
            skill = self.inspect(metadata.parent.name)
            matches = any(trigger.casefold() in normalized for trigger in skill.triggers)
            if matches and used + skill.context_budget <= budget:
                routed.append(skill)
                used += skill.context_budget
        return routed

    def route_context(self, context: SkillRoutingContext) -> list[Skill]:
        scored: list[tuple[int, Skill]] = []
        for skill in self.all():
            if set(context.risks) & set(skill.denied_risks):
                continue
            score = 0
            if context.system_id and context.system_id in skill.systems:
                score += 40
            score += 30 * bool(set(context.business_domains) & set(skill.business_domains))
            score += 15 * bool(
                context.repository_role and context.repository_role in skill.repository_roles
            )
            score += 10 * bool(context.stage and context.stage in skill.stages)
            score += 5 * bool(set(context.artifact_types) & set(skill.artifact_types))
            if score:
                scored.append((score, skill))
        selected: list[Skill] = []
        used = 0
        for _, skill in sorted(scored, key=lambda item: (-item[0], item[1].id)):
            if used + skill.context_budget <= context.token_budget:
                selected.append(skill)
                used += skill.context_budget
        return selected

    def search(self, query: str) -> list[Skill]:
        normalized = query.casefold()
        matches = []
        for skill in self.all():
            haystack = " ".join(
                (skill.id, *skill.triggers, skill.path.read_text(encoding="utf-8"))
            ).casefold()
            if normalized in haystack:
                matches.append(skill)
        return matches

    def _metadata_paths(self) -> list[Path]:
        return sorted((*self.root.glob("*/skill.toml"), *self.root.glob("*/*/skill.toml")))

    def verify(self) -> Result:
        skills = self.all()
        ids = [skill.id for skill in skills]
        duplicate_ids = sorted({skill_id for skill_id in ids if ids.count(skill_id) > 1})
        invalid = [
            skill.id
            for skill in skills
            if not all((skill.version, skill.license, skill.source, skill.source_version))
        ]
        ok = not duplicate_ids and not invalid
        return Result(
            ok,
            "OK" if ok else "SKILL_CATALOG_INVALID",
            data={"count": len(skills), "duplicate_ids": duplicate_ids, "invalid": invalid},
        )

    def duplicates(self) -> Result:
        grouped: dict[str, list[str]] = {}
        for skill in self.all():
            grouped.setdefault(skill.normalized_content_hash, []).append(skill.id)
        groups = sorted(sorted(ids) for ids in grouped.values() if len(ids) > 1)
        return Result(True, data={"groups": groups, "action": "review-only"})

    def resource(self, uri: str) -> str:
        prefix = "praxis://skills/"
        if not uri.startswith(prefix):
            raise KeyError(uri)
        skill_type, skill_id = uri.removeprefix(prefix).split("/", 1)
        skill = self.inspect(skill_id)
        if skill.type != skill_type:
            raise KeyError(uri)
        return skill.path.read_text(encoding="utf-8")


def normalize_skill_content(content: str) -> str:
    if content.startswith("---\n"):
        parts = content.split("---", 2)
        if len(parts) == 3:
            content = parts[2]
    return " ".join(content.casefold().split())
