from __future__ import annotations

import json
import tempfile
from pathlib import Path

from praxis.workspace.service import WorkspaceService


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        WorkspaceService(root).init(profile_id="base")
        print(json.dumps({"ok": True, "message": "smoke 通过"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
