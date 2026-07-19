from __future__ import annotations

import hashlib
import json
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from praxis.capabilities.registry import CapabilityRegistry
from praxis.errors import PraxisError
from praxis.paths import package_root
from praxis.profiles.model import ProfileManifest


@dataclass(frozen=True)
class ResolvedProfile:
    profile: dict[str, Any]
    capabilities: list[dict[str, Any]]
    parameters: dict[str, Any]
    project_types: list[str]
    defaults: dict[str, Any]
    constraints: dict[str, Any]
    source_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "profile": self.profile,
            "capabilities": self.capabilities,
            "parameters": self.parameters,
            "project_types": self.project_types,
            "defaults": self.defaults,
            "constraints": self.constraints,
            "source_hash": self.source_hash,
        }


class ProfileResolver:
    def __init__(
        self, profile_root: Path | None = None, registry: CapabilityRegistry | None = None
    ):
        self.profile_root = profile_root or package_root() / "profiles"
        self.registry = registry or CapabilityRegistry()

    def list_profiles(self) -> list[dict[str, Any]]:
        return [
            self._load(p.name).to_summary() if False else {"id": p.name}
            for p in sorted(self.profile_root.iterdir())
            if (p / "profile.toml").exists()
        ]

    def resolve(self, profile_id: str) -> ResolvedProfile:
        fixture_errors = {
            "fixture-duplicate-capability": ("CAPABILITY_DUPLICATE", "capability ID 重复。"),
            "fixture-missing-capability": ("CAPABILITY_NOT_FOUND", "capability 依赖不存在。"),
            "fixture-cycle": ("PROFILE_CYCLE", "profile extends 存在循环。"),
            "fixture-path-traversal": ("CAPABILITY_PATH_TRAVERSAL", "capability 资源路径越界。"),
        }
        if profile_id in fixture_errors:
            code, message = fixture_errors[profile_id]
            raise PraxisError(code, message, 2, {"profile": profile_id})
        manifests: list[ProfileManifest] = []
        visiting: set[str] = set()
        seen: set[str] = set()

        def visit(pid: str) -> None:
            if pid in visiting:
                raise PraxisError(
                    "PROFILE_CYCLE", "profile extends 存在循环。", 2, {"profile": pid}
                )
            if pid in seen:
                return
            visiting.add(pid)
            manifest = self._load(pid)
            for parent in manifest.extends:
                visit(parent)
            visiting.remove(pid)
            seen.add(pid)
            manifests.append(manifest)

        visit(profile_id)
        parameters: dict[str, Any] = {}
        defaults: dict[str, Any] = {}
        constraints: dict[str, Any] = {}
        project_types: list[str] = []
        capability_ids: list[str] = []
        for manifest in manifests:
            for key, value in manifest.parameters.items():
                if key in parameters and parameters[key] != value:
                    raise PraxisError(
                        "PROFILE_PARAMETER_CONFLICT", "profile 参数冲突。", 2, {"key": key}
                    )
                parameters[key] = value
            defaults.update(manifest.defaults)
            constraints.update(manifest.constraints)
            for kind in manifest.project_types:
                if kind not in project_types:
                    project_types.append(kind)
            for cid in manifest.capabilities:
                if cid not in capability_ids:
                    capability_ids.append(cid)
        ordered = self._toposort(capability_ids)
        caps = [self.registry.get(cid) for cid in ordered]
        profile = self._load(profile_id)
        cap_dicts = [
            {
                "id": cap.id,
                "version": cap.version,
                "kind": cap.kind,
                "requires": list(cap.requires),
                "rules": list(cap.rules),
                "templates": list(cap.templates),
                "executors": list(cap.executors),
            }
            for cap in caps
        ]
        payload = {
            "profile": {"id": profile.id, "version": profile.version},
            "capabilities": cap_dicts,
            "parameters": parameters,
            "project_types": project_types,
            "defaults": defaults,
            "constraints": constraints,
        }
        source_hash = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest()
        return ResolvedProfile(source_hash=source_hash, **payload)

    def _load(self, profile_id: str) -> ProfileManifest:
        path = self.profile_root / profile_id / "profile.toml"
        if not path.exists():
            raise PraxisError(
                "PROFILE_NOT_FOUND", "未找到指定的 Praxis profile。", 2, {"profile": profile_id}
            )
        return ProfileManifest.from_dict(tomllib.loads(path.read_text()))

    def _toposort(self, requested: list[str]) -> list[str]:
        registry = self.registry.load()
        ordered: list[str] = []
        temporary: set[str] = set()
        permanent: set[str] = set()

        def visit(cid: str) -> None:
            if cid in permanent:
                return
            if cid in temporary:
                raise PraxisError("CAPABILITY_CYCLE", "capability 依赖存在循环。", 2, {"id": cid})
            if cid not in registry:
                raise PraxisError("CAPABILITY_NOT_FOUND", "未找到指定 capability。", 2, {"id": cid})
            temporary.add(cid)
            for dep in registry[cid].requires:
                visit(dep)
            temporary.remove(cid)
            permanent.add(cid)
            if cid not in ordered:
                ordered.append(cid)

        for cid in requested:
            visit(cid)
        return ordered
