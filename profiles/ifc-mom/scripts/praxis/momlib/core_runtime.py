from __future__ import annotations

import sys
from pathlib import Path


def load_praxis_core() -> None:
    """Expose the synced core, with a source-checkout fallback for profile tests."""
    try:
        import praxis_core  # noqa: F401

        return
    except ModuleNotFoundError:
        pass

    for parent in Path(__file__).resolve().parents:
        runtime_root = parent / "runtime"
        if (runtime_root / "praxis_core" / "__init__.py").is_file():
            sys.path.insert(0, str(runtime_root))
            return
    raise ModuleNotFoundError("cannot locate portable praxis_core runtime")
