from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProfileManifest:
    id: str
    version: str
    extends: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    parameters: dict[str, Any] = field(default_factory=dict)
    project_types: tuple[str, ...] = ()
    defaults: dict[str, Any] = field(default_factory=dict)
    constraints: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProfileManifest:
        return cls(
            id=data["id"],
            version=data.get("version", "0.1.0"),
            extends=tuple(data.get("extends", [])),
            capabilities=tuple(data.get("capabilities", [])),
            parameters=dict(data.get("parameters", {})),
            project_types=tuple(data.get("project_types", [])),
            defaults=dict(data.get("defaults", {})),
            constraints=dict(data.get("constraints", {})),
        )
