from __future__ import annotations

from importlib.resources import files
from pathlib import Path


def package_root() -> Path:
    resource_root = files("praxis.resources")
    return Path(str(resource_root))


def workspace_file(root: Path) -> Path:
    return root / ".praxis" / "workspace.toml"


def ensure_inside(base: Path, candidate: Path) -> Path:
    base_resolved = base.resolve()
    resolved = candidate.resolve()
    if base_resolved != resolved and base_resolved not in resolved.parents:
        from praxis.errors import PraxisError

        raise PraxisError(
            "PATH_TRAVERSAL",
            "路径越过允许的 capability 或 workspace 边界。",
            2,
            {"path": str(candidate)},
        )
    return resolved
