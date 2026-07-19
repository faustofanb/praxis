from __future__ import annotations

import tomllib
from pathlib import Path

from praxis.capabilities.manifest import CapabilityManifest
from praxis.errors import PraxisError
from praxis.paths import ensure_inside, package_root


class CapabilityRegistry:
    def __init__(self, roots: list[Path] | None = None):
        self.roots = roots or [package_root() / "capabilities"]
        self._items: dict[str, CapabilityManifest] | None = None

    def load(self) -> dict[str, CapabilityManifest]:
        if self._items is not None:
            return self._items
        items: dict[str, CapabilityManifest] = {}
        for root in self.roots:
            if not root.exists():
                continue
            for manifest_path in sorted(root.rglob("capability.toml")):
                data = tomllib.loads(manifest_path.read_text())
                manifest = CapabilityManifest.from_dict(data)
                if manifest.id in items:
                    raise PraxisError(
                        "CAPABILITY_DUPLICATE", "capability ID 重复。", 2, {"id": manifest.id}
                    )
                cap_root = manifest_path.parent
                for rel in [*manifest.rules, *manifest.templates, *manifest.executors]:
                    ensure_inside(cap_root, cap_root / rel)
                items[manifest.id] = manifest
        for manifest in items.values():
            for required in manifest.requires:
                if required not in items:
                    raise PraxisError(
                        "CAPABILITY_NOT_FOUND",
                        "capability 依赖不存在。",
                        2,
                        {"id": required, "required_by": manifest.id},
                    )
        self._items = items
        return items

    def get(self, capability_id: str) -> CapabilityManifest:
        items = self.load()
        try:
            return items[capability_id]
        except KeyError as exc:
            raise PraxisError(
                "CAPABILITY_NOT_FOUND", "未找到指定 capability。", 2, {"id": capability_id}
            ) from exc
