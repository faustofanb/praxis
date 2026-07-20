from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from praxis.documents.atomic_writer import atomic_write_text
from praxis.knowledge.requirements import RequirementService
from praxis.result import Result
from praxis.storage.sqlite import StateStore
from praxis.workspace.service import WorkspaceService

_DOMAIN_ID = re.compile(r"^[a-z][a-z0-9-]{1,63}$")


class DomainService:
    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.workspace = WorkspaceService(self.root)
        self.store = StateStore(self.root)

    def add(self, system_id: str, domain_id: str, name_zh: str) -> Result:
        if not _DOMAIN_ID.fullmatch(domain_id):
            return Result(False, "DOMAIN_ID_INVALID")
        if not name_zh.strip():
            return Result(False, "DOMAIN_NAME_REQUIRED")
        payload = self.workspace.load(raw=True)
        system = next(
            (item for item in payload.get("systems", []) if item["id"] == system_id), None
        )
        if not system:
            return Result(False, "SYSTEM_NOT_FOUND")
        if domain_id in system.get("domains", []):
            return Result(False, "DOMAIN_ALREADY_EXISTS")
        system.setdefault("domains", []).append(domain_id)
        system["domains"].sort()
        self.workspace._write(payload)
        data = {"domain_id": domain_id, "name_zh": name_zh.strip(), "systems": [system_id]}
        self.store.set("business_domain", domain_id, data)
        self._write_document(data)
        self.store.audit("domain.added", "OK", data)
        return Result(True, data=data)

    def list(self) -> Result:
        payload = self.workspace.load()
        registered = {item["domain_id"]: item for item in self.store.list_scope("business_domain")}
        systems_by_domain: dict[str, list[str]] = {}
        for system in payload.get("systems", []):
            for domain in system.get("domains", []):
                systems_by_domain.setdefault(domain, []).append(system["id"])
        domains = [
            {
                "domain_id": domain,
                "name_zh": registered.get(domain, {}).get("name_zh", domain),
                "systems": sorted(systems),
            }
            for domain, systems in sorted(systems_by_domain.items())
        ]
        return Result(True, data={"domains": domains})

    def merge(self, source: str, target: str) -> Result:
        payload = self.workspace.load(raw=True)
        all_domains = {
            domain for system in payload.get("systems", []) for domain in system.get("domains", [])
        }
        if source not in all_domains or target not in all_domains:
            return Result(False, "DOMAIN_NOT_FOUND")
        for system in payload.get("systems", []):
            domains = system.get("domains", [])
            if source in domains:
                system["domains"] = sorted(
                    dict.fromkeys(target if item == source else item for item in domains)
                )
        self.workspace._write(payload)
        updated = self.store.merge_domain(source, target)
        self.store.set("domain_alias", source, {"source": source, "target": target})
        RequirementService(self.root).repair_projections()
        return Result(
            True,
            data={"source": source, "target": target, "updated_requirements": updated},
        )

    def _write_document(self, data: dict[str, Any]) -> None:
        knowledge_root = self.workspace.load()["knowledge_root"]
        path = self.root / knowledge_root / "业务域" / f"{data['domain_id']}.md"
        systems = "\n".join(f"  - {item}" for item in data["systems"])
        atomic_write_text(
            path,
            f"---\n业务域编号: {data['domain_id']}\n业务域名称: {data['name_zh']}\n"
            f"所属系统:\n{systems}\n曾用名称: []\n---\n\n# {data['name_zh']}\n",
        )
