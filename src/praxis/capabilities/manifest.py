from __future__ import annotations

from dataclasses import dataclass

ALLOWED_KINDS = {"reusable", "stack", "domain"}


@dataclass(frozen=True)
class CapabilityManifest:
    id: str
    version: str
    kind: str
    requires: tuple[str, ...] = ()
    rules: tuple[str, ...] = ()
    templates: tuple[str, ...] = ()
    executors: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: dict) -> CapabilityManifest:
        kind = data.get("kind", "")
        if kind not in ALLOWED_KINDS:
            from praxis.errors import PraxisError

            raise PraxisError(
                "CAPABILITY_INVALID_KIND", "capability kind 非法。", 2, {"kind": kind}
            )
        return cls(
            id=data["id"],
            version=data.get("version", "0.1.0"),
            kind=kind,
            requires=tuple(data.get("requires", [])),
            rules=tuple(data.get("rules", [])),
            templates=tuple(data.get("templates", [])),
            executors=tuple(data.get("executors", [])),
        )
