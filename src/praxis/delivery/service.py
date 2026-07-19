from __future__ import annotations

from pathlib import Path

from praxis.errors import PraxisError
from praxis.verification.service import VerificationService


class DeliveryService:
    def __init__(self, root: Path | str):
        self.root = Path(root)

    def prepare(self, require_check: str | None = None) -> dict:
        result = VerificationService(self.root).run()
        ok_checks = {check["id"] for check in result["checks"] if check["ok"]}
        if require_check and require_check not in ok_checks:
            raise PraxisError(
                "DELIVERY_BLOCKED",
                "required check 未通过，交付被阻止。",
                4,
                {"check": require_check},
            )
        return {"status": "ready", "verification": result}
